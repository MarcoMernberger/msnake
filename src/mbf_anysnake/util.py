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
