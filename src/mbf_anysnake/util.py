# -*- coding: future_fstrings -*-
import requests
import time
import shutil
import time
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


def find_storage_path_from_other_machine(dockerator, postfix, check_func=None):
    """Find a usable storage path for this if it was already done by another machine
    and storage_per_hostname is set. 
    Otherwise return the local storage_path / postfix
    """
    if check_func is None:
        check_func = lambda x: x.exists()
    search_path = dockerator.paths["storage"].parent.parent
    docker_image = Path(dockerator.paths["storage"].name)
    result = dockerator.paths["storage"] / postfix
    postfix = docker_image / postfix
    if not result.exists():
        if dockerator.storage_per_hostname:
            for d in search_path.glob("*"):
                if d.is_dir():
                    if check_func(d / postfix):
                        result = d / postfix
                        break
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
