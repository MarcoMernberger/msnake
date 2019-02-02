from pathlib import Path
from docker import from_env as docker_from_env
import tempfile
import shutil
import requests
import subprocess
import re
import pprint
import packaging.version


def main():
    with open("project.setup") as op:
        req_str = op.read()
    parsed = parse_requirements(req_str)
    pprint.pprint(parsed)
    if not "python" in parsed or not parsed["python"]["version"]:
        raise ValueError(
            "Must specify at the very least a python version to use, e.g. python==3.7"
        )
    python_version = parsed["python"]["version"]
    del parsed["python"]
    if "docker_image" in parsed:
        docker_image = parsed["docker_image"]["version"]
        del parsed["docker_image"]
    else:
        docker_image = 'mbf_dockerator:18.04'
    if "bioconductor" in parsed:
        bioconductor_version = parsed["bioconductor"]["version"]
        del parsed["bioconductor"]
    else:
        bioconductor_version = None
    if "R" in parsed:
        R_version = parsed["R"]["version"]
        del parsed["R"]
    else:
        R_version = None

    if 'storage_path' in parsed:
        storage_path = Path(parsed['storage_path']['version'])
        del parsed['storage_path']
    else:
        storage_path = Path("version_store")
    if not storage_path.exists():
        storage_path.mkdir(exist_ok=True)

    if 'code_path' in parsed:
        code_path = Path(parsed['code_path']['version'])
        del parsed['code_path']
    else:
        code_path = Path("code")
    if not code_path.exists():
        code_path.mkdir(exist_ok=True)

    Path("logs").mkdir(parents=False, exist_ok=True)
    d = Dockerator(
        docker_image,
        python_version,
        bioconductor_version,
        R_version,
        parse_requirements(
            """
jupyter
"""
        ),
        parsed,
        storage_path,
        code_path,
        
    )
    d.ensure()


