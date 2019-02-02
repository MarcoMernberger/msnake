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
    with open("project.install") as op:
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
        docker_image = None
    if "bioconductor" in parsed:
        bioconductor_version = parsed["bioconductor_version"]["version"]
        del parsed["bioconductor"]
    else:
        bioconductor_version = None
    if "R" in parsed:
        R_version = parsed["R"]["version"]
        del parsed["R"]
    else:
        R_version = None

    if not docker_image:
        raise ValueError(
            "Must specify docker image to use, e.g. docker_image==ubuntu:18.04"
        )
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
        Path("version_store"),
        Path("local_venv"),
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
        local_venv_path,
    ):

        self.storage_path = Path(storage_path)
        if not self.storage_path.exists():
            raise IOError(f"{self.storage_path} did not exist")
        self.storage_path = storage_path / docker_image.replace(":", "-")
        self.local_venv_path = Path(local_venv_path)
        self.local_venv_path.mkdir(parents=False, exist_ok=True)
        self.docker_image = docker_image
        self.python_version = python_version
        self.bioconductor_version = bioconductor_version
        if self.bioconductor_version:
            if r_version:
                raise ValueError("Must not specify both R and bioconductor version")
            self.R_version = self.find_r_from_bioconductor(bioconductor_version)
        else:
            self.R_version = r_version
        self.global_venv_packages = global_venv_packages
        self.local_venv_packages = local_venv_packages

        if self.R_version is not None and self.R_version < "3.0":
            raise ValueError("Requested an R version that is not rpy2 compatible")

    @property
    def major_python_version(self):
        p = self.python_version
        if p.count(".") == 2:
            return p[: p.rfind(".")]
        elif p.count(".") == 1:
            return p
        else:
            raise ValueError(f"Error parsing {self.python_version} to major version")

    def check_python_version_exists(self):
        version = self.python_version
        r = requests.get("https://www.python.org/doc/versions/").text
        if not f"release/{version}/" in r:
            raise ValueError(
                f"Unknown python version {version} - check https://www.python.org/doc/versions/"
            )

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

    def find_r_from_bioconductor(self):
        # straight copy paste https://bioconductor.org/about/release-announcements/
        raw = """
3.7, 3.8	3.5
3.5, 3.6	3.4
3.3, 3.4	3.3
3.1, 3.2	3.2
2.14, 3.0	3.1
2.12, 2.13	3.0
2.10, 2.11	2.15
2.9	2.14
2.8	2.13
2.7	2.12
2.6	2.11
2.5	2.10
2.4	2.9
2.3	2.8
2.2	2.7
2.1	2.6
2.0	2.5
1.9	2.4
1.8	2.3
1.7	2.2
1.6	2.1
1.5	2.0
1.4	1.9
1.3	1.8
1.2	1.7
1.1	1.6
1.0	1.5"""
        lines = [x.split("\t") for x in raw.split("\n")]
        result = {}
        for bc_versions, r_version in lines:
            for bc_version in bc_versions.split(", "):
                result[bc_version] = r_version
        return result["https://bioconductor.org/about/release-announcements/"]

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
            if isinstance(v, dict):
                volume_args[k] = v
            else:
                volume_args[k] = {"bind": v, "mode": "rw"}
        run_kwargs["volumes"] = volume_args
        pprint.pprint(volume_args)
        tf.write(bash_script)
        tf.flush()
        container_result = client.containers.run(
            docker_image, "/bin/bash /opt/run.sh", **run_kwargs
        )
        if Path("logs").exists():
            (Path("logs") / (log_name + ".stdouterr")).write_bytes(container_result)
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
                    f"Docker build failed. Investigate logs/{log_name}.stdout/stderr"
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
            target_dir=self.storage_path / "python" / self.python_version,
            target_dir_inside_docker="/opt/python",
            relative_check_filename="bin/virtualenv",
            log_name="dockerator.python_build",
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

python-build %s /opt/python
/opt/python/bin/pip install -U pip virtualenv
chown 1001 /opt/python -R 2>/dev/null
echo "done"
"""
            % self.python_version,
        )

    def ensure_global_venv(self):
        self.build(
            target_dir=self.storage_path / "global_venv" / self.python_version,
            target_dir_inside_docker="/opt/global_venv",
            relative_check_filename=Path("bin") / "activate.fish",
            log_name="dockerator.global_venv",
            additional_volumes={
                self.storage_path / "python" / self.python_version: "/opt/python"
            },
            build_cmds="""
/opt/python/bin/virtualenv -p /opt/python/bin/python /opt/global_venv
chown 1001 /opt/global_venv -R 2>/dev/null
echo "done"
""",
        )

    def ensure_local_venv(self):
        self.build(
            target_dir=self.local_venv_path / self.python_version / "venv",
            target_dir_inside_docker="/opt/local_venv",
            relative_check_filename=Path("bin") / "activate.fish",
            log_name="dockerator.local_venv",
            additional_volumes={
                self.storage_path / "python" / self.python_version: "/opt/python",
                # self.storage_path / "global_venv" / self.python_version: '/opt/global_venv,
            },
            build_cmds="""
