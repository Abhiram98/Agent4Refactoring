import refagent.utils.refminer_utils as rminer_utils
import refagent.utils.project_manager as pm
import refagent.refactoring_types.refactorings as ref

from typing import Optional, Type


def run_on_project(project_name: str,
                   filter_refactoring_type: Optional[Type[ref.RefminerOut]] = None,
                   limit_commits:int = 200):
    project = pm.EvalProject(project_name)
    commits_inspected = 0

    for commit in project.git_repo.iter_commits():
        commits_inspected += 1
        if commits_inspected > limit_commits:
            print(f"Reached {limit_commits} commits. Stopping.")
            break
        commit_hash = commit.hexsha
        refactorings = rminer_utils.default_runner.run(
            project_path=project.get_project_path(),
            commit_hash=commit_hash,
        )
        if filter_refactoring_type:
            filtered_refactorings = [i for i in refactorings
                                     if isinstance(i, filter_refactoring_type)]
        else:
            filtered_refactorings = refactorings

        print(f"Found {len(filtered_refactorings)} refactorings for commit {commit.hexsha}")


if __name__ == '__main__':
    run_on_project("flink", ref.ExtractClass)

