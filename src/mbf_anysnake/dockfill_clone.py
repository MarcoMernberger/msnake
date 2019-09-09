from .util import clone_repo


class DockFill_Clone:
    """Just clone arbitrary repos and do nothing with them"""

    def __init__(self, anysnake):
        self.anysnake = anysnake
        self.paths = self.anysnake.paths

        self.paths.update(
            {
                "storage_clones": self.paths["storage"] / "clones",
                "code_clones": self.paths["code"] / "clones",
                "docker_storage_clones": "/anysnake/clones",
                "docker_code_clones": "/anysnake/code_clones",
            }
        )
        self.volumes = {
            anysnake.paths["docker_storage_clones"]: anysnake.paths["storage_clones"],
            anysnake.paths["docker_code_clones"]: anysnake.paths["code_clones"],
        }
        self.paths['storage_clones'].mkdir(exist_ok=True)
        self.paths['code_clones'].mkdir(exist_ok=True)

    def pprint(self):
        print("  Global cloned repos")
        for entry in self.anysnake.global_clones.items():
            print(f"    {entry}")
        print("  Locally cloned repos")
        for entry in self.anysnake.local_clones.items():
            print(f"    {entry}")

    def ensure(self):
        cloned = False
        with open(self.paths["storage_clones"] / "log.txt", "w") as log_file:
            for name, source in self.anysnake.global_clones.items():
                cloned |= self.clone(name, source, self.paths["storage_clones"], log_file)
        with open(self.paths["code_clones"] / "log.txt", "w") as log_file:
            for name, source in self.anysnake.local_clones.items():
                cloned |= self.clone(name, source, self.paths["code_clones"], log_file)
        return cloned

    def clone(self, name, source, target_path, log_file):
        if not (target_path / name).exists():
            clone_repo(source, name, target_path / name, log_file)
            return True
        return False