/opt/python/bin/virtualenv -p /opt/python/bin/python /opt/local_venv
chown 1001 /opt/local_venv -R 2>/dev/null
echo "done"
""",
        )
        pass

    def ensure_r(self):
        #todo: switch to cdn by default / config in file
        r_mirror = "https://ftp.fau.de/cran/src/base/"
        r_url = (
            r_mirror + "R-" + self.R_version[0] + "/R-" + self.R_version + "tar.gz"
        )
        self.build(
            target_dir=self.storage_path / "R" / self.R_version,
            target_dir_inside_docker="/opt/R",
            relative_check_filename="bin/R",
            log_name="dockerator.R",
            additional_volumes={},
            build_cmds=f"""
apt-get update
export DEBIAN_FRONTEND=noninteractive
apt-get install -y tzdata

apt-get install -y libopenblas-dev libcurl4-openssl-dev
apt-get build-dep r-base

cd /root
wget {r_url} -O R.tar.gz
tar xf R.tar.gz
cd R-{self.R_version}
./configure --prefix=/opt/R --enable-R-shlib --with-blas --with-lapack --with-x=no
make
make install

chown 1001 /opt/R -R
echo "done"
""",
        )

    def ensure_correct_rpy(self):
        # TODO: This will probably need fine tuning for combining older Rs and the
        # latest rpy2 version that supported them
        self.build(
            target_dir=self.storage_path
            / "rpy2"
            / f"{self.python_version}_{self.R_version}",
            target_dir_inside_docker="/opt/rpy2_venv",
            relative_check_filename=do_not_know_yet,
            log_name="dockerator.rpy2",
            additional_volumes={
                self.storage_path / "python" / self.python_version: "/opt/python",
                self.storage_path / "R" / self.R_version: "/opt/R",
            },
            build_cmds="""
export R_HOME=/opt/R
export PATH=/opt/R/bin:$PATH 
/opt/python/bin/virtualenv -p /opt/python/bin/python /opt/rpy2_venv
cd /root
/opt/rpy2_venv/bin/pip3 download rpy2
#this might not be enough later on, if rpy2 gains a version that is 
# dependend on something we don't get as a wheel
/opt/rpy2_venv/bin/pip3 install *.whl
tar xf rpy2-*.tar.gz
rm rpy2-*.tar.gz
mv rpy2* rpy2
cd rpy2
python setup.py install

/opt/rpy2_venv/bin/pip install rpy2
touch /opt/rpy2_venv/done
chown 1001 /opt/rpy2_venv -R
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
r["CRAN"] <- "https://cloud.r-project.org"
options(repos=r)

lib = "/opt/bioconductor"
.libPaths(c(lib, .libPaths()))
if (!requireNamespace("BiocManager"))
    install.packages("BiocManager", lib=lib)
BiocManager::install({package_vector}, lib=lib)
write("done", "/opt/bioconductor/done")
echo "done"
"""
        r_build_file = tempfile.NamedTemporaryFile(suffix=".r")
        r_build_file.write(r_build_script)
        r_build_file.flush()

        self.build(
            target_dir=self.storage_path / "bioconductor" / self.bioconductor_version,
            target_dir_inside_docker="/opt/bioconductor",
            relative_check_filename="done",
            log_name="dockerator.bioconductor",
            additional_volumes={
                self.storage_path / "R" / self.R_version: "/opt/R",
                r_build_file.name: "/opt/bioconductor/install.R",
            },
            build_cmds="""
apt-get update
export DEBIAN_FRONTEND=noninteractive
apt-get install -y tzdata

apt-get install -y adduser apt base-files base-passwd bash bsdutils\
 build-essential bzip2\
 ca-certificates coreutils dash debconf debianutils diffutils dpkg e2fsprogs \
 fdisk findutils gcc-8-base gfortran gpgv grep gzip hostname init-system-helpers\
 libacl1 libapt-pkg5.0 libattr1 libaudit-common libaudit1 libblkid1\
 libbz2-1.0 libc-bin libc6 libcap-ng0 libcom-err2 libcurl4-openssl-dev libdb5.3\
 libdebconfclient0 libext2fs2 libfdisk1 libffi6 libgcc1 libgcrypt20 libgmp10\
 libgnutls30 libgpg-error0 libhogweed4 libidn2-0 liblz4-1 liblzma5 libmount1\
 libncurses5 libncursesw5 libnettle6 libopenblas-dev libp11-kit0 libpam-modules\
 libpam-modules-bin libpam-runtime libpam0g libpcre3 libprocps6 libseccomp2\
 libselinux1 libsemanage-common libsemanage1 libsepol1 libsmartcols1 libss2\
 libstdc++6 libsystemd0 libtasn1-6 libtinfo5 libudev1 libunistring2 libuuid1\
 libzstd1 login lsb-base mawk mount ncurses-base ncurses-bin openjdk-8-jdk\
 openjdk-8-jre passwd perl-base procps sed sensible-utils\
 sysvinit-utils tar ubuntu-keyring util-linux vim wget zlib1g
