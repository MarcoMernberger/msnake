import re
import tempfile
import requests
from .util import combine_volumes


class DockFill_R:
    def __init__(self, dockerator):
        self.dockerator = dockerator
        self.paths = self.dockerator.paths
        self.R_version = self.dockerator.R_version
        self.cran_mirror = self.dockerator.cran_mirror

        self.paths.update(
            {
                "storage_r": self.paths["storage"] / "R" / self.R_version,
                "docker_storage_r": "/dockerator/R",
                "log_r": self.paths["log_storage"] / "dockerator.R.log",
                "code_r_venv": self.paths["code"] / "cran" / self.R_version,
                "docker_code_r_venv": "/dockerator/r_venv",
            }
        )
        self.volumes = {self.paths["storage_r"]: self.paths["docker_storage_r"]}

    def check_r_version_exists(self):
        if not re.match(r"\d+\.\d+\.\d", self.R_version):
            raise ValueError(
                "Incomplete R version specified - bust look like e.g 3.5.3"
            )
        url = self.cran_mirror + "src/base/R-" + self.R_version[0]
        r = requests.get(url).text
        if not f"R-{self.R_version}.tar.gz" in r:
            raise ValueError(
                f("Unknown R version {self.R_version - check {url} for list")
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
        self.dockerator.build(
            target_dir=self.paths["storage_r"],
            target_dir_inside_docker=self.paths["docker_storage_r"],
            relative_check_filename="bin/R",
            log_name="log_r",
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
        self.dockfill_py = dockfill_py
        self.dockfill_r = dockfill_r

        self.paths.update(
            {
                "storage_rpy2": (
                    self.paths["storage"]
                    / "rpy2"
                    / f"{self.python_version}_{self.R_version}"
                ),
                "docker_storage_rpy2": "/dockerator/rpy2",
                "log_rpy2": self.paths["log_storage"] / "dockerator.rpy2.log",
            }
        )
        self.volumes = {self.paths["storage_rpy2"]: self.paths["docker_storage_rpy2"]}

    def ensure(self):
        # TODO: This will probably need fine tuning for combining older Rs and the
        # latest rpy2 version that supported them
        self.dockerator.build(
            target_dir=self.paths["storage_rpy2"],
            target_dir_inside_docker=self.paths["docker_storage_rpy2"],
            relative_check_filename=f"lib/python{self.major_python_version}/site-packages/rpy2/__init__.py",
            log_name="log_rpy2",
            additional_volumes=combine_volumes(
                "ro", self.dockfill_python.volumes, self.dockfill_r.volumes
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


class DockFill_CRAN:
    def __init__(self, dockerator, dockfill_r):
        self.dockerator = dockerator
        self.paths = self.dockerator.paths
        self.cran_mirror = self.dockerator.cran_mirror
        self.dockfill_r = dockfill_r

    def ensure(self):
        return
        parsed_packages = list(self.local_venv_packages.values())
        installed = []
        cran_packages = [x for x in parsed_packages if x["method"] == "cran"]
        missing = set(cran_packages) - set(installed)
        if missing:
            r_script = """
lib = "{self.paths['docker_code_r_venv']}"
.libPaths(c(lib, .libPaths()))
if (!requireNamespace("versions"))
    install.packages("versions", lib=lib, Ncpus={self.dockerator.cores})
    """
            for name in missing:
                if entry['version']:
                    r_script += f"install.versions('{entry['name']}','{entry['version']}', lib=lib, Ncpus{self.dockerator.cores})\n"
                else:
                    r_script += f"install.packages('{entry['name']}','{entry['version']}', lib=lib, Ncpus{self.dockerator.cores})\n"


            r_build_file = tempfile.NamedTemporaryFile(suffix=".r", mode="w")
            r_build_file.write(r_build_script)
            r_build_file.flush()

            self._run_docker(
                """{self.paths['docker_storage_r']}/bin/R --no-save < /opt/install.R
                    """,
                volumes=combine_volumes(ro = [self.dockfill_r.volumes],
                                        rw = [
                {
                    self.paths["code_r_venv"]: self.paths["docker_code_r_venv"],
                    r_build_file.name: "/opt/install.R",
                }],
                )
            )
