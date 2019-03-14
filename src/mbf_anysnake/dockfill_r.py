# -*- coding: future_fstrings -*-

import re
from pathlib import Path
import requests
from .util import combine_volumes, find_storage_path_from_other_machine


class DockFill_R:
    def __init__(self, dockerator):
        self.dockerator = dockerator
        self.paths = self.dockerator.paths
        self.R_version = self.dockerator.R_version
        self.cran_mirror = self.dockerator.cran_mirror

        self.paths.update(
            {
                "storage_r": find_storage_path_from_other_machine(
                    self.dockerator, Path("R") / self.R_version
                ),
                "docker_storage_r": "/dockerator/R",
                "log_r": self.paths["log_storage"]
                / f"dockerator.R.{self.R_version}.log",
            }
        )
        self.volumes = {self.paths["storage_r"]: self.paths["docker_storage_r"]}
        self.shell_path = str(Path(self.paths["docker_storage_r"]) / "bin")

    def pprint(self):
        print(f"  R version={self.R_version}")

    def check_r_version_exists(self):
        if not re.match(r"\d+\.\d+\.\d", self.R_version):
            raise ValueError(
                "Incomplete R version specified - bust look like e.g 3.5.3"
            )
        url = self.cran_mirror + "src/base/R-" + self.R_version[0]
        r = requests.get(url).text
        if not f"R-{self.R_version}.tar.gz" in r:
            raise ValueError(
                (f"Unknown R version {self.R_version} - check {url} for list")
            )

    def ensure(self):
        # todo: switch to cdn by default / config in file
        r_url = (
            self.dockerator.cran_mirror
            + "src/base/R-"
            + self.dockerator.R_version[0]
            + "/R-"
            + self.dockerator.R_version
            + ".tar.gz"
        )
        return self.dockerator.build(
            target_dir=self.paths["storage_r"],
            target_dir_inside_docker=self.paths["docker_storage_r"],
            relative_check_filename="bin/R",
            log_name=f"log_r",
            additional_volumes={},
            version_check=self.check_r_version_exists(),
            build_cmds=f"""
cd ~
wget {r_url} -O R.tar.gz
tar xf R.tar.gz
cd R-{self.dockerator.R_version}
./configure --prefix={self.paths['docker_storage_r']} --enable-R-shlib --with-blas --with-lapack --with-x=no
make -j {self.dockerator.cores}
make install

echo "done"
""",
        )


class DockFill_Rpy2:
    def __init__(self, dockerator, dockfill_py, dockfill_r):
        self.dockerator = dockerator
        self.paths = self.dockerator.paths
        self.python_version = self.dockerator.python_version
        self.R_version = self.dockerator.R_version
        self.dockfill_python = dockfill_py
        self.dockfill_r = dockfill_r

        self.paths.update(
            {
                "storage_rpy2": (
                    find_storage_path_from_other_machine(
                        self.dockerator,
                        Path("rpy2") / f"{self.python_version}_{self.R_version}",
                    )
                ),
                "docker_storage_rpy2": "/dockerator/rpy2",
                "log_rpy2": self.paths["log_storage"]
                / f"dockerator.rpy2.{self.python_version}-{self.R_version}.log",
            }
        )
        self.volumes = {self.paths["storage_rpy2"]: self.paths["docker_storage_rpy2"]}

    def pprint(self):
        pass

    def ensure(self):
        # TODO: This will probably need fine tuning for combining older Rs and the
        # latest rpy2 version that supported them
        return self.dockerator.build(
            target_dir=self.paths["storage_rpy2"],
            target_dir_inside_docker=self.paths["docker_storage_rpy2"],
            relative_check_filename=f"lib/python{self.dockerator.major_python_version}/site-packages/rpy2/__init__.py",
            log_name=f"log_rpy2",
            additional_volumes=combine_volumes(
                ro=[self.dockfill_python.volumes, self.dockfill_r.volumes]
            ),
            build_cmds=f"""

export R_HOME={self.paths['docker_storage_r']}
export PATH={self.paths['docker_storage_r']}/bin:$PATH
{self.paths['docker_storage_python']}/bin/virtualenv -p {self.paths['docker_storage_python']}/bin/python {self.paths['docker_storage_rpy2']}
cd /root
{self.paths['docker_storage_rpy2']}/bin/pip3 download rpy2
#this might not be enough later on, if rpy2 gains a version that is
# dependend on something we don't get as a wheel
{self.paths['docker_storage_rpy2']}/bin/pip3 install *.whl
tar xf rpy2-*.tar.gz
rm rpy2-*.tar.gz
mv rpy2* rpy2
cd rpy2
python setup.py install

{self.paths['docker_storage_rpy2']}/bin/pip install rpy2
touch {self.paths['docker_storage_rpy2']}/done
chown 1001 {self.paths['docker_storage_rpy2']} -R
echo "done"
""",
        )
