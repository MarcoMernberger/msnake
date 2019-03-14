# -*- coding: future_fstrings -*-

from pathlib import Path
import subprocess
import docker


class DockFill_Docker:
    def __init__(self, dockerator):
        self.dockerator = dockerator
        self.paths = self.dockerator.paths
        self.paths.update(
            {
                "docker_image_build_scripts": (
                    Path(__file__).parent.parent.parent / "docker_images"
                )
            }
        )
        self.volumes = {}

    def ensure(self):
        """Build (or pull) the docker container if it's not present in the system.
        pull only happens if we don't have a build script
        """
        client = docker.from_env()
        tags_available = set()
        for img in client.images.list():
            tags_available.update(img.tags)
        if self.dockerator.docker_image in tags_available:
            pass
        else:
            bs = (
                self.paths["docker_image_build_scripts"]
                / self.dockerator.docker_image
                / "build.sh"
            )
            if bs.exists():
                print("having to call", bs)
                subprocess.check_call(
                    [str(bs)],
                    cwd=str(
                        self.paths["docker_image_build_scripts"]
                        / self.dockerator.docker_image
                    ),
                )
            else:
                print(bs, "not found")
                client.images.pull(self.dockerator.docker_image)
        return False

    def pprint(self):
        print(f"  docker_image = {self.dockerator.docker_image}")
