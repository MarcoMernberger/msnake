import re
import pprint
from pathlib import Path
from .dockerator import Dockerator


def parse_requirements(req_str):
    """Parse the requirements from a project.setup file 
    file looks like
    [base]
    python==3.6
    R==3.4
    bioconductor==3.5
    # = and == mean the same thing.
    # no # in keys or values - it triggers comment
    docker_image=mbf_dockerator:18.04 #comments are ignored

    [python]
    pandas>=0.24
    scipy
    #github
    Tyberius_prime/dppd
    #any hg/git url
    git+https://github.com/Tyberius_prime/pypipegraph
    hg+https://mbf.imt.uni-marburg.de/hg/dppd_plotnine

    [cran]
    ggplot2==2.0.0
    dplyr
    
    [something_we_dont_care_about]

    """
    lines = [sanitize(x) for x in req_str.strip().split("\n")]
    blocks = to_blocks(lines)
    for k in blocks:
        blocks[k] = parse_block(blocks[k])
    return blocks


def parse_block(lines):
    result = {}
    for ii, l in lines:
        if not l:
            continue
        m = re.match(r"([^=><]+)(==|=|=>|<=|<|>)?(.+)?", l)
        if not m:
            raise ValueError("Could not parse line %ii, '%s'" % (ii, l))
        key, op, value = m.groups()
        if key in result:
            raise ValueError("duplicate key in line %ii, '%s'" % (ii, l))
        if op == "=":
            op = "=="
        result[key] = {"name": key, "op": op, "version": value}

    return result


def parsed_to_dockerator(parsed):
    pprint.pprint(parsed)
    if not "base" in parsed:
        raise ValueError("no [base] in configuration")
    base = parsed["base"]
    if not "python" in base or not base["python"]["version"]:
        raise ValueError(
            "Must specify at the very least a python version to use, e.g. python==3.7"
        )
    python_version = base["python"]["version"]

    if "docker_image" in base:
        docker_image = base["docker_image"]["version"]
    else:
        docker_image = "mbf_dockerator:18.04"

    if "bioconductor" in base:
        bioconductor_version = base["bioconductor"]["version"]
    else:
        bioconductor_version = None
    if "R" in base:
        R_version = base["R"]["version"]
    else:
        R_version = None

    if "storage_path" in base:
        storage_path = Path(base["storage_path"]["version"])
    else:
        storage_path = Path("version_store")
    if not storage_path.exists():
        storage_path.mkdir(exist_ok=True)

    if "code_path" in base:
        code_path = Path(base["code_path"]["version"])
        del base["code_path"]
    else:
        code_path = Path("code")
    if not code_path.exists():
        code_path.mkdir(exist_ok=True)

    # Todo: make configurable
    Path("logs").mkdir(parents=False, exist_ok=True)

    return Dockerator(
        docker_image,
        python_version,
        bioconductor_version,
        R_version,
        parse_requirements(
            """
[python]
jupyter
"""
        ),
        parsed,
        storage_path,
        code_path,
    )


def to_blocks(sanitized_lines):
    blocks = {}
    last_name = "[unnamed]"
    last_block = []
    for ii, ll in enumerate(sanitized_lines):
        if ll.startswith("[") and ll.endswith("]"):
            if last_block:
                if last_name in blocks:
                    raise ValueError("Duplicate block %s" % l)
                blocks[last_name] = last_block
            last_name = ll[1:-1]
            last_block = []
        else:
            last_block.append((ii, ll))
    if last_block:
        if last_name in blocks:
            raise ValueError("Duplicate block %s" % l)
        blocks[last_name] = last_block
    return blocks


def sanitize(s):
    s = s.strip()
    if "#" in s:
        s = s[: s.find("#")].strip()
    return s
