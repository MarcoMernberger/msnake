# -*- coding: future_fstrings -*-
import re
import os
from pathlib import Path
from .dockerator import Dockerator
import tomlkit


def merge_config(d1, d2):
    result = d1.copy()
    for key in d2:
        if not key in result:
            result[key] = {}
        for key2 in d2[key]:
            result[key][key2] = d2[key][key2]
    return result


def replace_env_vars(s):
    for k, v in os.environ.items():
        s = s.replace("${%s}" % (k,), v)
    return s


def parse_requirements(req_file):
    """Parse the requirements from a anysnake.toml file
    See readme.

    """
    used_files = [req_file]
    with open(req_file) as op:
        p = tomlkit.loads(op.read())
    if "base" in p and "global_config" in p["base"]:
        fn = replace_env_vars(p["base"]["global_config"])
        with open(fn) as op:
            gconfig = tomlkit.loads(op.read())
            used_files.insert(0, p["base"]["global_config"])
            p = merge_config(gconfig, p)

    paths = [("base", "storage_path")]
    if "env" in p:
        for k in p["env"]:
            if isinstance(p["env"][k], str):
                paths.append(("env", k))
    for path in paths:
        if path[0] in p:
            if path[1] in p[path[0]]:
                p[path[0]][path[1]] = replace_env_vars(p[path[0]][path[1]])
    p["used_files"] = used_files
    return p


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
        docker_image = "mbf_anysnake_18.04:%md5sum%"

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
    storage_per_hostname = bool(base.get("storage_per_hostname", False))

    post_build_cmd = parsed.get("build", {}).get("post_storage_build", False)
    if not isinstance(post_build_cmd, str) and not post_build_cmd is False:
        raise ValueError("post_storage_build must be a string")

    if "code_path" in base:
        code_path = Path(base["code_path"])
        del base["code_path"]
    else:
        code_path = Path("code")

    # Todo: make configurable
    Path("logs").mkdir(parents=False, exist_ok=True)

    additional_pip_lookup_res = list((parsed.get('pip_regexps', {})).items())
    additional_pip_lookup_res.append(("^@gh/([^/]+)/(.+)", r"@git+https://github.com/\1/\2"))
    global_pip_packages = parsed.get("global_python", {})
    local_pip_packages = parsed.get("python", {})
    check_pip_definitions(global_pip_packages, additional_pip_lookup_res)
    check_pip_definitions(local_pip_packages, additional_pip_lookup_res)
    bioconductor_whitelist = base.get("bioconductor_whitelist", [])
    if not isinstance(bioconductor_whitelist, list):
        raise ValueError("bioconductor_whitelist must be a list")
    cran_mode = base.get("cran", "full")
    if not cran_mode in ("minimal", "full"):
        raise ValueError("cran must be one of ('full', 'minimal')")

    environment_variables = parsed.get("env", {})

    rust_versions = parsed.get("base", {}).get("rust", [])
    if bioconductor_version and not "1.30.0" in rust_versions:  # TODO: refactor
        rust_versions.append("1.30.0")
    cargo_install = parsed.get("cargo_install")

    return Dockerator(
        docker_image,
        python_version,
        bioconductor_version,
        R_version,
        global_pip_packages,
        local_pip_packages,
        bioconductor_whitelist,
        cran_mode,
        storage_path,
        storage_per_hostname,
        code_path,
        environment_variables=environment_variables,
        post_build_cmd=post_build_cmd,
        rust_versions=rust_versions,
        cargo_install=cargo_install,
    )


def check_pip_definitions(defs, pip_lookup_regexps):
    for k, v in defs.items():
        for rex, replacement in pip_lookup_regexps:
            if re.match(rex,v):
                defs[k] = re.sub(rex, replacement, v)

    for k, v in defs.items():
        if not re.match(
            "^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$", k, flags=re.IGNORECASE
        ):
            raise ValueError(
                f"Python package name did not match PEP-0508 Names regexps: {k}"
            )
        if v and v[0] != "@":
            operators = ["<=", "<", "!=", "==", ">=", ">", "~=", "==="]
            r = r"^(" + "|".join(operators) + r")?([A-Za-z0-9_.*+!-]+)"
            if not re.match(r, v):
                raise ValueError(
                    f"Invalid version specification '{k}' = '{v}' - See PEP-0508"
                )
            if "/" in v:
                raise ValueError(
                    f"Invalid version specification - urls must start with @: '{k}' = '{v}' "
                )

