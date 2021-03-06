# *- coding: future_fstrings -*-

import requests
from pathlib import Path
import re
from .util import find_storage_path_from_other_machine, download_file


class DockFill_Bioconductor:
    def __init__(self, anysnake, dockfill_r):
        self.anysnake = anysnake
        self.dockfill_r = dockfill_r
        self.paths = self.anysnake.paths
        self.bioconductor_version = anysnake.bioconductor_version
        self.bioconductor_whitelist = anysnake.bioconductor_whitelist
        self.cran_mode = anysnake.cran_mode

        self.done_string = (
            "done:" + self.cran_mode + ":" + ":".join(self.bioconductor_whitelist)
        )
        bc_path = find_storage_path_from_other_machine(
            self.anysnake,
            Path("bioconductor") / self.bioconductor_version,
            self.is_done,
        )
        self.paths.update(
            {
                "storage_bioconductor": bc_path,
                "docker_storage_bioconductor": "/anysnake/bioconductor",
                "storage_bioconductor_download": (
                    self.paths["storage"]
                    / "bioconductor_download"
                    / self.bioconductor_version
                ),
                "docker_storage_bioconductor_download": (
                    str(Path("/anysnake/bioconductor_download"))
                ),
                "log_bioconductor": (
                    self.paths["log_storage"]
                    / f"anysnake.bioconductor.{self.bioconductor_version}.log"
                ),
                "log_bioconductor.todo": (
                    self.paths["log_storage"]
                    / f"anysnake.bioconductor.{self.bioconductor_version}.todo.log"
                ),
                "project_bioconductor": self.paths['code'] / 'venv' / 'bioconductor'/ self.bioconductor_version,
                "docker_project_bioconductor": Path('/project') / 'code' / 'venv' / 'bioconductor'/ self.bioconductor_version,
            }
        )
        self.volumes = {
            self.paths["docker_storage_bioconductor"]: self.paths[
                "storage_bioconductor"
            ],
            self.paths["docker_storage_bioconductor_download"]: self.paths[
                "storage_bioconductor_download"
            ],
        }
        self.env = {
            "R_LIBS_SITE": "/anysnake/bioconductor",
            "R_LIBS": self.paths['docker_project_bioconductor']
        }

    def is_done(self, path):
        done_file = path / "done.sentinel"
        return done_file.exists() and done_file.read_text() == self.done_string

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
        try:
            info = {}  #  release -> {'date': , 'r_major_version':
            for block in tbody.split("</tr>"):
                if not block.strip():
                    continue
                if block.count("<td style") != 4:
                    print(block.count("<td style"))
                    raise ValueError(
                        "Bioconductor relase page layout changed - update fetch_bioconductor_release_information() - too few elements?"
                    )
                tds = block.split("<td style")[1:]
                bc_version = re.findall("\d+\.\d+", tds[0])[0]
                release_date = tds[1][tds[1].find('">') + 2 :]
                release_date = release_date[: release_date.find("<")]
                package_count = re.findall(">(\d+)<", tds[2])[0]
                r_version = re.findall(">(\d+\.\d+)<", tds[3])[0]

                release_date = maya.parse(release_date)
                release_date = release_date.rfc3339()
                release_date = release_date[: release_date.find("T")]

                info[bc_version] = {
                    "date": release_date,
                    "r_major_version": r_version,
                    "pckg_count": int(package_count),
                }
        except:
            print(
                "Bioconductor relase page layout changed - update fetch_bioconductor_release_information()"
            )
            raise

        return info

    @classmethod
    def bioconductor_relase_information(cls, anysnake):
        """Fetch the information, annotate it with a viable minor release,
        and cache the results.

        Sideeffect: inside one storeage, R does not get minor releases
        with out a change in Bioconductor Version.

        Guess you can overwrite R_version in your configuration file.
        """
        import tomlkit

        anysnake.paths.update(
            {
                "storage_bioconductor_release_info": (
                    anysnake.paths["storage"]
                    / "bioconductor_release_info"
                    / anysnake.bioconductor_version
                )
            }
        )
        cache_file = anysnake.paths["storage_bioconductor_release_info"]
        if not cache_file.exists():
            cache_file.parent.mkdir(exist_ok=True, parents=True)
            all_info = cls.fetch_bioconductor_release_information()
            if not anysnake.bioconductor_version in all_info:
                raise ValueError(
                    f"Could not find bioconductor {anysnake.bioconductor_version} - check https://bioconductor.org/about/release-announcements/"
                )
            info = all_info[anysnake.bioconductor_version]
            major = info["r_major_version"]
            url = anysnake.cran_mirror + "src/base/R-" + major[0]
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
    def find_r_from_bioconductor(cls, anysnake):
        return cls.bioconductor_relase_information(anysnake)["r_version"]

    def check_r_bioconductor_match(self):
        info = self.get_bioconductor_release_information()
        major = info["r_major_version"]
        if not self.anysnake.R_version.startswith(major):
            raise ValueError(
                f"bioconductor {self.bioconductor_version} requires R {major}.*, but you requested {self.R_version}"
            )

    def ensure(self):
        done_file = self.paths["storage_bioconductor"] / "done.sentinel"
        should = self.done_string
        self.paths['project_bioconductor'].mkdir(exist_ok=True, parents=True)
        if not done_file.exists() or done_file.read_text() != should:
            info = self.bioconductor_relase_information(self.anysnake)
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
            for k, url in urls.items():
                cache_path = self.paths["storage_bioconductor_download"] / (
                    k + ".PACKAGES"
                )
                if not cache_path.exists():
                    cache_path.parent.mkdir(exist_ok=True, parents=True)
                    download_file(url + "src/contrib/PACKAGES", cache_path)

            bash_script = f"""
{self.paths['docker_storage_python']}/bin/virtualenv /tmp/venv
source /tmp/venv/bin/activate
pip install pypipegraph requests==2.20.0 future-fstrings packaging numpy
export PATH=$PATH:/anysnake/cargo/bin
echo "cargo?"
echo `which cargo`
python  {self.paths['docker_storage_bioconductor']}/_inside_dockfill_bioconductor.py
"""
            env = {"URL_%s" % k.upper(): v for (k, v) in urls.items()}
            env["BIOCONDUCTOR_VERSION"] = self.bioconductor_version
            env["BIOCONDUCTOR_WHITELIST"] = ":".join(self.bioconductor_whitelist)
            env["CRAN_MODE"] = self.cran_mode
            env[
                "RUSTUP_TOOLCHAIN"
            ] = "1.30.0"  # Todo: combine with the one in parser.py
            volumes = {
                self.paths["docker_storage_python"]: self.paths["storage_python"],
                self.paths["docker_storage_venv"]: self.paths["storage_venv"],
                self.paths["docker_storage_r"]: self.paths["storage_r"],
                self.paths["docker_storage_bioconductor"]
                / "_inside_dockfill_bioconductor.py": Path(__file__).parent
                / "_inside_dockfill_bioconductor.py",
                self.paths["docker_storage_bioconductor_download"]: self.paths[
                    "storage_bioconductor_download"
                ],
                self.paths["docker_storage_bioconductor"]: self.paths[
                    "storage_bioconductor"
                ],
                self.paths["docker_storage_rustup"]: self.paths["storage_rustup"],
                self.paths["docker_storage_cargo"]: self.paths["storage_cargo"],
            }
            print("calling bioconductor install docker")
            self.anysnake._run_docker(
                bash_script,
                {"volumes": volumes, "environment": env},
                "log_bioconductor",
                root=True,
            )
            if not self.is_done(self.paths["storage_bioconductor"]):
                print(
                    f"bioconductor install failed, check {self.paths['log_bioconductor']}"
                )
            else:
                print("bioconductor install done")
            return True
        return False

    def freeze(self):
        return {
            "base": {
                "bioconductor_version": self.bioconductor_version,
                "bioconductor_whitelist": self.bioconductor_whitelist,
                "cran": self.cran_mode,
            }
        }
