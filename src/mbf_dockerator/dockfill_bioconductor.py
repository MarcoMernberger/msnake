import requests
import tempfile
import re
from .util import combine_volumes


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
                "log_bioconductor": (
                    self.paths["log_storage"]
                    / f"dockerator.bioconductor.{self.bioconductor_version}.log"
                ),
            }
        )
        self.volumes = {
            self.paths["storage_bioconductor"]: self.paths[
                "docker_storage_bioconductor"
            ]
        }

    @staticmethod
    def get_bioconductor_r_pairs():
        pairs = {}
        url = "https://bioconductor.org/about/release-announcements/"
        bc = requests.get(url).text
        tbody = bc[
            bc.find("<tbody>") : bc.find("</tbody>")
        ]  # at least for now it's the first table on the page
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
                    pairs[b] = r_version
        return pairs

    @classmethod
    def find_r_from_bioconductor(cls, dockerator, bioconductor_version):
        dockerator.paths.update(
            {
                "storage_bioconductor_r_version": (
                    dockerator.paths["storage"]
                    / "bioconductor_r_version"
                    / bioconductor_version
                )
            }
        )
        cache_file = dockerator.paths["storage_bioconductor_r_version"]
        if not cache_file.exists():
            cache_file.parent.mkdir(exist_ok=True, parents=True)
            pairs = cls.get_bioconductor_r_pairs()
            if not bioconductor_version in pairs:
                raise ValueError(
                    f"Could not find bioconductor {bioconductor_version } - check https://bioconductor.org/about/release-announcements/"
                )
            major = pairs[bioconductor_version]
            # chosen = major + '.0'
            if True:
                # this is very nice, but simply wrong - 3.8 does not work with R 3.5.2 e.g.
                # now we now 3.x - but we don't know 3.x.y
                url = dockerator.cran_mirror + "src/base/R-" + major[0]
                r = requests.get(url).text
                available = re.findall("R-(" + major + r"\.\d+).tar.gz", r)
                matching = [x for x in available if x.startswith(major)]
                by_minor = [(re.findall(r"\d+.\d+.(\d+)", x), x) for x in matching]
                by_minor.sort()
                chosen = by_minor[-1][1]
            cache_file.write_text(chosen)
        return cache_file.read_text()

    def check_r_bioconductor_match(self):
        pairs = self.get_bioconductor_r_pairs()
        major = pairs[self.dockerator.bioconductor_version]
        if not self.dockerator.R_version.startswith(major):
            raise ValueError(
                f"bioconductor {self.bioconductor_version} requires R {major}.*, but you requested {self.R_version}"
            )

    def list_available_bc_packages(self):
        import json
        install_list_file = (
            self.paths["storage_bioconductor"] / "should_be_installed.txt"
        )
        if not install_list_file.exists():
            c = BioConductorPackageInfo(self.bioconductor_version)
            c.load()
            bioc, cran = c.get_bioc_and_cran_deps()
            install_list_file.write_text(json.dumps([list(bioc), list(cran)]))
        return json.loads(install_list_file.read_text())

    def ensure(self):
        self.check_r_bioconductor_match()
        self.paths["storage_bioconductor"].mkdir(exist_ok=True, parents=True)
        to_install_bioc, to_install_cran = self.list_available_bc_packages()

        installed = set([
            x for x in self.paths["storage_bioconductor"].glob("*") if x.is_dir()
        ])
        missing_cran = [x for x in to_install_cran if not x in installed]
        missing_bioc = [x for x in to_install_bioc if not x in installed]

        if missing_cran or missing_bioc:
            print(f"missing {len(missing_bioc)} bioconductor packages, {len(missing_cran)} cran packages")
            bioc_package_vector = "c(" + ", ".join([f'"{x}"' for x in missing_bioc]) + ")"
            cran_package_vector = "c(" + ", ".join([f'"{x}"' for x in missing_cran]) + ")"
            r_build_script = f"""
r <- getOption("repos")
r["CRAN"] <- "{self.dockerator.cran_mirror}"
options(repos=r)

lib = "{self.paths['docker_storage_bioconductor']}"
.libPaths(c(lib, .libPaths()))
if (!requireNamespace("BiocManager"))
    install.packages("BiocManager", lib=lib, Ncpus={self.dockerator.cores})
    
print("installing cran")
install.packages({cran_package_vector}, lib=lib, Ncpus={self.dockerator.cores}, dependencies=T)
    
print("installing bioc")
BiocManager::install({bioc_package_vector}, lib=lib, Ncpus={self.dockerator.cores}, dependencies=F)
"""
            bash_script = f"""
{self.paths['docker_storage_r']}/bin/R --no-save </opt/install.R 
"""
            r_build_file = tempfile.NamedTemporaryFile(suffix=".r", mode="w")
            r_build_file.write(r_build_script)
            r_build_file.flush()

            self.dockerator._run_docker(
                bash_script,
                {
                    "volumes": combine_volumes(
                        ro=[self.dockfill_r.volumes],
                        rw=[self.volumes, {r_build_file.name: "/opt/install.R"}],
                    )
                },
                "log_bioconductor",
            )


class BioConductorPackageInfo:
    """An interface to bioconductors PACKAGES
    information - used to calculate what to install
    """

    def __init__(self, version):
        self.urls = {
            "software": f"https://bioconductor.org/packages/{version}/bioc/src/contrib/PACKAGES",
            "annotation": f"https://bioconductor.org/packages/{version}/data/annotation/src/contrib/PACKAGES",
            "experiment": f"https://bioconductor.org/packages/{version}/data/experiment/src/contrib/PACKAGES",
        }

    def load(self):
        self.package_info = {}
        for key, url in self.urls.items():
            raw = requests.get(url).text
            raw = re.split("^Package: ", raw, flags=re.MULTILINE)[1:]
            pkgs = {}
            for r in raw:
                name = r[: r.find("\n")]
                deps = self.by_tag(r, "Depends")
                suggests = self.by_tag(r, "Suggests")
                imports = self.by_tag(r, "Imports")
                pkgs[name] = {"depends": deps, "suggests": suggests, "imports": imports}
            self.package_info[key] = pkgs

    def get_bioc_and_cran_deps(self):
        """What is the bare minimum to install from bioconductor and cran?
        result is (bioc_packages, non_bioc_packages), which the later being presumably
        cran 
        bioc_packages is in topological order, ready to install
        
        """
        all_deps = set()
        for r in self.package_info["software"].values():
            all_deps.update(r["depends"])
        all_deps = all_deps.difference(set(self.package_info["annotation"].keys()))
        all_deps = all_deps.difference(set(self.package_info["experiment"].keys()))
        cran_deps = all_deps.difference(set(self.package_info["software"].keys()))
        bioc_deps = list(self.package_info['software'].keys())
        return bioc_deps, cran_deps

    @staticmethod
    def by_tag(r, tag):
        if "\n" + tag in r:
            r = r[r.find("\n" + tag) + len(tag) + 3 :]
            if "\n" in r:
                r = r[: r.find("\n")]
            r = re.split(", ?", r)
            r = [x.strip() for x in r]
            m = []
            for x in r:
                if x.strip():
                    y = re.findall("^[^ ()]+", x)
                    if not y:
                        raise ValueError(x)
                    m.append(y[0])
            return m
        return []

