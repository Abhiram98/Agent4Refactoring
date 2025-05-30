import json

import refagent
import refagent.utils.project_manager as pm
import argparse
from pydantic import BaseModel, PrivateAttr
from typing import List, Set
import refagent.benchmark.load as bm_load
import refagent.benchmark.creation.scrape_project as scrape

class Monitor(BaseModel):
    output_file_name: str = "monitor_results.json"
    _output_json: List = PrivateAttr(default=[])
    _previously_analysed_commits: Set[str] = PrivateAttr(default=[])
    _used_ids: Set[int] = PrivateAttr(default=[])



    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initialize_directory()

        with open(refagent.data_folder.joinpath('monitoring').joinpath("previously_analysed_commits.json")) as f:
            commits = json.load(f)
        self._previously_analysed_commits = set(commits)

        with open(refagent.data_folder.joinpath('monitoring').joinpath("used_ids.json")) as f:
            self._used_ids = set(json.load(f))

    def initialize_directory(self):
        if not refagent.data_folder.joinpath('monitoring').exists():
            refagent.data_folder.joinpath('monitoring').mkdir()
        if not refagent.data_folder.joinpath('monitoring').joinpath("previously_analysed_commits.json").exists():
            with open(refagent.data_folder.joinpath('monitoring').joinpath("previously_analysed_commits.json"),
                      'w') as f:
                json.dump([], f, indent=4)
        if not refagent.data_folder.joinpath('monitoring').joinpath("used_ids.json").exists():
            with open(refagent.data_folder.joinpath('monitoring').joinpath("used_ids.json"), 'w') as f:
                json.dump([], f, indent=4)

    def process_project(self, project: pm.EvalProject) -> List[bm_load.BenchmarkItem]:
        monitoring_data = []
        project.pull_project()

        for commit in project.git_repo.iter_commits(project.git_repo.head):
            if commit.hexsha in self._previously_analysed_commits:
                print(f"commit {commit.hexsha} was previously analysed. skipping")
                continue

            if commit.authored_datetime < self.cutoff_date:
                print(f"commit {commit.hexsha} is older than cutoff date. skipping")
                print("Stopping loop.")
                break

            data = scrape.RenameProcessor(
                id_counter=self.get_new_id(),
                project=project,
                commit=commit,
            ).process_commit()
            if data is not None:
                monitoring_data.append(data)
                self._previously_analysed_commits.add(commit.hexsha)
                self._used_ids.add(data.ref_id)
            else:
                print(f"commit {commit.hexsha} was not added to the monitoring data")
            self.save_monitored_commit(commit)
            self.save_used_ids()

        return monitoring_data

    def save_monitored_commit(self, commit):
        with open(refagent.data_folder.joinpath('monitoring').joinpath("previously_analysed_commits.json"), 'w') as f:
            json.dump(list(self._previously_analysed_commits), f, indent=4)
        print(f"commit {commit.hexsha} was added to the monitoring data")

    def run(self, project_names: List[str]):
        new_data = []
        for name in project_names:
            project = pm.EvalProject(name)
            new_data += self.process_project(project)

        with open(self.output_file_name, 'w') as f:
            json.dump(new_data, f, indent=4)

    def get_new_id(self):
        return max(self._used_ids) + 1 if len(self._used_ids) > 0 else 10000

    def save_used_ids(self):
        with open(refagent.data_folder.joinpath('monitoring').joinpath("used_ids.json"), 'w') as f:
            json.dump(list(self._used_ids), f, indent=4)


def main():
    parser = argparse.ArgumentParser(description='monitor different projects')
    parser.add_argument('project_names_file', type=str, help='File containing project names to monitor')
    parser.add_argument('--cutoff_date', type=str, default='2025-05-30', help='Cutoff date for commits to monitor from')
    parser.add_argument('--output_file_name', type=str, default='monitor_results.json', help='Output file to store results')
    args = parser.parse_args()

    project_names = args.project_names_file.split('\n')
    Monitor(output_file_name=args.output_file_name).run(project_names)





if __name__ == '__main__':
    main()