# -*- coding: future_fstrings -*-
from .util import combine_volumes, find_storage_path_from_other_machine, download_file
import re
from pathlib import Path


class DockFill_Rust:
    def __init__(self, dockerator, rust_versions, cargo_install):
        self.dockerator = dockerator
        self.rust_versions = rust_versions
        for v in rust_versions:
            if v.startswith("nigthly") and not re.match(r"nigthly-\d{4}-\d\d-\d\d", v):
                raise ValueError(
                    "Rust nigthly versions must be dated e.g. nigthly-2019-03-20"
                )
            elif v.startswith("stable"):
                raise ValueError(
                    "stable is auto updating - use a definied version (e.g. 1.30.0) instead"
                )
        self.paths = self.dockerator.paths
        self.paths.update(
            {
                # this does not use the find_storage_path_from_other_machine
                # because rustup will place the binaries in the cargo/bin path
                # but the cargo stuff needs to be per machine because 
                # the downloads happen there.
                "storage_rustup": self.paths['storage'] / 'rustup_home', 
                "docker_storage_rustup": Path("/dockerator/rustup_home"),
                "storage_cargo": self.paths["storage"] / "rust_cargo",
                "docker_storage_cargo": Path("/dockerator/cargo"),
                "log_rust": (self.paths["log_storage"] / f"dockerator.rust.log"),
            }
        )
        self.volumes = {
            self.paths["storage_rustup"]: self.paths["docker_storage_rustup"]
        }
        self.rw_volumes = {
            self.paths["storage_cargo"]: self.paths["docker_storage_cargo"]
        }
        self.env = {
            "RUSTUP_HOME": self.paths["docker_storage_rustup"],
            "CARGO_HOME": self.paths["docker_storage_cargo"],
            "RUSTUP_TOOLCHAIN": self.rust_versions[0],
        }
        self.shell_path = str(self.paths["docker_storage_cargo"] / "bin")

    def pprint(self):
        print(f"  Rust versions={self.rust_versions}")

    def ensure(self):
        self.paths["storage_rustup"].mkdir(exist_ok=True)
        self.paths["storage_cargo"].mkdir(exist_ok=True)
        installed_versions = self.get_installed_rust_versions()
        missing = set(self.rust_versions).difference(installed_versions)
        if missing:
            print("installing rust versions ", missing)
            download_file(
                "https://sh.rustup.rs", self.paths["storage_rustup"] / "rustup.sh"
            )
            env = {
                "RUSTUP_HOME": self.paths["docker_storage_rustup"],
                "CARGO_HOME": self.paths["docker_storage_cargo"],
            }
            cmd = f"""
        sh $RUSTUP_HOME/rustup.sh -y --default-toolchain none
        mkdir -p $RUSTUP_HOME/dockerator
        export PATH=$PATH:$CARGO_HOME/bin
        echo "rustup default {self.rust_versions[0]}"
        rustup default {self.rust_versions[0]}
            """
            for version in self.rust_versions:
                if not version in installed_versions:
                    cmd += f"rustup toolchain install {version} && cargo && touch $RUSTUP_HOME/dockerator/{version}.done\n"
            volumes = {
                self.paths["storage_rustup"]: self.paths["docker_storage_rustup"],
                self.paths["storage_cargo"]: self.paths["docker_storage_cargo"],
            }
            self.dockerator._run_docker(
                cmd, {"volumes": volumes, "environment": env}, "log_rust", root=True
            )
            installed_now = self.get_installed_rust_versions()
            if missing.difference(installed_now):
                raise ValueError(f"rust install failed, check {self.paths['log_rust']}")
            else:
                print("rust install done")
            return True
        return False

    def get_installed_rust_versions(self):
        result = set()
        p = self.paths["storage_rustup"] / "dockerator"
        if p.exists():
            for d in p.glob("*.done"):
                v = d.name[:-5]
                result.add(v)
        return result
