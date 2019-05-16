# -*- coding: future_fstrings -*-
import click
import click_completion

click_completion.init()

from pathlib import Path
from mbf_anysnake import parse_requirements, parsed_to_anysnake
import subprocess
from .util import get_next_free_port


config_file = "anysnake.toml"
home_files = [".hgrc", ".git-credentials", ".gitconfig"]
home_dirs = [
    ".config/fish",
    ".config/matplotlib",
    ".cache/matplotlib",
    ".jupyter",
    ".local/share/fish",
    ".local/share/jupyter",
    ".ipython",
]


@click.group()
def main():
    pass


def get_anysnake():
    parsed = parse_requirements(config_file)
    return parsed_to_anysnake(parsed), parsed


def get_volumes_config(config, key2):
    """Extract a volumes config from the config if present"""
    result = {}
    for key1 in ["global_run", "run"]:
        if key1 in config and key2 in config[key1]:
            for (f, t) in config[key1][key2]:
                result[Path(f).expanduser().absolute()] = t
    return result


@main.command()
@click.option("--do-time", default=False, is_flag=True)
def build(do_time=False):
    """Build everything if necessary - from docker to local venv from project.setup"""
    d, _ = get_anysnake()
    d.ensure(do_time)
    return d


@main.command()
def rebuild():
    """for each locally cloned package in code,
    call python setup.py install
    """
    d, config = get_anysnake()
    d.rebuild()


@main.command()
@click.argument("packages", nargs=-1, required=True)
def remove_pip(packages):
    """Remove pip modules, from anysnake.toml. 
    If they're installed, remove their installation
    If they're editable, remove their code/folders as well"""
    import shutil
    import tomlkit

    d, config = get_anysnake()
    local_config = tomlkit.loads(Path("anysnake.toml").read_text())
    write_toml = False
    for p in packages:
        if p in local_config.get("python"):
            del local_config["python"][p]
            write_toml = True
        path = d.paths["code_clones"] / p
        if path.exists():
            if click.confirm(f"really remove {path}?)"):
                shutil.rmtree(str(path))
        lib_path = (
            d.paths["code_venv"]
            / "lib"
            / ("python" + d.major_python_version)
            / "site-packages"
        )
        print(p + "*")
        for f in lib_path.glob(p + "*"):
            print(f)

    if write_toml:
        import time

        backup_filename = "anysnake.toml.%s" % time.strftime("%Y-%M-%d-%H-%M")
        print("writing new anysnake.toml - old one in %s" % backup_filename)
        shutil.copy("anysnake.toml", backup_filename)
        with open("anysnake.toml", "w") as op:
            op.write(tomlkit.dumps(local_config))


@main.command()
def rebuild_global_venv():
    raise ValueError("todo")


@main.command()
@click.option(
    "--no-build/--build",
    default=False,
    help="don't perform build if things are missing",
)
@click.option(
    "--allow-writes/--no-allow-writes", default=False, help="mount all volumes rw"
)
@click.option(
    "--include-perf/--no-include-perf",
    default=False,
    help="include perf tool for profiling",
)
def shell(no_build=False, allow_writes=False, include_perf=False):
    """Run a shell with everything mapped (build if necessary)"""
    import os

    d, config = get_anysnake()
    if not no_build:
        d.ensure()
    else:
        d.ensure_just_docker()
    cmd = "/usr/bin/fish"
    if include_perf:
        cmd = (
            "sudo apt-get update;\nsudo apt-get install -y linux-tools-common linux-tools-generic linux-tools-`uname -r`\n"
            + cmd
        )
    print(
        d.run(
            cmd,
            allow_writes=allow_writes,
            home_files=home_files,
            home_dirs=home_dirs,
            volumes_ro=get_volumes_config(config, "additional_volumes_ro"),
            volumes_rw=get_volumes_config(config, "additional_volumes_rw"),
        )
    )


@main.command()
@click.option("--no-build/--build", default=False)
@click.option("--pre/--no-pre", default=True, help="run pre_run_inside/outside")
@click.option("--post/--no-post", default=True, help="run post_run_inside/outside")
@click.argument("cmd", nargs=-1)
def run(cmd, no_build=False, pre=True, post=True):
    """Run a command"""
    import subprocess

    d, config = get_anysnake()
    if not no_build:
        d.ensure()
    else:
        d.ensure_just_docker()

    pre_run_outside = config.get("run", {}).get("pre_run_outside", False)
    pre_run_inside = config.get("run", {}).get("pre_run_inside", False)
    if pre and pre_run_outside:
        subprocess.Popen(pre_run_outside, shell=True).communicate()
    cmd = "\n" + " ".join(cmd) + "\n"
    if pre and pre_run_inside:
        cmd = pre_run_inside + cmd
    post_run_outside = config.get("run", {}).get("post_run_outside", False)
    post_run_inside = config.get("run", {}).get("post_run_inside", False)
    if post and post_run_inside:
        cmd += post_run_inside
    print(
        d.run(
            cmd,
            allow_writes=False,
            home_files=home_files,
            home_dirs=home_dirs,
            volumes_ro=get_volumes_config(config, "additional_volumes_ro"),
            volumes_rw=get_volumes_config(config, "additional_volumes_rw"),
        )
    )
    if post and post_run_outside:
        subprocess.Popen(post_run_outside, shell=True).communicate()


