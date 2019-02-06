# *- coding: future_fstrings -*-

import requests
import time
import shutil
from pathlib import Path
import tempfile
import re

from .util import combine_volumes


def chunks(iter, n):
    # For item i in a range that is a length of l,
    col = []
    for i in iter:
        col.append(i)
        if len(col) == n:
            yield col
            col = []
    if col:
        yield col


class DockFill_Bioconductor:
    def __init__(self, dockerator, dockfill_r):
        self.dockerator = dockerator
        self.dockfill_r = dockfill_r
        self.paths = self.dockerator.paths
        self.bioconductor_version = dockerator.bioconductor_version
        self.paths.update(
            {
                "storage_bioconductor": (
                    self.paths["storage"] / "bioconductor" / self.bioconductor_version
                ),
                "docker_storage_bioconductor": "/dockerator/bioconductor",
                "storage_bioconductor_download": (
                    self.paths["storage"]
                    / "bioconductor_download"
                    / self.bioconductor_version
                ),
                "docker_storage_bioconductor_download": (
                    str(
                        Path("/dockerator/bioconductor_download")
                        / self.bioconductor_version
                    )
                ),
                "log_bioconductor": (
                    self.paths["log_storage"]
                    / f"dockerator.bioconductor.{self.bioconductor_version}.log"
                ),
                "log_bioconductor.todo": (
                    self.paths["log_storage"]
                    / f"dockerator.bioconductor.{self.bioconductor_version}.todo.log"
                ),
            }
        )
        self.volumes = {
            self.paths["storage_bioconductor"]: self.paths[
                "docker_storage_bioconductor"
            ]
        }

    def pprint(self):
        print(f"  Bioconductor version={self.bioconductor_version}")

    @staticmethod
    def fetch_bioconductor_release_information():
        import maya

        url = "https://bioconductor.org/about/release-announcements/"
        bc = requests.get(url).text
        tbody = bc[
            bc.find("<tbody>") : bc.find("</tbody>")
        ]  # at least for now it's the first table on the page
        if not ">3.8<" in tbody:
            raise ValueError(
                "Bioconductor relase page layout changed - update fetch_bioconductor_release_information()"
            )
        info = {}
        for block in tbody.split("</tr>"):
            bc_versions = re.findall(r"/packages/(\d+.\d+)/", block)
            if bc_versions:
                r_version = re.findall(r">(\d+\.\d+)</td>", block)
                if len(r_version) != 1:
                    raise ValueError(
                        "Failed to parse bioconductor -> R listing from website, check screen scrapping code"
                    )
                r_version = r_version[0]
                for b in bc_versions:
                    if b in info:
                        raise ValueError(
                            "Unexpected double information for bc relase %s? Check scraping code"
                            % bc
                        )
                    info[b] = {"r_major_version": r_version}

        if not '"release-announcements"' in bc:
            raise ValueError(
                "Bioconductor relase page layout changed - update fetch_bioconductor_release_information()"
            )
        ra_offset = bc.find("release-announcements")
        tbody = bc[bc.find("<tbody>", ra_offset) : bc.find("</tbody>", ra_offset)]
        for block in tbody.split("</tr>"):
            if not "href" in block:  # old relases no longer available
                continue
            release = re.findall(r">(\d+\.\d+)<", block)
            if len(release) != 1:
                raise ValueError(
                    "Bioconductor relase page layout changed - update fetch_bioconductor_release_information()"
                )
            pckg_count = re.findall(r">(\d+)<", block)
            if len(pckg_count) != 1:
                raise ValueError(
                    "Bioconductor relase page layout changed - update fetch_bioconductor_release_information()"
                )
            date = re.findall(r">([A-Z][a-z]+[0-9 ,]+)<", block)
            if len(date) != 1:
                raise ValueError(
                    "Bioconductor relase page layout changed - update fetch_bioconductor_release_information()"
                )
            release = release[0]
            pckg_count = pckg_count[0]
            date = maya.parse(date[0])
            date = date.rfc3339()
            date = date[: date.find("T")]
            info[release]["date"] = date
            info[release]["pckg_count"] = pckg_count
        return info

    @classmethod
    def bioconductor_relase_information(cls, dockerator):
        """Fetch the information, annotate it with a viable minor release,
        and cache the results.

        Sideeffect: inside one storeage, R does not get minor releases
        with out a change in Bioconductor Version.

        Guess you can overwrite R_version in your configuration file.
        """
        import tomlkit

        dockerator.paths.update(
            {
                "storage_bioconductor_release_info": (
                    dockerator.paths["storage"]
                    / "bioconductor_release_info"
                    / dockerator.bioconductor_version
                )
            }
        )
        cache_file = dockerator.paths["storage_bioconductor_release_info"]
        if not cache_file.exists():
            cache_file.parent.mkdir(exist_ok=True, parents=True)
            all_info = cls.fetch_bioconductor_release_information()
            if not dockerator.bioconductor_version in all_info:
                raise ValueError(
                    f"Could not find bioconductor {dockerator.bioconductor_version } - check https://bioconductor.org/about/release-announcements/"
                )
            info = all_info[dockerator.bioconductor_version]
            major = info["r_major_version"]
            url = dockerator.cran_mirror + "src/base/R-" + major[0]
            r = requests.get(url).text
            available = re.findall("R-(" + major + r"\.\d+).tar.gz", r)
            matching = [x for x in available if x.startswith(major)]
            by_minor = [(re.findall(r"\d+.\d+.(\d+)", x), x) for x in matching]
            by_minor.sort()
            chosen = by_minor[-1][1]
            info["r_version"] = chosen
            cache_file.write_text(tomlkit.dumps(info))
        raw = cache_file.read_text()
        return tomlkit.loads(raw)

    @classmethod
    def find_r_from_bioconductor(cls, dockerator):
        return cls.bioconductor_relase_information(dockerator)["r_version"]

    def check_r_bioconductor_match(self):
        info = self.get_bioconductor_release_information()
        major = info["r_major_version"]
        if not self.dockerator.R_version.startswith(major):
            raise ValueError(
                f"bioconductor {self.bioconductor_version} requires R {major}.*, but you requested {self.R_version}"
            )

    def ensure(self):
        done_file = self.paths["storage_bioconductor"] / "done.txt"
        if not done_file.exists():
            info = self.bioconductor_relase_information(self.dockerator)
            # bioconductor can really only be reliably installed with the CRAN
            # packages against which it was developed
            # arguably, that's an illdefined problem
            # but we'll go with "should've worked at the release date at least"
            # for now
            # Microsoft's snapshotted cran mirror to the rescue

            mran_url = f"https://cran.microsoft.com/snapshot/{info['date']}/"

            urls = {
                "software": f"https://bioconductor.org/packages/{self.bioconductor_version}/bioc/",
                "annotation": f"https://bioconductor.org/packages/{self.bioconductor_version}/data/annotation/",
                "experiment": f"https://bioconductor.org/packages/{self.bioconductor_version}/data/experiment/",
                "cran": mran_url,
            }
            for k in urls:
                (self.paths["storage_bioconductor_download"] / k).mkdir(exist_ok=True)
            pkg_info = {
                k: RPackageInfo(urls[k], k, self.paths["storage_bioconductor"]).get()
                for k in urls
            }
            dep_fields = ["depends", "imports"]

            packages_to_fetch = set(pkg_info["software"].keys())
            all_packages = set.union(*[set(info.keys()) for info in pkg_info.values()])
            all_deps = self.get_dependencies(all_packages, pkg_info, dep_fields)
            packages_to_fetch = self.expand_dependencies(packages_to_fetch, all_deps)
            # packages_to_fetch now dict of name -> dependencies
            data_packages = set(
                pkg_info["annotation"].keys() | pkg_info["experiment"].keys()
            )
            packages_needing_pruning = {
                pkg: deps.intersection(data_packages)
                for (pkg, deps) in packages_to_fetch.items()
                if deps.intersection(data_packages)
            }
            print("no. Packages that might need pruning", len(packages_needing_pruning))

            installed = self.list_installed()
            # packages to fetch now set again

            fetch_order = self.apply_topological_order(
                sorted(packages_to_fetch), all_deps
            )
            fetch_order = [x for x in fetch_order if x not in installed][::-1]

            order_plus_info = [
                (pkg, self.find_info(pkg_info, pkg)) for pkg in fetch_order
            ]
            (self.paths["storage_bioconductor"] / "order").write_text(
                "\n".join([x[0] for x in order_plus_info])
            )
            self.download_packages(order_plus_info)
            self.install_packages(order_plus_info)

    def find_info(self, pkg_info, pkg):
        for i in pkg_info.values():
            if pkg in i:
                return i[pkg]
        raise KeyError(pkg)

    def get_dependencies(self, packages, pkg_info, dep_fields):
        result = {}
        for p in packages:
            for i in pkg_info.values():
                if p in i:
                    result[p] = set()
                    for f in dep_fields:
                        result[p].update(i[p][f])
        return result

    def expand_dependencies(self, packages, all_dependencies):
        deps = {}
        stack = list(packages)
        while stack:
            pkg = stack.pop()
            pkg_deps = all_dependencies[pkg]
            deps[pkg] = pkg_deps
            for d in pkg_deps:
                if not d in deps:
                    stack.append(d)
        return deps

    def apply_topological_order(self, packages, all_dependencies):
        class Node:
            def __init__(self, name):
                self.name = name
                self.prerequisites = []
                self.dependants = []

            def depends_on(self, other_node):
                self.prerequisites.append(other_node)
                other_node.dependants.append(self)

        nodes_by_name = {}
        for n in packages:
            nodes_by_name[n] = Node(n)
        for n in packages:
            deps = all_dependencies[n]
            for d in sorted(deps):
                try:
                    nodes_by_name[n].depends_on(nodes_by_name[d])
                except KeyError:
                    print(n, d)
                    raise ValueError()

        for ii, job in enumerate(nodes_by_name.values()):
            job.dependants_copy = job.dependants.copy()
        list_of_jobs = list(nodes_by_name.values())

        L = []
        S = [job for job in list_of_jobs if len(job.dependants_copy) == 0]
        S.sort(key=lambda job: job.prio if hasattr(job, "prio") else 0)
        while S:
            n = S.pop()
            L.append(n)
            for m in n.prerequisites:
                m.dependants_copy.remove(n)
                if not m.dependants_copy:
                    S.append(m)
        return [n.name for n in L]

    def download_packages(self, pkg_plus_info):
        for pkg, info in pkg_plus_info:
            fn = (
                self.paths["storage_bioconductor_download"]
                / info["repo"]
                / f"{pkg}_{info['version']}.tar.gz"
            )
            download_file(info["url"], fn)

    def install_packages(self, packages):
        count = 0
        chunk_size = self.dockerator.cores * 2
        for sub in chunks(packages, chunk_size):
            print("installing bioconductor packages: ", [x[0] for x in sub])
            remaining = len(packages) - count
            count += chunk_size
            print("%i to go afterwards" % remaining)
            filenames = [
                "%s/%s/%s_%s.tar.gz"
                % (
                    self.paths["docker_storage_bioconductor_download"],
                    info["repo"],
                    name,
                    info["version"],
                )
                for name, info in sub
            ]

            file_vector = "c(" + ",".join([f"'{x}'" for x in filenames]) + ")"
            r_build_script = f"""
            r <- getOption("repos")
            r["CRAN"] <- "{self.dockerator.cran_mirror}"
            options(repos=r)

            lib = "{self.paths['docker_storage_bioconductor']}"
            .libPaths(c(lib, .libPaths()))
            install.packages({file_vector},
            lib=lib,
            repos=NULL,
            type='source',
            install_opts = c('--no-docs', '--no-multiarch')
            )

            """
            bash_script = f"""
            export MAKE_OPTS="-j{self.dockerator.cores}"
            export MAKE="make -j{self.dockerator.cores}"
            {self.paths['docker_storage_r']}/bin/R --no-save </opt/install.R
            echo "done running R$?"
            """
            print(r_build_script)
            r_build_file = tempfile.NamedTemporaryFile(suffix=".r", mode="w")
            r_build_file.write(r_build_script)
            r_build_file.flush()

            self.dockerator._run_docker(
                bash_script,
                {
                    "volumes": combine_volumes(
                        ro=[
                            self.dockfill_r.volumes,
                            {
                                self.paths["storage_bioconductor_download"]: self.paths[
                                    "docker_storage_bioconductor_download"
                                ]
                            },
                        ],
                        rw=[self.volumes, {r_build_file.name: "/opt/install.R"}],
                    )
                },
                "log_bioconductor",
                append_to_log=True,
            )
            break

    def list_installed(self):
        return set(
            [x.name for x in self.paths["storage_bioconductor"].glob("*") if x.is_dir()]
        )


