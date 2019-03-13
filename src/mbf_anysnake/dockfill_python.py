# -*- coding: future_fstrings -*-
import requests
import tempfile
import re
import os
import subprocess
import packaging.version
import pkg_resources
from pathlib import Path
from .util import combine_volumes


class DockFill_Python:
    def __init__(self, dockerator):
        self.dockerator = dockerator
        self.python_version = self.dockerator.python_version
        self.paths = self.dockerator.paths
        self.paths.update(
            {
                "storage_python": (
                    self.paths["storage"] / "python" / self.python_version
                ),
                "docker_storage_python": "/dockerator/python",
                "docker_code": "/project/code",
                "log_python": self.paths["log_storage"]
                / f"dockerator.python.{self.python_version}.log",
            }
        )
        self.volumes = {
            dockerator.paths["storage_python"]: dockerator.paths[
                "docker_storage_python"
            ]
        }

    def pprint(self):
        print(f"  Python version={self.python_version}")

    def ensure(self):
        # python beyond these versions needs libssl 1.1
        # the older ones need libssl1.0
        # on older debians/ubuntus that would be libssl-dev
        # but on 18.04+ it's libssl1.0-dev
        # and we're not anticipating building on something older
        python_version = self.dockerator.python_version
        if (
            (python_version >= "3.5.3")
            or (python_version >= "3.6.0")
            or (python_version >= "2.7.13")
        ):
            # ssl_lib = "libssl-dev"
            pass
        else:
            raise ValueError("Find a fix for old ssl lib")
            # ssl_lib = "libssl1.0-dev"

        self.dockerator.build(
            target_dir=self.paths["storage_python"],
            target_dir_inside_docker=self.paths["docker_storage_python"],
            relative_check_filename="bin/virtualenv",
            log_name="log_python",
            additional_volumes={},
            version_check=self.check_python_version_exists,
            root=True,
            build_cmds=f"""
#/bin/bash
cd ~/
git clone git://github.com/pyenv/pyenv.git
cd pyenv/plugins/python-build
./install.sh

export MAKE_OPTS=-j{self.dockerator.cores}
export CONFIGURE_OPTS=--enable-shared
export PYTHON_CONFIGURE_OPTS=--enable-shared
python-build {python_version} {self.paths['docker_storage_python']}
{self.paths['docker_storage_python']}/bin/pip install -U pip virtualenv
chown {os.getuid()}:{os.getgid()} {self.paths['docker_storage_python']} -R
echo "done"
""",
        )

    def check_python_version_exists(self):
        version = self.python_version
        r = requests.get("https://www.python.org/doc/versions/").text
        if not (
            f'release/{version}/"' in r or f'release/{version}"'
        ):  # some have / some don't
            raise ValueError(
                f"Unknown python version {version} - check https://www.python.org/doc/versions/"
            )


re_github = r"[A-Za-z0-9-]+\/[A-Za-z0-9]+"


