import requests
import tempfile
import re
from .util import combine_volumes


class DockFill_Bioconductor:
    def __init__(self, dockerator, dockfill_r):
        self.dockerator = dockerator
        self.dockfill_r = dockfill_r
        self.paths = self.paths
        self.paths.update(
            {
                "storage_bioconductor": (
                    self.paths["storage"] / "bioconductor" / self.bioconductor_version
                ),
                "storage_bioconductor_r_version": (
                    self.paths["storage"]
                    / "bioconductor_r_version"
                    / self.bioconductor_version
                ),
                "docker_storage_bioconductor": "/dockerator/bioconductor",
                "log_bioconductor": (
                    self.paths["log_storage"] / "dockerator.bioconductor.log"
                ),
                "storage_bioconductor_temp": (
                    self.paths["storage"]
                    / "bioconductor/downloads"
                    / self.bioconductor_version
                ),
                "docker_storage_bioconductor_temp": "/dockerator/bioconductor_downloads",
            }
        )

    @staticmethod
    def get_bioconductor_r_pairs(self):
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

    def ensure(self):
        self.check_r_bioconductor_match()
        install_list_file = (
            self.paths["storage_bioconductor"] / "should_be_installed.txt"
        )
        if not install_list_file.exists():
            # we can not use BiocManager::available
            # for that also lists >15k data packages...
            # that we do not want
            r = requests.get(
                f"https://www.bioconductor.org/packages/{self.dockorator.bioconductor_version}/bioc/"
            ).text
            packages = re.findall('href="html/(.+).html"', r)
            install_list_file.write_text("\n".join(packages))
        to_install = install_list_file.read_text().strip().split("\n")
        installed = []
        self.paths["storage_bioconductor"].mkdir(exist_ok=True)
        installed = [
            x for x in self.paths["storage_bioconductor"].glob("*") if x.is_dir()
        ]
        missing = set(to_install) - set(installed)
        if missing:
            print(f"missing {len(missing)} bioconductor packages")
            package_vector = "c(" + ", ".join([f'"{x}"' for x in missing]) + ")"
            r_build_script = f"""
r <- getOption("repos")
r["CRAN"] <- "{self.dockorator.cran_mirror}"
options(repos=r)

lib = "{self.paths['docker_storage_bioconductor']}"
.libPaths(c(lib, .libPaths()))
if (!requireNamespace("BiocManager"))
    install.packages("BiocManager", lib=lib, Ncpus={self.dockorator.cores},
    destdir="{self.paths['docker_storage_bioconductor_temp']}"
    
    )
BiocManager::install({package_vector}, lib=lib, Ncpus={self.dockorator.cores},
    destdir="{self.paths['docker_storage_bioconductor_temp']}"

)
"""
            bash_script = f"""
{self.paths['docker_storage_r']}/bin/R --no-save </opt/install.R 
"""
            r_build_file = tempfile.NamedTemporaryFile(suffix=".r", mode="w")
            r_build_file.write(r_build_script)
            r_build_file.flush()

            self.dockorator._run_docker(
                bash_script,
                {
                    "volumes": combine_volumes(
                        ro=[self.dockfill_r.volumes],
                        rw=[
                            {
                                r_build_file.name: "/opt/install.R",
                                self.paths["storage_bioconductor"]: (
                                    self.paths["docker_storage_bioconductor"],
                                    "rw",
                                ),
                            }
                        ],
                    )
                },
                self.paths["log_bioconductor"],
            )
