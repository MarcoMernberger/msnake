import sys
import pprint
from pathlib import Path

try:
    from mbf_dockerator import parse_requirements, Dockerator
except ModuleNotFoundError:
    sys.path.append(str(Path(__file__).parent.parent / "src"))
    from mbf_dockerator import parse_requirements, parsed_to_dockerator, Dockerator

import click

@click.group()
def main():
    pass

@main.command()
def build():
    """Build everything if necessary - from docker to local venv from project.setup"""
    with open("project.setup") as op:
        req_str = op.read()
    parsed = parse_requirements(req_str)
    d = parsed_to_dockerator(parsed)
    
    d.ensure()
    return d

@main.command()
@click.option('--no-build', default=False)
def shell(no_build=False):
    """Run a shell with everything mapped (build if necessary)"""
    if not no_build:
        d = build()
    d.run("/usr/bin/fish")


if __name__ == "__main__":
    main()
