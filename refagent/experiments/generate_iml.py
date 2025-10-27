import json
import os
import xml.etree.ElementTree as ET
import sys
from typing import List, Tuple
from pathlib import Path

import refagent.utils.project_manager as pm
import refagent.benchmark.load as benchmark_load
from pydantic import BaseModel


class GenerateImlFiles(BaseModel):
    commits: List[str]
    project: pm.EvalProject
    iml_dir: Path

    module_dirs: List[str] = []

    class Config:
        arbitrary_types_allowed = True

    def generate(self):

        self.load_module_dirs()

        for commit in self.commits:
            self.project.checkout(commit, force=True)
            src_dirs, test_dirs = self.get_all_src_dirs()

            for src_dir in src_dirs:
                if src_dir not in self.module_dirs:
                    self.edit_iml_file(src_dir, is_src=True)

            for test_dir in test_dirs:
                if test_dir not in self.module_dirs:
                    self.edit_iml_file(test_dir, is_src=False)

    def get_all_src_dirs(self) -> Tuple[List[str], List[str]]:
        """
        Traverse the project root and return all directories that contain
        a src/main/java subdirectory. Return the module directory path.
        """
        project_root = Path(self.project.get_project_path())
        src_dirs = []
        test_dirs = []
        for root, dirs, files in os.walk(project_root):
            if root.endswith("src/main/java"):
                # module root is two levels up (project/module/)
                src_dirs.append(str(Path(root).relative_to(project_root)))
            if root.endswith("src/test/java"):
                test_dirs.append(str(Path(root).relative_to(project_root)))
        return src_dirs, test_dirs

    def load_module_dirs(self):
        # self.module_dirs += os.listdir(str(self.iml_dir.joinpath('modules')))
        with open(self.iml_dir.parent.joinpath("ratpack.iml")) as f:
            splits = f.read().split("file://$MODULE_DIR$/")[1:]
        self.module_dirs += [i.split('"')[0] for i in splits]

    def create_new_src_dir(self, src_dir: str):
        module_path = self.iml_dir.joinpath(f"modules/{src_dir}")
        module_path.mkdir(parents=True, exist_ok=True)

        # copy files
        with open(self.iml_dir.joinpath("ratpack.ratpack-project.iml")) as f:
            new_project_iml = f.read().replace("ratpack-thymeleaf3", src_dir)

        with open(module_path.joinpath(f"ratpack.{src_dir}.iml"), "w") as f:
            f.write(new_project_iml)

        with open(self.iml_dir.joinpath("ratpack.ratpack-project.main.iml")) as f:
            new_project_main = f.read().replace("ratpack-thymeleaf3", src_dir)
        with open(module_path.joinpath(f"ratpack.{src_dir}.main.iml"), "w") as f:
            f.write(new_project_main)

        with open(self.iml_dir.joinpath("ratpack.ratpack-project.test.iml")) as f:
            new_project_test = f.read().replace("ratpack-thymeleaf3", src_dir)
        with open(module_path.joinpath(f"ratpack.{src_dir}.test.iml"), "w") as f:
            f.write(new_project_test)

        with open(self.iml_dir.joinpath("modules.xml")) as f:
            module_content = f.read()

        new_module_content = f"""
              <module fileurl="file://$PROJECT_DIR$/.idea/modules/{src_dir}/ratpack.{src_dir}.iml" filepath="$PROJECT_DIR$/.idea/modules/{src_dir}/ratpack.{src_dir}.iml" />
      <module fileurl="file://$PROJECT_DIR$/.idea/modules/{src_dir}/ratpack.{src_dir}.main.iml" filepath="$PROJECT_DIR$/.idea/modules/{src_dir}/ratpack.{src_dir}.main.iml" />
      <module fileurl="file://$PROJECT_DIR$/.idea/modules/{src_dir}/ratpack.{src_dir}.test.iml" filepath="$PROJECT_DIR$/.idea/modules/{src_dir}/ratpack.{src_dir}.test.iml" />"""
        module_content = module_content.replace(
            "</modules>", f"{new_module_content}\n</modules>"
        )

        with open(self.iml_dir.joinpath("modules.xml"), "w") as f:
            f.write(module_content)

        self.module_dirs.append(src_dir)

    def edit_iml_file(self, src_dir, is_src):
        with open(self.iml_dir.parent.joinpath("ratpack.iml")) as f:
            content = f.read()
        is_test_source = "false" if is_src else "true"
        new_content = f"""  <sourceFolder url="file://$MODULE_DIR$/{src_dir}" isTestSource="{is_test_source}" />
        </content>"""
        content = content.replace("</content>", new_content)
        with open(self.iml_dir.parent.joinpath("ratpack.iml"), "w") as f:
            f.write(content)

        self.module_dirs.append(src_dir)


if __name__ == "__main__":
    import refagent

    iml_dir = refagent.repo_root.joinpath("data/iml_files/ratpack_modules")

    renas_benchmark_path = sys.argv[1]
    with open(renas_benchmark_path, "r") as f:
        json_data = json.load(f)
        benchmark = benchmark_load.load_benchmark(json_data, benchmark_load.RenameItem)

    project = pm.EvalProject("ratpack")

    GenerateImlFiles(
        commits=[i.v1_hash for i in benchmark if i.project_name == "ratpack"],
        project=project,
        iml_dir=iml_dir,
    ).generate()
