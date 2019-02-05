import re
import pprint
from pathlib import Path
from .dockerator import Dockerator
import tomlkit


def parse_requirements(req_str):
    """Parse the requirements from a anysnake.toml file 
    See readme.
    
    """
    return tomlkit.loads(req_str)


def parsed_to_dockerator(parsed):
    if not "base" in parsed:
        raise ValueError("no [base] in configuration")
    base = parsed["base"]

    if not "python" in base or not base["python"]:
        raise ValueError(
            "Must specify at the very least a python version to use, e.g. python==3.7"
        )
    python_version = base["python"]

    if "docker_image" in base:
        docker_image = base["docker_image"]
    else:
        docker_image = "mbf_dockerator:18.04"

    if "bioconductor" in base:
        bioconductor_version = base["bioconductor"]
    else:
        bioconductor_version = None
    if "R" in base:
        R_version = base["R"]
    else:
        R_version = None

    if "storage_path" in base:
        storage_path = Path(base["storage_path"])
    else:
        storage_path = Path("version_store")
    if not storage_path.exists():
        storage_path.mkdir(exist_ok=True)

    if "code_path" in base:
        code_path = Path(base["code_path"])
        del base["code_path"]
    else:
        code_path = Path("code")
    if not code_path.exists():
        code_path.mkdir(exist_ok=True)

    # Todo: make configurable
    Path("logs").mkdir(parents=False, exist_ok=True)

    global_pip_packages = parsed.get("global_python", {})
    local_pip_packages = parsed.get("python", {})
    check_pip_definitions(global_pip_packages)
    check_pip_definitions(local_pip_packages)
    cran_packages = parsed.get("cran", {})
    for key, v in cran_packages.items():
        if v and not re.match("==[0-9.]+", v):
            raise ValueError(f"Invalid CRAN version specification {key}: '{v}'")

    return Dockerator(
        docker_image,
        python_version,
        bioconductor_version,
        R_version,
        global_pip_packages,
        local_pip_packages,
        cran_packages,
        storage_path,
        code_path,
    )


def check_pip_definitions(defs):
    for k, v in defs.items():
        if not re.match(
            "^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$", k, flags=re.IGNORECASE
        ):
            raise ValueError(
                f"Python package name did not match PEP-0508 Names regexps: {k}"
            )
        if v and v[0] != "@":
            operators = ['<=', '<', '!=', '==', '>=', '>', '~=', '===']
            r = r'^(' + "|".join(operators) + r')?([A-Za-z0-9_.*+!-]+)'
            if not re.match(r, v):
                raise ValueError(f"Invalid version specification '{k}' = '{v}' - See PEP-0508")
            if '/' in v:
                raise ValueError(f"Invalid version specification - urls must start with @: '{k}' = '{v}' ")

