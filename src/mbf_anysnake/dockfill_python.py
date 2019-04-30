# -*- coding: future_fstrings -*-
import requests
import tempfile
import re
import os
import subprocess
import packaging.version
import pkg_resources
from pathlib import Path
from .util import combine_volumes, find_storage_path_from_other_machine
import tomlkit


class DockFill_Python:
    def __init__(self, anysnake):
        self.anysnake = anysnake
        self.python_version = self.anysnake.python_version
        self.paths = self.anysnake.paths

        self.paths.update(
            {
                "storage_python": find_storage_path_from_other_machine(
                    self.anysnake, Path("python") / self.python_version
                ),
                "docker_storage_python": "/anysnake/python",
                "docker_code": "/project/code",
                "log_python": self.paths["log_storage"]
                / f"anysnake.python.{self.python_version}.log",
            }
        )
        self.volumes = {
            anysnake.paths["storage_python"]: anysnake.paths["docker_storage_python"]
        }

    def pprint(self):
        print(f"  Python version={self.python_version}")

    def ensure(self):
        # python beyond these versions needs libssl 1.1
        # the older ones need libssl1.0
        # on older debians/ubuntus that would be libssl-dev
        # but on 18.04+ it's libssl1.0-dev
        # and we're not anticipating building on something older
        python_version = self.anysnake.python_version
        if (
            (python_version >= "3.5.3")
            or (python_version >= "3.6.0")
            or (python_version >= "2.7.13")
        ):
            # ssl_lib = "libssl-dev"
            ssl_lib = None
            ssl_cmd = ""
            pass
        else:
            # raise ValueError("Find a fix for old ssl lib")
            ssl_lib = "libssl1.0-dev"
            ssl_cmd = f"sudo apt-get install -y {ssl_lib}"

        return self.anysnake.build(
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
{ssl_cmd}

export MAKE_OPTS=-j{self.anysnake.cores}
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

    def freeze(self):
        return {"base": {"python": self.python_version}}


re_github = r"[A-Za-z0-9-]+\/[A-Za-z0-9]+"


def safe_name(name):
    return pkg_resources.safe_name(name).lower()


class MiniNode:
    def __init__(self, name):
        self.name = safe_name(name)
        self.unsafe_name = name
        self.prerequisites = set()
        self.dependants = set()

    def depends_on(self, other_node):
        self.prerequisites.add(other_node)
        other_node.dependants.add(self)


class _DockerFillVenv:
    def __init__(self):
        self.paths.update(
            {
                f"log_{self.name}_venv": (
                    self.log_path / f"anysnake.{self.name}_venv.log"
                ),
                f"log_{self.name}_venv_pip": (
                    self.log_path / f"anysnake.{self.name}_venv_pip.log"
                ),
            }
        )

    def ensure(self):
        res = self.create_venv()
        res |= self.fill_venv()
        return res

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
                self.anysnake.major_python_version
            )
            for c in code_names:
                if safe_name(c) not in installed_versions:
                    had_to_clone.add(c)
            to_install = {
                k: v
                for (k, v) in self.packages.items()
                if (
                    k not in code_names
                    and not version_is_compatible(
                        v, installed_versions.get(safe_name(k), "")
                    )
                )
                or (k in code_names and k in had_to_clone)
            }
        extra_reqs = []
        if to_install:
            self.install_pip_packages(to_install, had_to_clone, extra_reqs)
            return True
        return False

    def clone_code_packages(self, code_packages):
        result = set()
        for name, url_spec in code_packages.items():
            log_key = f"log_{self.name}_venv_{name}"
            self.paths[log_key + "_clone"] = self.log_path / (
                f"anysnake.{self.name}_venv_{name}.pip.log"
            )
            target_path = self.clone_path / name
            with open(str(self.paths[log_key + "_clone"]), "wb") as log_file:
                if not target_path.exists():
                    print("\tcloning", name)
                    result.add(name)
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
                        try:
                            subprocess.check_call(
                                ["git", "clone", url, str(target_path)],
                                stdout=log_file,
                                stderr=log_file,
                            )
                        except subprocess.CalledProcessError:
                            import shutil

                            shutil.rmtree(target_path)
                            raise
                    elif method == "hg":
                        try:
                            subprocess.check_call(
                                ["hg", "clone", url, str(target_path)],
                                stdout=log_file,
                                stderr=log_file,
                            )
                        except subprocess.CalledProcessError:
                            import shutil

                            shutil.rmtree(target_path)
                            raise

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
                result[safe_name(name)] = version
            elif p.name.endswith(".egg-link"):
                name = p.name[: -1 * len(".egg-link")]
                version = "unknown"
                result[safe_name(name)] = version
            elif p.name.endswith(".so"):
                name = p.name[: p.name.find(".")]
                version = "unknown"
                result[safe_name(name)] = version

        return result

    def is_pyo3_package(self, code_package_name):
        target_path = self.clone_path / code_package_name
        return (
            not (target_path / "setup.py").exists()
            and (target_path / "Cargo.toml").exists()
            and (target_path / "src" / "lib.rs").exists()
        )

    def is_pep517_package(self, editable_name):
        target_path = self.clone_path / editable_name / "pyproject.toml"
        return target_path.exists()

    def is_pep517_but_setuptools(self, editable_name):
        target_path = self.clone_path / editable_name / "pyproject.toml"
        if not target_path.exists():
            return False
        return "setuptools" in target_path.read_text()

    def install_pip_packages(
        self, packages, editable_packages, packages_to_install_extra_reqs_from
    ):
        """packages are parse_requirements results with method == 'pip'"""
        # this is a horrible mess of cludgy hacks to work around limitations in
        # pip
        # such as 'no sensible dependency resolution for editable insstlls'
        # 'no editable installs for pep517 packages'
        step_a = []
        step_b = []
        step_c = []

        # step a - install editable packages without dependencies and non-editable
        # to circumvent pep517 limitations
        # step b - pip install (without -e) everything
        # step c - unistall editable packages and reinstall with python setup.py
        # develop
        pip_cmd = []
        for k, v in packages.items():
            if k not in editable_packages and safe_name(k) not in editable_packages:
                pip_cmd.append(f'"{k}{v}"')
            else:
                if not self.is_pyo3_package(k):
                    step_a.append(f"pip install /project/code/{k} --no-deps")
                else:
                    if self.anysnake.dockfill_rust is None:
                        raise ValueError(f"pyo3 package {k} but no Rust definied")

                pip_cmd.append(f"/project/code/{k}")
        step_b.append(("pip install --disable-pip-version-check \\\n" + "\n".join(["  " + x + " \\" for x in pip_cmd]))[:-2])

        for k in editable_packages:
            if self.is_pyo3_package(k):
                step_c.append(f"cd /project/code/{k} && pyo3-pack develop --release")
            elif not self.is_pep517_package(k) or self.is_pep517_but_setuptools(k):
                #step_c.append(f"pip uninstall {k}")
                #step_c.append(f"cd /project/code/{k} && python setup.py develop")
                step_c.append(f"pip install -e /project/code/{k} --no-use-pep517")
            else:
                raise ValueError(
                    f"package {k} was pep517 but not setuptools"
                    " - you will need to take care of that case"
                )
        for k in packages_to_install_extra_reqs_from:
            step_c.append(f'pip install "/project/code/{k}[{extra}]"')

        volumes_ro = self.dockfill_python.volumes.copy()
        volumes_rw = {
            self.target_path: self.target_path_inside_docker,
            self.clone_path: self.clone_path_inside_docker,
        }
        env = {}
        paths = [self.target_path_inside_docker + "/bin"]
        if self.anysnake.dockfill_rust is not None:  # if we have a rust, use it
            volumes_ro.update(self.anysnake.dockfill_rust.volumes)
            volumes_rw.update(self.anysnake.dockfill_rust.rw_volumes)
            paths.append(self.anysnake.dockfill_rust.shell_path)
            env.update(self.anysnake.dockfill_rust.env)
        from .cli import home_files

        home_inside_docker = "/home/u%i" % os.getuid()
        for h in home_files:
            p = Path("~").expanduser() / h
            if p.exists():
                volumes_ro[str(p)] = str(Path(home_inside_docker) / h)

            
        env["EXTPATH"] = ":".join(paths)
        # /anysnake/code_venv/bin /anysnake/cargo/bin /anysnake/code_venv/bin /anysnake/storage_venv/bin /anysnake/R/bin /usr/local/sbin /usr/local/bin /usr/sbin /usr/bin /sbin /bin /machine/opt/infrastructure/client /machine/opt/infrastructure/repos/FloatingFileSystemClient
        cmd = "\n".join(step_a + step_b + step_c)

        return_code, logs = self.anysnake._run_docker(
            f"""
#!/bin/bash
    export PATH=$PATH:$EXTPATH
    echo "Path: $PATH"
    echo "pip cmd:"
    echo <<EOF
{cmd}
EOF
{cmd}
    echo "done"
  
    """,
            {
                "volumes": combine_volumes(ro=volumes_ro, rw=volumes_rw),
                "environment": env,
            },
            f"log_{self.name}_venv_pip",
        )
        installed_now = self.find_installed_packages(self.anysnake.major_python_version)
        still_missing = set([safe_name(k) for k in packages.keys()]).difference(
            [safe_name(k) for k in installed_now]
        )
        if still_missing:
            msg = f"Installation of packages failed: {still_missing}\n"
        elif (isinstance(return_code, int) and (return_code != 0)) or (
            not isinstance(return_code, int) and (return_code["StatusCode"] != 0)
        ):
            msg = f"Installation of packages failed: return code was not 0 (was {return_code})\n"
        else:
            msg = ""
        if msg:
            print(self.paths[f"log_{self.name}_venv_pip"].read_text())
            raise ValueError(
                msg + "Check log in " + str(self.paths[f"log_{self.name}_venv_pip"])
            )