class _DockerFillVenv:
    def __init__(self):
        self.paths.update(
            {
                f"log_{self.name}_venv": (
                    self.log_path / f"dockerator.{self.name}_venv.log"
                ),
                f"log_{self.name}_venv_pip": (
                    self.log_path / f"dockerator.{self.name}_venv_pip.log"
                ),
            }
        )

    def ensure(self):
        self.create_venv()
        self.fill_venv()

    def fill_venv(self, rebuild=False):
        code_packages = {
            k: v
            for (k, v) in self.packages.items()
            if v.startswith("@git+")
            or v.startswith("@hg+")
            or v.startswith("@")
            and re.match(re_github, v[1:])  # github
        }
        code_names = set(code_packages.keys())
        had_to_clone = self.clone_code_packages(code_packages)
        if rebuild:
            to_install = self.packages
            had_to_clone = code_names
        else:
            installed_versions = self.find_installed_package_versions(
                self.dockerator.major_python_version
            )
            for c in code_names:
                if self.safe_name(c) not in installed_versions:
                    had_to_clone.add(c)
            to_install = {
                k: v
                for (k, v) in self.packages.items()
                if (
                    k not in code_names
                    and not version_is_compatible(
                        v, installed_versions.get(self.safe_name(k), "")
                    )
                )
                or (k in code_names and k in had_to_clone)
            }
        if to_install:
            self.install_pip_packages(to_install, had_to_clone)

    def safe_name(self, name):
        return pkg_resources.safe_name(name).lower()

    def clone_code_packages(self, code_packages):
        result = set()
        for name, url_spec in code_packages.items():
            log_key = f"log_{self.name}_venv_{name}"
            self.paths[log_key + "_clone"] = self.log_path / (
                f"dockerator.{self.name}_venv_{name}.pip.log"
            )
            target_path = self.clone_path / name
            with open(str(self.paths[log_key + "_clone"]), "wb") as log_file:
                if not target_path.exists():
                    print("\tcloning", name)
                    result.add(target_path)
                    url = url_spec
                    if url.startswith("@"):
                        url = url[1:]
                    if re.match(re_github, url):
                        method = "git"
                        url = "https://github.com/" + url
                    elif url.startswith("git+"):
                        method = "git"
                        url = url[4:]
                    elif url.startswith("hg+"):
                        method = "hg"
                        url = url[3:]
                    else:
                        raise ValueError(
                            "Could not parse url / must be git+http(s) / hg+https, or github path"
                        )
                    if method == "git":
                        subprocess.check_call(
                            ["git", "clone", url, str(target_path)],
                            stdout=log_file,
                            stderr=log_file,
                        )
                    elif method == "hg":
                        subprocess.check_call(
                            ["hg", "clone", url, str(target_path)],
                            stdout=log_file,
                            stderr=log_file,
                        )
        return result

    def find_installed_packages(self, major_python_version):
        return list(self.find_installed_package_versions(major_python_version).keys())

    def find_installed_package_versions(self, major_python_version):
        venv_dir = (
            self.target_path
            / "lib"
            / ("python" + major_python_version)
            / "site-packages"
        )
        result = {}
        for p in venv_dir.glob("*"):
            if p.name.endswith(".dist-info"):
                name = p.name[: p.name.rfind("-", 0, -5)]
                version = p.name[p.name.rfind("-", 0, -5) + 1 : -1 * len(".dist-info")]
                result[self.safe_name(name)] = version
            elif p.name.endswith(".egg-link"):
                name = p.name[: -1 * len(".egg-link")]
                version = "unknown"
                result[self.safe_name(name)] = version
        return result

    def install_pip_packages(self, packages, code_packages):
        """packages are parse_requirements results with method == 'pip'"""
        pkg_string = []
        for k, v in packages.items():
            if k in code_packages:
                pkg_string.append(f'-e "/project/code/{k}"')
            else:
                pkg_string.append('"%s%s"' % (k, v))
        pkg_string = " ".join(pkg_string)
        print(f"\tpip install {pkg_string}")
        self.dockerator._run_docker(
            f"""
#!/bin/bash
    {self.target_path_inside_docker}/bin/pip install {pkg_string}
    echo "done"
    """,
            {
                "volumes": combine_volumes(
                    ro=[self.dockfill_python.volumes],
                    rw=[
                        {
                            self.target_path: self.target_path_inside_docker,
                            self.clone_path: self.clone_path_inside_docker,
                        }
                    ],
                )
            },
            f"log_{self.name}_venv_pip",
        )
        installed_now = self.find_installed_packages(
            self.dockerator.major_python_version
        )
        still_missing = set([self.safe_name(k) for k in packages.keys()]).difference(
            [self.safe_name(k) for k in installed_now]
        )
        if still_missing:
            raise ValueError(
                f"Installation of packages failed: {still_missing}\n"
                + "Check log in "
                + str(self.paths[f"log_{self.name}_venv_pip"])
            )


class DockFill_GlobalVenv(_DockerFillVenv):
    def __init__(self, dockerator, dockfill_python):
        self.dockerator = dockerator
        self.paths = self.dockerator.paths
        self.python_version = self.dockerator.python_version
        self.name = "storage"
        self.paths.update(
            {
                "storage_venv": (self.paths["storage"] / "venv" / self.python_version),
                "docker_storage_venv": "/dockerator/storage_venv",
                "storage_clones": self.paths["storage"] / "code",
                "docker_storage_clones": "/dockerator/storage_clones",
            }
        )
        self.target_path = self.paths["storage_venv"]
        self.target_path_inside_docker = self.paths["docker_storage_venv"]
        self.clone_path = self.paths["storage_clones"]
        self.clone_path_inside_docker = self.paths["docker_storage_clones"]
        self.log_path = self.paths["log_storage"]

        self.dockfill_python = dockfill_python
        self.volumes = {
            self.paths["storage_venv"]: dockerator.paths["docker_storage_venv"],
            self.paths["storage_clones"]: dockerator.paths["docker_storage_clones"],
        }
        self.packages = self.dockerator.global_python_packages
        self.shell_path = str(Path(self.paths["docker_storage_venv"]) / "bin")
        super().__init__()

    def pprint(self):
        print("  Global python packages")
        for entry in self.dockerator.global_python_packages.items():
            print(f"    {entry}")

    def create_venv(self):
        self.dockerator.build(
            target_dir=self.target_path,
            target_dir_inside_docker=self.target_path_inside_docker,
            relative_check_filename=Path("bin") / "activate.fish",
            log_name=f"log_{self.name}_venv",
            additional_volumes=self.dockfill_python.volumes,
            build_cmds=f"""
{self.paths['docker_storage_python']}/bin/virtualenv -p {self.paths['docker_storage_python']}/bin/python {self.target_path_inside_docker}
echo "done"
""",
        )