@main.command()
@click.option("--no-build/--build", default=False)
def jupyter(no_build=False):
    """Run a jupyter with everything mapped (build if necessary)"""

    d, config = get_anysnake()
    if not no_build:
        d.ensure()
    else:
        d.ensure_just_docker()
    host_port = get_next_free_port(8888)
    print("Starting notebookt at %i" % host_port)

    d.run(
        "jupyter notebook --ip=0.0.0.0 --no-browser",
        home_files=home_files,
        home_dirs=home_dirs,
        volumes_ro=get_volumes_config(config, "additional_volumes_ro"),
        volumes_rw=get_volumes_config(config, "additional_volumes_rw"),
        ports=[(host_port, 8888)],
    )

@main.command()
@click.option("--no-build/--build", default=False)
def ssh(no_build=False):
    """Run an sshd with everything mapped (build if necessary),
    using your authorized_keys keys from ~/.ssh

    You might want to use additional_volumes_ro to map in
    some host keys (
        "/etc/ssh/ssh_host_ecdsa_key",
        "/etc/ssh/ssh_host_ed25519_key",
        "/etc/ssh/ssh_host_rsa_key",
    ).
    
    """

    d, config = get_anysnake()
    if not no_build:
        d.ensure()
    else:
        d.ensure_just_docker()
    host_port = get_next_free_port(8822)
    print("Starting sshd at %i" % host_port)
    if not ".vscode-remote" in home_dirs:
        home_dirs.append(".vscode-remote")
    home_files.append(".ssh/authorized_keys")

    volumes_ro = get_volumes_config(config, "additional_volumes_ro")
    volumes_ro
    d.run( """
        echo "now starting ssh server"
        sudo /usr/sbin/sshd -D
        #/usr/bin/fish
        """,
        home_files=home_files,
        home_dirs=home_dirs,
        volumes_ro=volumes_ro,
        volumes_rw=get_volumes_config(config, "additional_volumes_rw"),
        ports=[(host_port, 8822)],
    )


@main.command()
@click.argument("modules", nargs=-1)
@click.option("--report-only/--no-report-only", default=False)
def test(modules, report_only):
    """Run pytest on all (or a subset) modules that were in the code path and had a tests/conftest.py"""
    from . import testing

    d, config = get_anysnake()
    d.ensure()
    testing.run_tests(modules, d, config, report_only)


@main.command()
def show_config():
    """Print the config as it is actually used"""
    d, parsed = get_anysnake()
    d.pprint()
    print("")
    print("Additional volumes")
    print("  RO")
    for outside, inside in get_volumes_config(parsed, "additional_volumes_ro").items():
        print(f"    {outside} -> {inside}")
    print("  RW")
    for outside, inside in get_volumes_config(parsed, "additional_volumes_rw").items():
        print(f"    {outside} -> {inside}")
    print("")
    print("Config files used:", parsed["used_files"])


@main.command()
def show_paths():
    """Print the config as it is actually used"""
    d, parsed = get_anysnake()
    import pprint

    print("paths detected")
    pprint.pprint(d.paths)


@main.command()
def default_config():
    """Print a default config"""
    p = Path("anysnake.toml")
    print(
        """[base]
# optional global config to import
#global_config="/etc/anysnake.tompl"
# python version to use
python="3.7.2"
#project_name = folder name of anysnake.toml by default, overwrite here
#project_name="example"

#bioconductor version to use, R version and CRAN dates are derived from this
# (optional) 
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

# include rust (if you use bioconductor, rust 1.30.0 will be added automatically)
# rust = ["1.30.0", "nigthly-2019-03-20"]

[run]
additional_volumes_ro = [['/opt', '/opt']]
additional_volumes_rw = [['/home/some_user/.hgrc', '/home/u1000/.hgrc']]
pre_run_outside = \"""
        echo "bash script, runs outside of the continer before 'run'"
\"""

pre_run_inside = \"""
        echo "bash script, runs inside of the continer before 'run' (ie. after pre_run_outside)"
\"""
post_run_inside = "echo 'bash script running inside container after run cmd'"
post_run_outside = "echo 'bash script running outside container after run cmd'"

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


def merge_dicts(a, b, path=None):
    "merges b into a"
    if path is None:
        path = []
    for key in b:
        if key in a:
            if isinstance(a[key], dict) and isinstance(b[key], dict):
                merge_dicts(a[key], b[key], path + [str(key)])
            elif a[key] == b[key]:
                pass  # same leaf value
            else:
                raise Exception("Conflict at %s" % ".".join(path + [str(key)]))
        else:
            a[key] = b[key]
    return a


@main.command()
def freeze():
    """Output installed packages in anysnake.toml format"""
    import tomlkit

    d, parsed = get_anysnake()
    output = {}
    for s in d.strategies:
        if hasattr(s, "freeze"):
            merge_dicts(output, s.freeze())
    print(tomlkit.dumps(output))


@main.command()
def version():
    import mbf_anysnake

    print("mbf_anysnake version %s" % mbf_anysnake.__version__)


@main.command()
@click.option(
    "-i", "--case-insensitive/--no-case-insensitive", help="Case insensitive completion"
)
@click.argument(
    "shell",
    required=False,
    type=click_completion.DocumentedChoice(click_completion.core.shells),
)
def show_completion(shell, case_insensitive):
    """Show the click-completion-command completion code
    ie. what you need to add to your shell configuration.
    """
    extra_env = (
        {"_CLICK_COMPLETION_COMMAND_CASE_INSENSITIVE_COMPLETE": "ON"}
        if case_insensitive
        else {}
    )
    click.echo(click_completion.core.get_code(shell, extra_env=extra_env))


if __name__ == "__main__":
    main()