class DockFill_GlobalVenv(_DockerFillVenv):
    def __init__(self, anysnake, dockfill_python):
        self.anysnake = anysnake
        self.paths = self.anysnake.paths
        self.python_version = self.anysnake.python_version
        self.name = "storage"
        self.paths.update(
            {
                "storage_venv": (self.paths["storage"] / "venv" / self.python_version),
                "docker_storage_venv": "/anysnake/storage_venv",
                "storage_clones": self.paths["storage"] / "code",
                "docker_storage_clones": "/anysnake/storage_clones",
            }
        )
        self.target_path = self.paths["storage_venv"]
        self.target_path_inside_docker = self.paths["docker_storage_venv"]
        self.clone_path = self.paths["storage_clones"]
        self.clone_path_inside_docker = self.paths["docker_storage_clones"]
        self.log_path = self.paths["log_storage"]

        self.dockfill_python = dockfill_python
        self.volumes = {
            self.paths["storage_venv"]: anysnake.paths["docker_storage_venv"],
            self.paths["storage_clones"]: anysnake.paths["docker_storage_clones"],
        }
        self.packages = self.anysnake.global_python_packages
        self.shell_path = str(Path(self.paths["docker_storage_venv"]) / "bin")
        super().__init__()

    def pprint(self):
        print("  Global python packages")
        for entry in self.anysnake.global_python_packages.items():
            print(f"    {entry}")

    def create_venv(self):
        return self.anysnake.build(
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

    def freeze(self):
        """Return a toml string with all the installed versions"""
        result = {}
        for k, v in self.find_installed_package_versions(
            self.anysnake.major_python_version
        ).items():
            result[k] = f"{v}"
        return {"global_python": result}


class DockFill_CodeVenv(_DockerFillVenv):
    def __init__(self, anysnake, dockfill_python, dockfill_global_venv):
        self.anysnake = anysnake
        self.dockfill_global_venv = dockfill_global_venv
        self.paths = self.anysnake.paths
        self.name = "code"
        self.log_path = self.paths["log_code"]
        self.python_version = self.anysnake.python_version
        self.paths.update(
            {
                "code_venv": self.paths["code"] / "venv" / self.python_version,
                "docker_code_venv": "/anysnake/code_venv",
                "code_clones": self.paths["code"],
                "docker_code_clones": "/project/code",
            }
        )
        self.target_path = self.paths["code_venv"]
        self.target_path_inside_docker = self.paths["docker_code_venv"]
        self.clone_path = self.paths["code_clones"]
        self.clone_path_inside_docker = self.paths["docker_code_clones"]
        self.dockfill_python = dockfill_python
        self.volumes = {self.paths["code_venv"]: anysnake.paths[f"docker_code_venv"]}
        self.rw_volumes = {self.paths["code"]: anysnake.paths[f"docker_code"]}
        self.packages = self.anysnake.local_python_packages
        self.shell_path = str(Path(self.paths["docker_code_venv"]) / "bin")
        super().__init__()

    def ensure(self):
        super().ensure()
        self.copy_bins_from_global()
        self.fill_sitecustomize()
        return False

    def copy_bins_from_global(self):
        source_dir = self.paths["storage_venv"] / "bin"
        target_dir = self.paths["code_venv"] / "bin"
        for input_fn in source_dir.glob("*"):
            output_fn = target_dir / input_fn.name
            if not output_fn.exists():
                input = input_fn.read_bytes()
                if input.startswith(b"#"):
                    n_pos = input.find(b"\n")
                    first_line = input[:n_pos]
                    if (
                        first_line
                        == f"#!{self.paths['docker_storage_venv']}/bin/python".encode(
                            "utf-8"
                        )
                    ):
                        output = (
                            f"#!{self.paths['docker_code_venv']}/bin/python".encode(
                                "utf-8"
                            )
                            + input[n_pos:]
                        )
                        output_fn.write_bytes(output)
                else:
                    output_fn.write_bytes(input)
            output_fn.chmod(input_fn.stat().st_mode)
        pth_path = (
            self.paths["code_venv"]
            / "lib"
            / ("python" + self.anysnake.major_python_version)
            / "site-packages"
            / "anysnake.pth"
        )
        if not pth_path.exists():
            pth_path.write_text(
                str(
                    self.paths["docker_storage_venv"]
                    / "lib"
                    / ("python" + self.anysnake.major_python_version)
                    / "site-packages"
                )
                + "\n"
            )

    def pprint(self):
        print("  Local python packages")
        for entry in self.anysnake.local_python_packages.items():
            print(f"    {entry}")

    def create_venv(self):

        additional_volumes = self.dockfill_python.volumes.copy()

        self.anysnake.build(
            target_dir=self.target_path,
            target_dir_inside_docker=self.target_path_inside_docker,
            relative_check_filename=Path("bin") / "activate.fish",
            log_name=f"log_{self.name}_venv",
            additional_volumes=additional_volumes,
            build_cmds=f"""
ls {self.paths['docker_storage_python']}
{self.paths['docker_storage_python']}/bin/virtualenv -p {self.paths['docker_storage_python']}/bin/python {self.target_path_inside_docker}
echo "done"
""",
        )
        return False

    def fill_sitecustomize(self):
        lib_code = (
            Path(self.paths["docker_code_venv"])
            / "lib"
            / ("python" + self.anysnake.major_python_version)
        )
        lib_storage = (
            Path(self.paths["docker_storage_venv"])
            / "lib"
            / ("python" + self.anysnake.major_python_version)
        )
        if "docker_storage_rpy2" in self.paths:
            lib_rpy2 = (
                Path(self.paths["docker_storage_rpy2"])
                / "lib"
                / ("python" + self.anysnake.major_python_version)
            )
            rpy2_venv_str = f"'{lib_rpy2}/site-packages',"
        else:
            rpy2_venv_str = ""
        sc_file = str(
            self.paths["code_venv"]
            / "lib"
            / ("python" + self.anysnake.major_python_version)
            / "site-packages"
            / "sitecustomize.py"
        )

        tf = open(sc_file, "w")
        tf.write(
            f"""
import sys
for x in [
    {rpy2_venv_str}
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

    def rebuild(self, packages):
        if packages:
            self.packages = {k: self.packages[k] for k in packages}
            if not self.packages:
                raise ValueError("No packages matching your spec")
        self.fill_venv(rebuild=True)

    def fill_venv(self, rebuild=False):
        super().fill_venv(rebuild=rebuild)
        return False

    def freeze(self):
        """Return a toml string with all the installed versions"""
        result = {}
        for k, v in self.find_installed_package_versions(
            self.anysnake.major_python_version
        ).items():
            result[k] = f"{v}"
        return {"python": result}


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
