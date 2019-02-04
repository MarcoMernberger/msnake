import requests
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
                "code_venv": self.paths["code"] / self.python_version / "venv",
                "storage_python": (
                    self.paths["storage"] / "python" / self.python_version
                ),
                "docker_storage_python": "/dockerator/python",
                "docker_code": "/dockerator/code",
                "log_python": self.paths["log_storage"] / "dockerator.python.log",
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
        if not f"release/{version}/" in r:
            raise ValueError(
                f"Unknown python version {version} - check https://www.python.org/doc/versions/"
            )


class _DockerFillVenv:
    def create_venv(self):
        self.dockerator.build(
            target_dir=self.target_dir,
            target_dir_inside_docker=self.target_dir_inside_docker,
            relative_check_filename=Path("bin") / "activate.fish",
            log_name=self.log_name,
            additional_volumes=self.dockfill_python.volumes,
            build_cmds=f"""
{self.paths['docker_storage_python']}/bin/virtualenv -p {self.paths['docker_storage_python']}/bin/python {self.target_dir_inside_docker}
echo "done"
""",
        )

    def ensure(self):
        self.create_venv()
        self.fill_venv()


class DockFill_GlobalVenv(_DockerFillVenv):
    def __init__(self, dockerator, dockfill_python):
        self.dockerator = dockerator
        self.python_version = self.dockerator.python_version
        self.paths = self.dockerator.paths
        self.paths.update(
            {
                "storage_venv": (self.paths["storage"] / "venv" / self.python_version),
                "docker_storage_venv": "/dockerator/venv",
                "log_storage_venv": (
                    self.paths["log_storage"] / "dockerator.storage_venv.log"
                ),
                "log_storage_venv_pip": (
                    self.paths["log_storage"] / "dockerator.storage_venv_pip.log"
                ),
            }
        )
        self.log_name = "log_storage_venv"
        self.target_dir = self.paths["storage_venv"]
        self.target_dir_inside_docker = self.paths["docker_storage_venv"]
        self.dockfill_python = dockfill_python
        self.volumes = {
            self.paths["storage_venv"]: dockerator.paths[f"docker_storage_venv"]
        }

    def fill_venv(self):
        print("fill_global_venv")
        parsed_packages = list(self.dockerator.global_venv_packages.values())
        pip_packages = [x for x in parsed_packages if x["method"] == "pip"]
        non_pip_packages = [x for x in parsed_packages if x["method"] != "pip"]
        if non_pip_packages:
            raise ValueError("the global_venv must receive *only* pypi packages")
        installed = find_installed_packages(
            self.paths["storage_venv"], self.dockerator.major_python_version
        )
        missing = [x for x in pip_packages if not x["name"] in installed]
        print("missing pip", missing)
        if missing:
            install_pip_packages(
                self.dockerator, "storage", missing, self.dockfill_python
            )