class RPackageInfo:
    """Caching parser for CRAN style packages lists"""

    build_in = {
        "R",
        "base",
        "boot",
        "class",
        "cluster",
        "codetools",
        "compiler",
        "datasets",
        "foreign",
        "graphics",
        "grDevices",
        "grid",
        "KernSmooth",
        "lattice",
        "MASS",
        "Matrix",
        "methods",
        "mgcv",
        "nlme",
        "nnet",
        "parallel",
        "rpart",
        "spatial",
        "splines",
        "stats",
        "stats4",
        "survival",
        "tcltk",
        "tools",
        "utils",
    }

    def __init__(self, base_url, name, cache_path):
        self.name = name
        self.base_url = base_url
        if not self.base_url.endswith("/"):
            self.base_url += "/"
        self.cache_filename = cache_path / (self.name + ".PACKAGES")

    def get(self):
        """Return a dictionary:
        package -> depends, imports, suggests, version
        """
        if not hasattr(self, "_packages"):
            if not self.cache_filename.exists():
                full_url = self.base_url + "src/contrib/PACKAGES"
                download_file(full_url, self.cache_filename)
            raw = self.cache_filename.read_text()
            pkgs = {}
            for p in self.parse(raw):
                name = p["Package"]
                deps = set(p["Depends"]) - self.build_in
                suggests = set(p["Suggests"]) - self.build_in
                imports = set(p["Imports"]) - self.build_in
                version = p["Version"]
                version = version if version else ""
                pkgs[name] = {
                    "depends": deps,
                    "suggests": suggests,
                    "imports": imports,
                    "version": version,
                    "url": f"{self.base_url}src/contrib/{name}_{version}.tar.gz",
                    "repo": self.name,
                }
            self._packages = pkgs
        return self._packages

    def parse(self, raw):
        lines = raw.split("\n")
        result = []
        current = {}
        for line in lines:
            m = re.match("([A-Za-z0-9]+):", line)
            if m:
                key = m.groups()[0]
                value = line[line.find(":") + 2 :].strip()
                if key == "Package":
                    if current:
                        result.append(current)
                        current = {}
                if key in current:
                    raise ValueError(key)
                current[key] = value
            elif line.strip():
                current[key] += line.strip()

        if current:
            result.append(current)
        for current in result:
            for k in ["Depends", "Imports", "Suggests", "LinkingTo"]:
                if k in current:
                    current[k] = re.split(", ?", current[k].strip())
                    current[k] = set(
                        [re.findall("^[^ ()]+", x)[0] for x in current[k] if x]
                    )
                else:
                    current[k] = set()
        return result


def download_file(url, filename):
    """Download a file with requests if the target does not exist yet"""
    if not Path(filename).exists():
        print("downloading", url, filename)
        r = requests.get(url, stream=True)
        if r.status_code != 200:
            raise ValueError(f"Error return on {url} {r.status_code}")
        start = time.time()
        count = 0
        with open(str(filename) + "_temp", "wb") as op:
            for block in r.iter_content(1024 * 1024):
                op.write(block)
                count += len(block)
        shutil.move(str(filename) + "_temp", str(filename))
        stop = time.time()
        print("Rate: %.2f MB/s" % ((count / 1024 / 1024 / (stop - start))))