class DockFill_CodeVenv(_DockerFillVenv):
    def __init__(self, dockerator, dockfill_python, dockfill_global_venv):
        self.dockerator = dockerator
        self.dockfill_global_venv = dockfill_global_venv
        self.paths = self.dockerator.paths
        self.name = "code"
        self.log_path = self.paths["log_code"]
        self.python_version = self.dockerator.python_version
        self.paths.update(
            {
                "code_venv": self.paths["code"] / "venv" / self.python_version,
                "docker_code_venv": "/dockerator/code_venv",
                "code_clones": self.paths["code"],
                "docker_code_clones": "/project/code",
            }
        )
        self.target_path = self.paths["code_venv"]
        self.target_path_inside_docker = self.paths["docker_code_venv"]
        self.clone_path = self.paths["code_clones"]
        self.clone_path_inside_docker = self.paths["docker_code_clones"]
        self.dockfill_python = dockfill_python
        self.volumes = {
            self.paths["code"]: dockerator.paths[f"docker_code"],
            self.paths["code_venv"]: dockerator.paths[f"docker_code_venv"],
        }
        self.packages = self.dockerator.local_python_packages
        self.shell_path = str(Path(self.paths["docker_code_venv"]) / "bin")
        super().__init__()

    def ensure(self):
        super().ensure()
        self.copy_bins_from_global()

    def copy_bins_from_global(self):
        source_dir = self.paths["storage_venv"] / "bin"
        target_dir = self.paths["code_venv"] / "bin"
        for input_fn in source_dir.glob("*"):
            output_fn = target_dir / input_fn.name
            if not output_fn.exists():
                input = input_fn.read_text()
                if input.startswith("#"):
                    n_pos = input.find("\n")
                    first_line = input[:n_pos]
                    if (
                        first_line
                        == f"#!{self.paths['docker_storage_venv']}/bin/python"
                    ):
                        output = (
                            f"#!{self.paths['docker_code_venv']}/bin/python"
                            + input[n_pos:]
                        )
                        output_fn.write_text(output)
            output_fn.chmod(input_fn.stat().st_mode)
        pth_path = (
            self.paths["code_venv"]
            / "lib"
            / ("python" + self.dockerator.major_python_version)
            / "site-packages"
            / "anysnake.pth"
        )
        if not pth_path.exists():
            pth_path.write_text(
                str(
                    self.paths["docker_storage_venv"]
                    / "lib"
                    / ("python" + self.dockerator.major_python_version)
                    / "site-packages"
                )
                + "\n"
            )

    def pprint(self):
        print("  Local python packages")
        for entry in self.dockerator.local_python_packages.items():
            print(f"    {entry}")

    def create_venv(self):
        lib_code = (
            Path(self.paths["docker_code_venv"])
            / "lib"
            / ("python" + self.dockerator.major_python_version)
        )
        lib_storage = (
            Path(self.paths["docker_storage_venv"])
            / "lib"
            / ("python" + self.dockerator.major_python_version)
        )
        sc_file = str(lib_code / "site-packages" / "sitecustomize.py")

        tf = tempfile.NamedTemporaryFile(suffix=".py", mode="w")
        tf.write(
            f"""
import sys
for x in [
    '{lib_storage}/site-packages',
    '{lib_code}/site-packages',
    '{lib_code}',
    ]:
    if x in sys.path:
        sys.path.remove(x)
    sys.path.insert(0, x)
"""
        )
        tf.flush()
        additional_volumes = self.dockfill_python.volumes.copy()
        additional_volumes[tf.name] = "/opt/sitecustomize.py"

        self.dockerator.build(
            target_dir=self.target_path,
            target_dir_inside_docker=self.target_path_inside_docker,
            relative_check_filename=Path("bin") / "activate.fish",
            log_name=f"log_{self.name}_venv",
            additional_volumes=additional_volumes,
            build_cmds=f"""
ls {self.paths['docker_storage_python']}
{self.paths['docker_storage_python']}/bin/virtualenv -p {self.paths['docker_storage_python']}/bin/python {self.target_path_inside_docker}
cp /opt/sitecustomize.py {sc_file}
echo "done"
""",
        )

    def rebuild(self, packages):
        self.fill_venv(rebuild=True)


def version_is_compatible(dep_def, version):
    if version == "":  # not previously installed, I guess
        return False
    if dep_def == "":
        return True
    operators = ["<=", "<", "!=", "==", ">=", ">", "~=", "==="]
    for o in operators:
        if dep_def.startswith(o):
            op = o
            reqver = dep_def[len(op) :]
            break
    else:
        raise ValueError("Could not understand dependency definition %s" % dep_def)
    actual_ver = packaging.version.parse(version)
    if "," in reqver:
        raise NotImplementedError("Currently does not handle version>=x,<=y")
    should_ver = packaging.version.parse(reqver)
    if op == "<=":
        return actual_ver <= should_ver
    elif op == "<":
        return actual_ver < should_ver
    elif op == "!=":
        return actual_ver != should_ver
    elif op == "==":
        return actual_ver == should_ver
    elif op == ">=":
        return actual_ver >= should_ver
    elif op == ">":
        return actual_ver > should_ver
    elif op == "~=":
        raise NotImplementedError(
            "While ~= is undoubtedly useful, it's not implemented in anysnake yet"
        )
    elif op == "===":
        return version == reqver
    else:
        raise NotImplementedError("forget to handle a case?", dep_def, version)


def format_for_pip(parse_result):
    res = parse_result["name"]
    if parse_result["op"]:
        res += parse_result["op"]
        res += parse_result["version"]
    return f'"{res}"'
