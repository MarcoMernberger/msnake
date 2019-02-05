import requests
import tempfile
import re
import os
import subprocess
import packaging.version
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
                "docker_code": "/dockerator/code",
                "log_python": self.paths["log_storage"]
                / f"dockerator.python.{self.python_version}.log",
            }
        )
        self.volumes = {
            dockerator.paths["storage_python"]: dockerator.paths[
                "docker_storage_python"
            ]
        }

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
            ssl_lib = "libssl-dev"
        else:
            raise ValueError("Find a fix for old ssl lib")
            ssl_lib = "libssl1.0-dev"

        self.dockerator.build(
            target_dir=self.paths["storage_python"],
            target_dir_inside_docker=self.paths["docker_storage_python"],
            relative_check_filename="bin/virtualenv",
            log_name="log_python",
            additional_volumes={},
            version_check=self.check_python_version_exists(),
            root=True,
            build_cmds=f"""
#/bin/bash
cd ~/
git clone git://github.com/pyenv/pyenv.git
cd pyenv/plugins/python-build
./install.sh

export MAKE_OPTS=-j{self.dockerator.cores}
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

    
    def fill_venv(self):
        print("filling", self.name)
        code_packages = {
            k: v
            for (k, v) in self.packages.items()
            if v.startswith("@git+")
            or v.startswith("@hg+")
            or v.startswith("@")
            and re.match(re_github, v[1:])  # github
        }
        code_names = set(code_packages.keys())
        pip_packages = [
            (k, v) for (k, v) in self.packages.items() if k not in code_names
        ]

        installed_versions = self.find_installed_package_versions(
            self.dockerator.major_python_version
        )
        installed = set(installed_versions.keys())
        missing_pip = {
            k: v
            for (k, v) in pip_packages
            if k.lower() not in installed
            or not version_is_compatible(v, installed_versions[k.lower()])
        }
        if missing_pip:
            print("\tpip install", list(missing_pip.keys()))
            self.install_pip_packages(missing_pip, self.dockfill_python)

        missing_code = set([k for k in code_packages.keys() if not k in installed])
        self.install_code_packages(code_packages, missing_code)

    def install_code_packages(self, code_packages, missing_code):
        for name, url_spec in code_packages.items():
            log_key = f"log_{self.name}_venv_{name}"
            self.paths[log_key + "_pip"] = self.log_path / (
                f"dockerator.{self.name}_venv_{name}.pip.log"
            )
            self.paths[log_key + "_clone"] = self.log_path / (
                f"dockerator.{self.name}_venv_{name}.pip.log"
            )
            target_path = self.paths["code"] / name
            with open(self.paths[log_key + "_clone"], "wb") as log_file:
                if not target_path.exists():
                    missing_code.add(name)
                    print("\tcloning", name)
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
                            ["git", "clone", url, target_path],
                            stdout=log_file,
                            stderr=log_file,
                        )
                    elif method == "hg":
                        subprocess.check_call(
                            ["hg", "clone", url, target_path],
                            stdout=log_file,
                            stderr=log_file,
                        )
        for name in missing_code:
            print("\tpip install -e", "/opt/code/" + name)
            safe_name = name.replace("/", "_")
            log_key = f"log_{self.name}_venv_{name}"
            self.dockerator._run_docker(
                f"""
    echo {self.paths['docker_code_venv']}/bin/pip install -U -e {self.paths['docker_code']}/{name}
    {self.paths['docker_code_venv']}/bin/pip install -U -e {self.paths['docker_code']}/{name}
    echo "done"
    """,
                {
                    "volumes": combine_volumes(
                        ro=self.dockfill_python.volumes,
                        rw=[
                            {self.paths["code"]: self.paths["docker_code"]},
                            self.volumes,
                        ],
                    )
                },
                log_key + "_pip",
            )
        installed_now = self.find_installed_packages(
            self.dockerator.major_python_version
        )
        still_missing = set([x.lower() for x in missing_code]).difference(installed_now)
        if still_missing:
            raise ValueError(
                "Not all code packages installed. Missing were: %s" % (still_missing)
            )

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
                result[name.lower()] = version
            elif p.name.endswith(".egg-link"):
                name = p.name[: -1 * len(".egg-link")]
                version = "unknown"
                result[name.lower()] = version
        return result

    def install_pip_packages(self, packages, dockfill_python):
        """packages are parse_requirements results with method == 'pip'"""
        pkg_string = " ".join(["'%s%s'" % (k, v) for (k, v) in packages.items()])

        self.dockerator._run_docker(
            f"""
    {self.target_path_inside_docker}/bin/pip install {pkg_string}
    echo "done"
    """,
            {
                "volumes": combine_volumes(
                    ro=[dockfill_python.volumes],
                    rw=[{self.target_path: self.target_path_inside_docker}],
                )
            },
            f"log_{self.name}_venv_pip",
        )
        installed_now = self.find_installed_packages(
            self.dockerator.major_python_version
        )
        still_missing = set(packages.keys()).difference(installed_now)
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
            }
        )
        self.target_path = self.paths["storage_venv"]
        self.target_path_inside_docker = self.paths["docker_storage_venv"]
        self.log_path = self.paths["log_storage"]

        self.dockfill_python = dockfill_python
        self.volumes = {
            self.paths["storage_venv"]: dockerator.paths[f"docker_storage_venv"]
        }
        self.packages = self.dockerator.global_python_packages
        super().__init__()

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
    def __init__(self, dockerator, dockfill_python):
        self.dockerator = dockerator
        self.paths = self.dockerator.paths
        self.name = "code"
        self.log_path = self.paths["log_code"]
        self.python_version = self.dockerator.python_version
        self.paths.update(
            {
                "code_venv": self.paths["code"] / "venv" / self.python_version,
                "docker_code_venv": "/dockerator/code_venv",
            }
        )
        self.target_path = self.paths["code_venv"]
        self.target_path_inside_docker = self.paths["docker_code_venv"]
        self.dockfill_python = dockfill_python
        self.volumes = {
            self.paths["code"]: dockerator.paths[f"docker_code"],
            self.paths["code_venv"]: dockerator.paths[f"docker_code_venv"],
        }
        self.packages = self.dockerator.local_python_packages
        super().__init__()

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
{self.paths['docker_storage_python']}/bin/virtualenv -p {self.paths['docker_storage_python']}/bin/python {self.target_path_inside_docker}
cp /opt/sitecustomize.py {sc_file}
echo "done"
""",
        )


def version_is_compatible(dep_def, version):
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