class DockFill_CodeVenv(_DockerFillVenv):
    def __init__(self, dockerator, dockfill_python):
        self.dockerator = dockerator
        self.python_version = self.dockerator.python_version
        self.paths = self.dockerator.paths
        self.paths.update(
            {
                "docker_code_venv": "/dockerator/code_venv",
                "log_code_venv": self.paths["log_code"] / "dockerator.code_venv.log",
                "log_code_venv_pip": (
                    self.paths["log_code"] / "dockerator.code_venv_pip.log"
                ),
            }
        )
        self.log_name = "log_code_venv"
        self.target_dir = self.paths["code_venv"]
        self.target_dir_inside_docker = self.paths["docker_code_venv"]
        self.dockfill_python = dockfill_python
        self.volumes = {self.paths["code_venv"]: dockerator.paths[f"docker_code_venv"]}

    def fill_venv(self):
        print("fill_local_venv")
        parsed_packages = list(self.dockerator.local_venv_packages.values())
        pip_packages = [x for x in parsed_packages if x["method"] == "pip"]
        code_packages = [x for x in parsed_packages if x["method"] in ("git", "hg")]

        installed_versions = find_installed_package_versions(
            self.paths["code_venv"], self.dockerator.major_python_version
        )
        installed = set(installed_versions.keys())
        missing_pip = [
            x
            for x in pip_packages
            if x["name"].lower() not in installed
            or not version_is_compatible(x, installed_versions[x["name"].lower()])
        ]
        print("missing_pip", [x['name'] for x in missing_pip])
        if missing_pip:
            install_pip_packages(
                self.dockerator, "code", missing_pip, self.dockfill_python
            )
        missing_code = [x for x in code_packages if not x["name"] in installed]
        print("missing_code", [x['name'] for x in missing_code])
        for p in code_packages:
            target_path = self.paths["code"] / self.python_version / p["name"]
            if not target_path.exists():
                print("cloning", p["name"])
                if p["method"] == "git":
                    subprocess.check_call(["git", "clone", p["url"], target_path])
                elif p["method"] == "hg":
                    subprocess.check_call(["hg", "clone", p["url"], target_path])
            if not p["name"] in installed:
                print("pip install -e", "/opt/code/" + p["name"])
                self.paths[f'log_code_venv_{p["name"]}'] = self.paths["log_code"] / (
                    "dockerator.code_venv_" + p["name"].replace("/", "_") + ".log"
                )
                self.dockerator._run_docker(
                    f"""
echo {self.paths['docker_code_venv']}/bin/pip3 install -U -e {self.paths['docker_code']}//{p['name']}
{self.paths['docker_code_venv']}/bin/pip3 install -U -e {self.paths['docker_code']}//{p['name']}
echo "done2"
""",
                    {
                        "volumes": combine_volumes(
                            ro=self.dockfill_python.volumes,
                            rw=[{self.paths["code"] / self.python_version: self.paths["docker_code"]},
                                self.volumes],
                        )
                    },
                    f'log_code_venv_{p["name"]}',
                )
        installed_now = find_installed_packages(
            self.paths["code_venv"], self.dockerator.major_python_version
        )
        still_missing = set([x["name"].lower() for x in missing_code]).difference(
            installed_now
        )
        if still_missing:
            raise ValueError(
                "Not all code packages installed. Missing were: %s" % (still_missing)
            )


def version_is_compatible(parsed_req, version):
    if not parsed_req["op"]:
        return True
    actual_ver = packaging.version.parse(version)
    if "," in parsed_req["version"]:
        raise NotImplementedError("Currently does not handle version>=x,<=y")
    should_ver = packaging.version.parse(parsed_req["version"])
    if parsed_req["op"] == ">":
        return actual_ver > should_ver
    elif parsed_req["op"] == ">=":
        return actual_ver >= should_ver
    elif parsed_req["op"] == "<=":
        return actual_ver <= should_ver
    elif parsed_req["op"] == "<":
        return actual_ver < should_ver
    elif parsed_req["op"] == "==":
        return actual_ver == should_ver
    else:
        raise NotImplementedError("forget to handle a case?", parsed_req, version)


def find_installed_packages(venv_dir, major_python_version):
    return list(find_installed_package_versions(venv_dir, major_python_version).keys())


def find_installed_package_versions(venv_dir, major_python_version):
    venv_dir = venv_dir / "lib" / ("python" + major_python_version) / "site-packages"
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


def format_for_pip(parse_result):
    res = parse_result["name"]
    if parse_result["op"]:
        res += parse_result["op"]
        res += parse_result["version"]
    return f'"{res}"'


def install_pip_packages(dockerator, cs, packages, dockfill_python):
    """packages are parse_requirements results with method == 'pip'"""
    for x in packages:
        if x["method"] != "pip":
            raise ValueError("passed not pip packages to install_pip_packages")
    pkg_string = " ".join([format_for_pip(x) for x in packages])

    dockerator._run_docker(
        f"""
{dockerator.paths['docker_' + cs + '_venv']}/bin/pip3 install {pkg_string}
#2>/dev/null
echo "done"
""",
        {
            "volumes": combine_volumes(
                ro=[dockfill_python.volumes],
                rw=[
                    {
                        dockerator.paths[f"{cs}_venv"]: dockerator.paths[
                            f"docker_{cs}_venv"
                        ]
                    }
                ],
            )
        },
        "log_code_venv_pip",
    )
    installed_now = find_installed_packages(
        dockerator.paths[f"{cs}_venv"], dockerator.major_python_version
    )
    still_missing = set([x["name"] for x in packages]).difference(installed_now)
    if still_missing:
        raise ValueError(
            f"Installation of {cs} packages failed"
            f", check {dockerator.paths['log_' + cs + '_venv_pip']}\nFailed: {still_missing}"
        )
