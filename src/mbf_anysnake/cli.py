import click
from pathlib import Path
from mbf_anysnake import parse_requirements, parsed_to_dockerator


config_file = "anysnake.toml"
home_files = [".hgrc", ".git-credentials", ".gitconfig", ".config/fish", ".jupyter"]


@click.group()
def main():
    pass


def get_dockerator():
    parsed = parse_requirements(config_file)
    return parsed_to_dockerator(parsed), parsed


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


def get_volumes_config(config, key1, key2):
    """Extract a volumes config from the config if present"""
    result = {}
    if key1 in config and key2 in config[key1]:
        for (f, t) in config[key1][key2]:
            result[Path(f).absolute()] = t
    return result


@main.command()
@click.option("--do-time", default=False, is_flag=True)
def build(do_time=False):
    """Build everything if necessary - from docker to local venv from project.setup"""
    d, _ = get_dockerator()
    d.ensure(do_time)
    return d


@main.command()
@click.argument("modules", nargs=-1)
def rebuild(modules=[]):
    """for each locally cloned package in code,
    call python setup.py install
    """
    d, config = get_dockerator()
    d.rebuild(modules)


@main.command()
def rebuild_global_venv():
    raise ValueError("todo")


@main.command()
@click.option("--no-build/--build", default=False)
@click.option("--allow-writes/--no-allow-writes", default=False)
def shell(no_build=False, allow_writes=False):
    """Run a shell with everything mapped (build if necessary)"""
    d, config = get_dockerator()
    if not no_build:
        d.ensure()
    else:
        d.ensure_just_docker()
    d.run(
        "/usr/bin/fish",
        allow_writes=allow_writes,
        home_files=home_files,
        volumes_ro=get_volumes_config(config, "run", "additional_volumes_ro"),
        volumes_rw=get_volumes_config(config, "run", "additional_volumes_rw"),
    )


@main.command()
@click.option("--no-build/--build", default=False)
@click.argument("cmd", nargs=-1)
def run(cmd, no_build=False):
    """Run a command"""
    d, config = get_dockerator()
    if not no_build:
        d.ensure()
    else:
        d.ensure_just_docker()

    d.run(
        " ".join(cmd),
        allow_writes=False,
        home_files=home_files,
        volumes_ro=get_volumes_config(config, "run", "additional_volumes_ro"),
        volumes_rw=get_volumes_config(config, "run", "additional_volumes_rw"),
    )


@main.command()
@click.option("--no-build/--build", default=False)
def jupyter(no_build=False):
    """Run a jupyter with everything mapped (build if necessary)"""

    d, config = get_dockerator()
    if not no_build:
        d.ensure()
    else:
        d.ensure_just_docker()
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
    """Print the config as it is actually used"""
    d, parsed = get_dockerator()
    d.pprint()
    print("Config files used:", parsed["used_files"])


@main.command()
def default_config():
    """Write an anysnake.toml if none is present"""
    p = Path("anysnake.toml")
    if p.exists():
        print("Not overwriting existing anysnake.toml")
    else:
        p.write_text(
            """[base]
# optional global config to import
#global_config="/etc/anysnake.tompl"
# python version to use
python="3.7.2"
#bioconductor version to use, R version and CRAN dates are derived from this
bioconductor="3.8"
# cran options are 'minimal' (just what's needed from bioconductor) and 'full'
# (everything)
cran="full"
# where to store the installations
# python, R, global virtual enviromnments, bioconductor, cran
storage_path="/var/lib/anysnake"
# local venv, editable libraries
code_path="code"
# install all bioconductor packages whether they need experimental or annotation
# data or not.
# bioconductor_whitelist=["_full_"]
# or install selected packages otherwise omited like this
# bioconductor_whitelist=["chimera"]

[run]
additional_volumes_ro = [['/opt', '/opt']]
additional_volumes_rw = [['/home/some_user/.hgrc', '/home/u1000/.hgrc']]

[global_python]
jupyter=""

[python]
pandas=">=0.23"
# an editable library
dppd="@git+https://github.com/TyberiusPrime/dppd"

[env]
INSIDE_ANYSNAKE="yes"


"""
)
        
        print("Written default anysnake.toml")

@main.command()
def version():
    import mbf_anysnake
    print("mbf_anysnake version %s" % mbf_anysnake.__version__)


if __name__ == "__main__":
    main()