class Dockerator:
    """Wrap ubuntu version (=docker image),
    Python version,
    R version,
    bioconductor version,
    global and local venvs (including 'code')

    bioconductor_version can be set to None, then no bioconductor is installed,
    R_version can be set to None, then no (if bioconductor == None) or the 
        matching R version for the bioconductor is being installed.
    If bioconductor_version is set, R_version must not be set.

    """

    def __init__(
        self,
        docker_image,
        python_version,
        bioconductor_version,
        r_version,
        global_venv_packages,
        local_venv_packages,
        storage_path,
        code_path,
        cores = 8,
        cran_mirror = "https://ftp.fau.de/cran/", # https://cloud.r-project.org
    ):
        self.cores = int(cores)
        self.cran_mirror = cran_mirror

        self.storage_path = Path(storage_path)
        if not self.storage_path.exists():
            raise IOError(f"{self.storage_path} did not exist")
        storage_path = storage_path / docker_image.replace(":", "-")
        code_path = Path(code_path)
        code_path.mkdir(parents=False, exist_ok=True)

        

        self.docker_image = docker_image
        self.python_version = python_version
        self.bioconductor_version = bioconductor_version
        self.paths = {
                'log': Path('logs'),
                }

        if self.bioconductor_version:
            self.paths.update({
                'storage_bioconductor': storage_path / 'bioconductor' / self.bioconductor_version,
                'storage_bioconductor_r_version': storage_path / 'bioconductor_r_version' / self.bioconductor_version,
                'docker_storage_bioconductor': '/dockerator/bioconductor',
                'log_bioconductor': self.paths['log'] / 'dockerator.bioconductor.log',
            })
       
            if not r_version:
                self.R_version = self.find_r_from_bioconductor()
            else:
                self.R_version = r_version
        else:
            self.R_version = r_version
        self.global_venv_packages = global_venv_packages
        self.local_venv_packages = local_venv_packages

        if self.R_version is not None and self.R_version < "3.0":
            raise ValueError("Requested an R version that is not rpy2 compatible")
        self.paths.update({
                'storage': storage_path,
                'code': code_path / self.python_version,
                'code_venv': code_path / self.python_version / 'venv',
                'storage_venv': storage_path / 'venv' / self.python_version,
                'storage_python': storage_path / 'python' / self.python_version,
                'docker_storage_venv': '/dockerator/venv',
                'docker_storage_python': '/dockerator/python',
                'docker_code': '/dockerator/code',
                'docker_code_venv': '/dockerator/venv',

                'log_python': self.paths['log'] / 'dockerator.python.log',
                'log_storage_venv': self.paths['log'] / 'dockerator.storage_venv.log',
                'log_storage_venv_pip': self.paths['log'] / 'dockerator.storage_venv_pip.log',
                'log_code_venv': self.paths['log'] / 'dockerator.code_venv.log',
                'log_code_venv_pip': self.paths['log'] / 'dockerator.code_venv_pip.log',
                })
        if self.R_version is not None:
            self.paths.update({
                'storage_r': storage_path / 'R' / self.R_version,
                'storage_rpy2': storage_path / 'rpy2' / f"{self.python_version}_{self.R_version}",
                'docker_storage_r': '/dockerator/R',
                'docker_storage_rpy2': '/dockerator/rpy2',
                'log_r': self.paths['log'] / 'dockerator.R.log',
                'log_rpy2': self.paths['log'] / 'dockerator.rpy2.log',
                })
         
        for k, v in self.paths.items():
            self.paths[k] = Path(v)


    @property
    def major_python_version(self):
        p = self.python_version
        if p.count(".") == 2:
            return p[: p.rfind(".")]
        elif p.count(".") == 1:
            return p
        else:
            raise ValueError(f"Error parsing {self.python_version} to major version")

    def check_r_version_exists(self):
        if not re.match(r'\d+\.\d+\.\d', self.R_version):
            raise ValueError("Incomplete R version specified - bust look like e.g 3.5.3")
        url = self.cran_mirror + 'src/base/R-' + self.R_version[0]
        r = requests.get(url).text
        if not f'R-{self.R_version}.tar.gz' in r:
            raise ValueError(f("Unknown R version {self.R_version - check {url} for list"))


    def check_python_version_exists(self):
        version = self.python_version
        r = requests.get("https://www.python.org/doc/versions/").text
        if not f"release/{version}/" in r:
            raise ValueError(
                f"Unknown python version {version} - check https://www.python.org/doc/versions/"
            )

    def check_r_bioconductor_match(self):
        pairs = self.get_bioconductor_r_pairs()
        major = pairs[self.bioconductor_version]
        if not self.R_version.startswith(major):
            raise ValueError(f"bioconductor {self.bioconductor_version} requires R {major}.*, but you requested {self.R_version}")


    def ensure(self):
        self.ensure_python()
        self.ensure_global_venv()
        self.ensure_local_venv()
        self.fill_global_venv()
        self.fill_local_venv()

        if self.R_version:
            self.ensure_r()
            self.ensure_correct_rpy()
        if self.bioconductor_version:
            self.ensure_bioconductor()

    def run(self, bash_cmds):
        pass

    def get_bioconductor_r_pairs(self):
        pairs = {}
        url = 'https://bioconductor.org/about/release-announcements/'
        bc = requests.get(url).text
        tbody = bc[bc.find("<tbody>"):bc.find("</tbody>")] # at least for now it's the first table on the page
        for block in tbody.split("</tr>"):
            bc_versions = re.findall(r"/packages/(\d+.\d+)/", block)
            if bc_versions:
                r_version = re.findall(r">(\d+\.\d+)</td>", block)
                if len(r_version) != 1:
                    raise ValueError("Failed to parse bioconductor -> R listing from website, check screen scrapping code")
                r_version = r_version[0]
                for b in bc_versions:
                    pairs[b] = r_version
        return pairs

    def find_r_from_bioconductor(self):
        cache_file =(self.paths['storage_bioconductor_r_version']) 
        if not cache_file.exists():
            cache_file.parent.mkdir(exist_ok=True, parents=True)
            pairs = self.get_bioconductor_r_pairs()
            if not self.bioconductor_version in pairs:
                raise ValueError(f"Could not find bioconductor {version} - check {url}")
            major = pairs[self.bioconductor_version]
            # chosen = major + '.0'
            if True:
                # this is very nice, but simply wrong - 3.8 does not work with R 3.5.2 e.g.
                #now we now 3.x - but we don't know 3.x.y
                url = self.cran_mirror + 'src/base/R-' + major[0]
                r = requests.get(url).text
                available = re.findall("R-(" + major + r"\.\d+).tar.gz", r)
                matching = [x for x in available if x.startswith(major)]
                by_minor = [(re.findall(r"\d+.\d+.(\d+)", x), x) for x in matching]
                by_minor.sort()
                chosen = by_minor[-1][1]
            cache_file.write_text(chosen)
        return cache_file.read_text()
        
    def _run_docker(self, docker_image, bash_script, run_kwargs, log_name):
        run_kwargs["stdout"] = True
        run_kwargs["stderr"] = True
        client = docker_from_env()
        tf = tempfile.NamedTemporaryFile(mode="w")
        volumes = {tf.name: "/opt/run.sh"}
        volumes.update(run_kwargs["volumes"])
        volume_args = {}
        for k, v in volumes.items():
            k = str(Path(k).absolute())
            if isinstance(v, tuple):
                volume_args[k] = {"bind": str(v[0]), "mode": v[1]}
            else:
                volume_args[k] = {"bind": str(v), "mode": "rw"}
        run_kwargs["volumes"] = volume_args
        tf.write(bash_script)
        tf.flush()
        container_result = client.containers.run(
            docker_image, "/bin/bash /opt/run.sh", **run_kwargs
        )
        if Path("logs").exists():
            self.paths[log_name].write_bytes(container_result)
        return container_result

    def build(
        self,
        *,
        target_dir,
        target_dir_inside_docker,
        relative_check_filename,
        log_name,
        build_cmds,
        environment=None,
        additional_volumes=None,
        version_check=None,
    ):
        target_dir = target_dir.absolute()
        if not target_dir.exists():
            if version_check is not None:
                version_check()
            print("Building", log_name)
            build_dir = target_dir.with_name(target_dir.name + "_temp")
            if build_dir.exists():
                shutil.rmtree(build_dir)
            build_dir.mkdir(parents=True)
            volumes = {build_dir: target_dir_inside_docker}
            if additional_volumes:
                volumes.update(additional_volumes)
            container_result = self._run_docker(
                self.docker_image,
                build_cmds,
                {"volumes": volumes, "environment": environment},
                log_name,
            )

            if not (Path(build_dir) / relative_check_filename).exists():
                if Path("logs").exists():
                    pass  # written in _run_docker
                else:
                    print("container stdout/stderr", container_result)
                raise ValueError(
                    "Docker build failed. Investigate " + str(self.paths[log_name])
                )
            else:
                # un-atomic copy (across device borders!), atomic rename -> safe
                build_dir.rename(target_dir)

    def ensure_python(self):
        # python beyond these versions needs libssl 1.1
        # the older ones need libssl1.0
        # on older debians/ubuntus that would be libssl-dev
        # but on 18.04+ it's libssl1.0-dev
        # and we're not anticipating building on something older
        if (
            (self.python_version >= "3.5.3")
            or (self.python_version >= "3.6.0")
            or (self.python_version >= "2.7.13")
        ):
            ssl_lib = "libssl-dev"
        else:
            ssl_lib = "libssl1.0-dev"

        self.build(
            target_dir=self.paths['storage_python'],
            target_dir_inside_docker=self.paths['docker_storage_python'],
            relative_check_filename="bin/virtualenv",
            log_name="log_python",
            additional_volumes={},
            version_check=self.check_python_version_exists(),
            build_cmds=f"""
#/bin/bash
apt-get update
cd /root
git clone git://github.com/pyenv/pyenv.git
cd pyenv/plugins/python-build
./install.sh

apt-get install -y {ssl_lib} zlib1g-dev\
 libbz2-dev libreadline-dev libsqlite3-dev \
 libncurses5-dev  tk-dev libxml2-dev libxmlsec1-dev\
 libffi-dev liblzma-dev

python-build %s {self.paths['docker_storage_python']}
{self.paths['docker_storage_python']}/bin/pip install -U pip virtualenv
chown 1001 {self.paths['docker_storage_python']} -R 2>/dev/null
echo "done"
"""
            % self.python_version,
        )

    def ensure_global_venv(self):
        self.build(
            target_dir=self.paths['storage_venv'],
            target_dir_inside_docker=self.paths['docker_storage_venv'],
            relative_check_filename=Path("bin") / "activate.fish",
            log_name="log_storage_venv",
            additional_volumes={
                self.paths['storage_python']: (self.paths['docker_storage_python'], 'ro')
            },
            build_cmds=f"""
{self.paths['docker_storage_python']}/bin/virtualenv -p {self.paths['docker_storage_python']}/bin/python {self.paths['docker_storage_venv']}
chown 1001 {self.paths['docker_storage_venv']} -R 2>/dev/null
echo "done"
""",
        )

    def ensure_local_venv(self):
        self.build(
            target_dir=self.paths['code_venv'],
            target_dir_inside_docker=self.paths['docker_code_venv'],
            relative_check_filename=Path("bin") / "activate.fish",
            log_name="log_code_venv",
            additional_volumes={
                self.paths['storage_python']: (self.paths['docker_storage_python'], 'ro')
            },
            build_cmds=f"""
{self.paths['docker_storage_python']}/bin/virtualenv -p {self.paths['docker_storage_python']}/bin/python {self.paths['docker_code_venv']}
chown 1001 {self.paths['docker_code_venv']} -R 2>/dev/null
echo "done"
""",
        )
        pass

    def ensure_r(self):
        #todo: switch to cdn by default / config in file
        r_url = (
            self.cran_mirror + "src/base/R-" + self.R_version[0] + "/R-" + self.R_version + ".tar.gz"
        )
        self.build(
            target_dir=self.paths['storage_r'],
            target_dir_inside_docker=self.paths['docker_storage_r'],
            relative_check_filename="bin/R",
            log_name="log_r",
            additional_volumes={},
            version_check=self.check_r_version_exists(),
            build_cmds=f"""
export DEBIAN_FRONTEND=noninteractive

apt-get install -y libopenblas-dev libcurl4-openssl-dev
apt-get build-dep -y r-base

cd /root
wget {r_url} -O R.tar.gz
tar xf R.tar.gz
cd R-{self.R_version}
./configure --prefix={self.paths['docker_storage_r']} --enable-R-shlib --with-blas --with-lapack --with-x=no
make -j {self.cores}
make install

chown 1001 {self.paths['docker_storage_r']} -R
echo "done"
""",
        )

    def ensure_correct_rpy(self):
        # TODO: This will probably need fine tuning for combining older Rs and the
        # latest rpy2 version that supported them
        self.build(
            target_dir=self.paths['storage_rpy2']
            ,
            target_dir_inside_docker=self.paths['docker_storage_rpy2'],
            relative_check_filename=f"lib/python{self.major_python_version}/site-packages/rpy2/__init__.py",
            log_name="log_rpy2",
            additional_volumes={
                self.paths['storage_python']: (self.paths['docker_storage_python'], 'ro'),
                self.paths['storage_r']: (self.paths['docker_storage_r'], 'ro')
            },
            build_cmds=f"""
apt-get install -y libopenblas-dev libcurl4-openssl-dev
apt-get build-dep -y r-base

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

    def ensure_bioconductor(self):
        r = requests.get(
            f"https://www.bioconductor.org/packages/{self.bioconductor_version}/bioc/"
        ).text
        # we can not use BiocManager::available
        # for that also lists >15k data packages...
        # that we do not want

        packages = re.findall('href="html/(.+).html"', r)
        package_vector = "c(" + ", ".join([f'"{x}"' for x in packages]) + ")"
        r_build_script = f"""
r <- getOption("repos")
r["CRAN"] <- "{self.cran_mirror}"
options(repos=r)

lib = "{self.paths['docker_storage_bioconductor']}"
.libPaths(c(lib, .libPaths()))
if (!requireNamespace("BiocManager"))
    install.packages("BiocManager", lib=lib)
BiocManager::install({package_vector}, lib=lib, Ncpus={self.cores})
write("done", "{self.paths['docker_storage_bioconductor']}/done")
echo "done"
"""
        r_build_file = tempfile.NamedTemporaryFile(suffix=".r", mode='w')
        r_build_file.write(r_build_script)
        r_build_file.flush()

        self.build(
            target_dir=self.paths['storage_bioconductor'],
            target_dir_inside_docker=self.paths['docker_storage_bioconductor'],
            relative_check_filename="done",
            log_name="log_bioconductor",
            version_check=self.check_r_bioconductor_match(),
            additional_volumes={
                self.paths['storage_r']: (self.paths['docker_storage_r'], 'ro'),
                r_build_file.name: "/opt/install.R",
            },
            build_cmds=f"""
export DEBIAN_FRONTEND=noninteractive

{self.paths['docker_storage_r']}/bin/R --no-save </opt/install.R 

#removing some large datasets that get pulled dependencies
rm {self.paths['docker_storage_bioconductor']}/SVM2CRMdata -r
rm {self.paths['docker_storage_bioconductor']}/ITALICSData -r
rm {self.paths['docker_storage_bioconductor']}/LungCancerACvsSCCGEO -r
rm {self.paths['docker_storage_bioconductor']}/mitoODEdata -r
rm {self.paths['docker_storage_bioconductor']}/ABAData -r
chown 1001 {self.paths['docker_storage_bioconductor']} 2>/dev/null
echo "done"
""",
        )

    def find_installed_packages(self, venv_dir):
        return list(self.find_installed_package_versions(venv_dir).keys())

    def find_installed_package_versions(self, venv_dir):
        venv_dir = (
            venv_dir / "lib" / ("python" + self.major_python_version) / "site-packages"
        )
        print("looking for packages in ", venv_dir)
        result = {}
        for p in venv_dir.glob("*"):
            if p.name.endswith(".dist-info"):
                name = p.name[: p.name.rfind("-", 0, -5)]
                version = p.name[p.name.rfind("-", 0, -5) + 1 : -1 * len(".dist-info")]
                result[name.lower()] = version
            elif p.name.endswith('.egg-link'):
                name = p.name[:-1 * len('.egg-link')]
                version = 'unknown'
                result[name.lower()] = version
        return result

    def format_for_pip(self, parse_result):
        res = parse_result["name"]
        if parse_result["comp"]:
            res += parse_result["comp"]
            res += parse_result["version"]
        return f'"{res}"'

    def install_pip_packages(self, cs, packages):
        """packages are parse_requirements results with method == 'pip'"""
        for x in packages:
            if x["method"] != "pip":
                raise ValueError("passed not pip packages to install_pip_packages")
        pkg_string = " ".join([self.format_for_pip(x) for x in packages])

        self._run_docker(
            self.docker_image,
            f"""
{self.paths['docker_' + cs + '_venv']}/bin/pip3 install {pkg_string}
chown 1000 {self.paths['docker_' + cs + '_venv']} -R
#2>/dev/null
echo "done"
""",
            {
                "volumes": {
                    self.paths['storage_python']: (self.paths['docker_storage_python'], 'ro'),
                    self.paths[f'{cs}_venv']: self.paths[f'docker_{cs}_venv']
                }
            },
            'log_code_venv_pip',
        )
        installed_now = self.find_installed_packages(self.paths[f'{cs}_venv'])
        still_missing = set([x["name"] for x in packages]).difference(installed_now)
        if still_missing:
            raise ValueError(
                f"Installation of {cs} packages failed"
                f", check {self.paths['log_' + cs + '_venv_pip']}\nFailed: {still_missing}"
            )

    def fill_global_venv(self):
        """Global venv only installs if packages are *missing"""
        print("fill_global_venv")
        parsed_packages = list(self.global_venv_packages.values())
        pip_packages = [x for x in parsed_packages if x["method"] == "pip"]
        non_pip_packages = [x for x in parsed_packages if x["method"] != "pip"]
        if non_pip_packages:
            raise ValueError("the global_venv must receive *only* pypi packages")
        installed = self.find_installed_packages(self.paths['storage_venv'])
        missing = [x for x in pip_packages if not x["name"] in installed]
        if missing:
            self.install_pip_packages("storage", missing)

    def version_is_compatible(self, parsed_req, version):
        if not parsed_req["comp"]:
            return True
        actual_ver = packaging.version.parse(version)
        if "," in parsed_req["version"]:
            raise NotImplementedError("Currently does not handle version>=x,<=y")
        should_ver = packaging.version.parse(parsed_req["version"])
        if parsed_req["comp"] == ">":
            return actual_ver > should_ver
        elif parsed_req["comp"] == ">=":
            return actual_ver >= should_ver
        elif parsed_req["comp"] == "<=":
            return actual_ver <= should_ver
        elif parsed_req["comp"] == "<":
            return actual_ver < should_ver
        elif parsed_req["comp"] == "==":
            return actual_ver == should_ver
        else:
            raise NotImplementedError("forget to handle a case?", parsed_req, version)

    def fill_local_venv(self):
        print("fill_local_venv")
        parsed_packages = list(self.local_venv_packages.values())
        pip_packages = [x for x in parsed_packages if x["method"] == "pip"]
        code_packages = [x for x in parsed_packages if x["method"] in ("git", "hg")]

        installed_versions = self.find_installed_package_versions(self.paths['code_venv'])
        installed = set(installed_versions.keys())
        missing_pip = [
            x
            for x in pip_packages
            if x["name"].lower() not in installed
            or not self.version_is_compatible(x, installed_versions[x["name"].lower()])
        ]
        print("missing_pip", missing_pip)
        if missing_pip:
            self.install_pip_packages("code", missing_pip)
        missing_code = [x for x in code_packages if not x["name"] in installed]
        for p in code_packages:
            target_path = self.paths['code'] / p["name"]
            if not target_path.exists():
                print("cloning", p["name"])
                if p["method"] == "git":
                    subprocess.check_call(["git", "clone", p["url"], target_path])
                elif p["method"] == "hg":
                    subprocess.check_call(["hg", "clone", p["url"], target_path])
            if not p["name"] in installed:
                print("pip install -e", "/opt/code/" + p["name"])
                self.paths[f'log_code_venv_{p["name"]}'] = self.paths['log'] / f'dockerator.code_venv{p["name"]}.log'
                self._run_docker(
                    self.docker_image,
                    f"""
echo {self.paths['docker_code_venv']}/bin/pip3 install -U -e {self.paths['docker_code']}/{p['name']}
{self.paths['docker_code_venv']}/bin/pip3 install -U -e {self.paths['docker_code']}/{p['name']}
chown 1000 {self.paths['docker_code_venv']} -R
echo "done2"
""",
                    {
                        "volumes": {
                            self.paths['storage_python']: (self.paths['docker_storage_python'], 'ro'),
                            self.paths['code']: self.paths['docker_code'],
                            self.paths['code_venv']: self.paths['docker_code_venv'],
                        }
                    },
                    f'log_code_venv_{p["name"]}',
                )
        installed_now = self.find_installed_packages(self.paths['code_venv'])
        still_missing = set([x["name"].lower() for x in missing_code]).difference(installed_now)
        if still_missing:
            raise ValueError(
                "Not all code packages installed. Missing were: %s"
                % (still_missing)
            )


def parse_requirements(req_str):
    """Parse the requirements from a project.setup file"""
    lines = req_str.strip().split("\n")
    result = {}
    for line_no, line in enumerate(lines):
        line = line.strip()
        if line.startswith("#") or not line:
            continue
        if "=<" in line:
                raise ValueError("Parsing error, line contained =<, did you mean <=, line %i, was '%s'" % (line_no+1, line))
    
        for sep in ["==", "=>", "<=", ">", "<"]:
            if sep in line:
                a, v = line.split(sep)
                comp = sep
                break
        else:
            if "=" in line:
                raise ValueError("Parsing error, line contained =, did you mean ==, line %i, was '%s'" % (line_no+1, line))
            
            a = line
            v = ""
            comp = ""
        a = a.strip()
        v = v.strip()

        if "https://" in a:
            if "git" in a:
                method = "git"
                url = a
                name = a[a.rfind("/") + 1 :]
                if name.endswith(".git"):
                    name = name[: len(".git")]
            else:
                method = "hg"
                url = a
                name = url[url.rfind("/") + 1 :]
        elif a.count("/") == 1:
            method = "git"
            name = a[a.rfind("/") + 1 :]
            url = "https://github.com/" + a
        else:
            name = a
            url = ""
            if name in ("python", "bioconductor", "R"):
                method = "special"
            else:
                method = "pip"
        entry = {"name": name, "method": method, "version": v, "comp": comp, "url": url}
        print(line, entry)
        if entry["name"] in result:
            raise ValueError(f"Repeated definition for {entry['name']}")
        result[entry["name"]] = entry
    return result


if __name__ == "__main__":
    main()