apt-get build-dep r-base

/opt/R/bin/R /opt/bioconductor/install.R

#removing some large datasets that get pulled dependencies
rm /opt/bioconductor/SVM2CRMdata -r
rm /opt/bioconductor/ITALICSData -r
rm /opt/bioconductor/LungCancerACvsSCCGEO -r
rm /opt/bioconductor/mitoODEdata -r
rm /opt/bioconductor/ABAData -r
chown 1001 /opt/bioconductor -R 2>/dev/null
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

    def install_pip_packages(self, venv, storage_path, packages):
        """packages are parse_requirements results with method == 'pip'"""
        for x in packages:
            if x["method"] != "pip":
                raise ValueError("passed not pip packages to install_pip_packages")
        pkg_string = " ".join([self.format_for_pip(x) for x in packages])
        self._run_docker(
            self.docker_image,
            f"""
echo "/opt/{venv}/bin/pip3 install {pkg_string}"
/opt/{venv}/bin/pip3 install {pkg_string}
chown 1000 /opt/{venv} -R
#2>/dev/null
echo "done"
""",
            {
                "volumes": {
                    self.storage_path / "python" / self.python_version: "/opt/python",
                    storage_path: "/opt/" + venv,
                }
            },
            "dockerator." + venv + "_pip",
        )
        installed_now = self.find_installed_packages(storage_path)
        still_missing = set([x["name"] for x in packages]).difference(installed_now)
        if still_missing:
            raise ValueError(
                f"Installation of {venv} packages failed"
                f", check logs/{venv}_pip.*\nFailed: {still_missing}"
            )

    def fill_global_venv(self):
        """Global venv only installs if packages are *missing"""
        print("fill_global_venv")
        parsed_packages = list(self.global_venv_packages.values())
        pip_packages = [x for x in parsed_packages if x["method"] == "pip"]
        non_pip_packages = [x for x in parsed_packages if x["method"] != "pip"]
        if non_pip_packages:
            raise ValueError("the global_venv must receive *only* pypi packages")
        storage_path = self.storage_path / "global_venv" / self.python_version
        installed = self.find_installed_packages(storage_path)
        missing = [x for x in pip_packages if not x["name"] in installed]
        if missing:
            self.install_pip_packages("global_venv", storage_path, missing)

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

        code_dir = self.local_venv_path / self.python_version
        installed_versions = self.find_installed_package_versions(code_dir / "venv")
        installed = set(installed_versions.keys())
        missing_pip = [
            x
            for x in pip_packages
            if x["name"].lower() not in installed
            or not self.version_is_compatible(x, installed_versions[x["name"].lower()])
        ]
        print("missing_pip", missing_pip)
        if missing_pip:
            self.install_pip_packages("local_venv", code_dir / "venv", missing_pip)
        missing_code = [x for x in code_packages if not x["name"] in installed]
        for p in code_packages:
            target_path = code_dir / p["name"]
            if not target_path.exists():
                print("cloning", p["name"])
                if p["method"] == "git":
                    subprocess.check_call(["git", "clone", p["url"], target_path])
                elif p["method"] == "hg":
                    subprocess.check_call(["hg", "clone", p["url"], target_path])
            if not p["name"] in installed:
                print("pip install -e", "/opt/code/" + p["name"])
                self._run_docker(
                    self.docker_image,
                    f"""
/opt/local_venv/bin/pip3 install -U -e /opt/code/{p['name']}
chown 1000 /opt/local_venv -R
echo "done"
""",
                    {
                        "volumes": {
                            self.storage_path
                            / "python"
                            / self.python_version: "/opt/python",
                            code_dir / "venv": "/opt/local_venv",
                            code_dir: "/opt/code",
                        }
                    },
                    f'dockerator.local_venv_{p["name"]}_pip',
                )
        installed_now = self.find_installed_packages(code_dir / "venv")
        still_missing = set([x["name"].lower() for x in missing_code]).difference(installed_now)
        if still_missing:
            raise ValueError(
                "Not all code packages installed. Missing were: %s"
                % (still_missing)
            )


def parse_requirements(req_str):
    """Parse the requirements from a requirements file"""
    lines = req_str.strip().split("\n")
    result = {}
    for line in lines:
        line = line.strip()
        if line.startswith("#"):
            continue
        for sep in ["==", "=>", "<=", ">", "<"]:
            if sep in line:
                a, v = line.split(sep)
                comp = sep
                break
        else:
            if "=" in line:
                raise ValueError("Parsing error, line contained =, did you mean ==")
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
