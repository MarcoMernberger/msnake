from pathlib import Path


def combine_volumes(ro=[], rw=[]):
    d = dict()
    for (what, mode) in [(ro, "ro"), (rw, "rw")]:
        if isinstance(what, dict):
            what = [what]
        for dd in what:
            for k, v in dd.items():
                if isinstance(v, dict):
                    v = v["bind"]
                elif isinstance(v, tuple):
                    v = v[0]
                d[str(Path(k).absolute())] = (v, mode)
    return d


def find_storage_path_from_other_machine(dockerator, postfix):
    """Find a usable storage path for this if it was already done by another machine
    and storage_per_hostname is set. 
    Otherwise return the local storage_path / postfix
    """
    result = dockerator.paths["storage"] / postfix
    if not result.exists():
        if dockerator.storage_per_hostname:
            for d in dockerator.paths["storage"].parent.glob("*"):
                if d.is_dir():
                    if (d / postfix).exists():
                        result = d / postfix
                        break
    return result
