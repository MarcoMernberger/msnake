import sys
import pprint
from pathlib import Path

try:
    from mbf_anysnake import parse_requirements, Dockerator
except ModuleNotFoundError:
    sys.path.append(str(Path(__file__).parent.parent / "src"))
    from mbf_anysnake import parse_requirements, parsed_to_dockerator, Dockerator

import click

config_file = "anysnake.toml"
home_files = [".hgrc", ".git-credentials", ".gitconfig", ".config/fish", '.jupyter']


@click.group()
def main():
    pass


def get_dockerator():
    parsed = parse_requirements(config_file)
    return parsed_to_dockerator(parsed), parsed


@main.command()
@click.option("--do-time", default=False, is_flag=True)
def build(do_time=False):
    """Build everything if necessary - from docker to local venv from project.setup"""
    d, _ = get_dockerator()
    d.ensure(do_time)
    return d


@main.command()
def rebuild():
    """for each locally cloned package in code,
    call python setup.py install
    """
    raise ValueError("todo")


@main.command()
def rebuild_global_venv():
    raise ValueError("todo")


def get_volumes_config(config, key1, key2):
    result = {}
    if key1 in config and key2 in config[key1]:
        for (f, t) in config[key1][key2]:
            result[Path(f).absolute()] = t
    return result


@main.command()
@click.option("--no-build/--build", default=False)
@click.option("--allow_writes/--no-allow_writes", default=False)
def shell(no_build=False, allow_writes=False):
    """Run a shell with everything mapped (build if necessary)"""
    d, config = get_dockerator()
    if not no_build:
        d.ensure()

    d.run(
        "/usr/bin/fish",
        allow_writes=allow_writes,
        home_files=home_files,
        volumes_ro=get_volumes_config(config, "run", "additional_volumes_ro"),
        volumes_rw=get_volumes_config(config, "run", "additional_volumes_rw"),
    )


def get_next_free_port(start_at):
    import socket

    try_next = True
    port = start_at
    while try_next:
        try:
            s = socket.socket()
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("localhost", port))
            s.close()
            try_next = False
        except socket.error:
            port += 1
        if port > start_at + 100:
            raise ValueError("No empty port found within search range")
    return port


main.command()


@main.command()
@click.option("--no-build/--build", default=False)
def jupyter(no_build=False):
    """Run a jupyter with everything mapped (build if necessary)"""

    d, config = get_dockerator()
    if not no_build:
        d.ensure()
    host_port = get_next_free_port(8888)
    print("Starting notebookt at %i" % host_port)

    d.run(
        "jupyter notebook --ip=0.0.0.0 --no-browser",
        home_files=home_files,
        volumes_ro=get_volumes_config(config, "run", "additional_volumes_ro"),
        volumes_rw=get_volumes_config(config, "run", "additional_volumes_rw"),
        ports=[(host_port, 8888)],
    )


@main.command()
def show_config():
    """Print the config as understood by the parser from anysnake.toml"""
    d, parsed = get_dockerator()
    d.pprint()
    print("Config files used:", parsed['used_files'])


if __name__ == "__main__":
    main()
