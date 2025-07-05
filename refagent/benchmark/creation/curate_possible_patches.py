import json
import refagent
import sys
import refagent.benchmark.load as bm_load
import refagent.refactoring_types.refactorings as refactorings
from typing import List
import refagent.utils.project_manager as pm
from datetime import datetime, UTC, timedelta
import os
from pathlib import Path

from pydantic import BaseModel, Field

class PatchCurator(BaseModel):
    data_file_path: str= Field(description="path to the data file to look at")
    previously_analysed: List[str] = []
    cache_path: Path = refagent.data_folder.joinpath("monitoring/previously_analysed_for_patches.json")

    def load_previously_analysed(self):
        if os.path.exists(self.cache_path):
            with open(self.cache_path) as f:
                self.previously_analysed += json.load(f)



    def main(self):
        '''This script finds data from the monitoring results which are suitable to submit patches,
        and runs the agent where possible'''
        # monitor_results.jsonl
        self.load_previously_analysed()
        new_renames = self.find_new_data()
        self.run_agent(new_renames)

    def find_new_data(self):
        LAST_X = 300  # only analyse the last 300 entries in the
        with open(self.data_file_path) as f:
            data = [json.loads(i) for i in f.read().splitlines()[-LAST_X:]]
            rename_data = bm_load.load_benchmark(data)
        with open(refagent.data_folder.joinpath("monitoring/for_patches.json")) as f:
            previous_data = json.load(f)
        filtered_renames: List[bm_load.BenchmarkItem] = []
        filtered_renames += bm_load.load_benchmark(previous_data)
        for i in rename_data:
            print(f"processing item {i.ref_id}")
            if any(i.ref_id == k.ref_id for k in filtered_renames):
                print("previously processed item")
                continue
            i.refactoring_changes = [r for r in i.refactoring_changes if isinstance(r, refactorings.Rename)]
            fun_refactorings = [r for r in i.refactoring_changes if
                                isinstance(r, refactorings.Rename) and r.has_type_change == False]
            project = pm.EvalProject(i.project_name)
            # project.checkout_main()
            # project.pull_project()

            try:
                commit = project.git_repo.commit(i.v2_hash)
            except:
                continue
            if (10 >= len(fun_refactorings) > 0
                    and commit.committed_datetime
                    > datetime.now(UTC) - timedelta(days=7)):
                filtered_renames.append(i)
        for r in filtered_renames:
            fun_refactorings = [r1 for r1 in r.refactoring_changes if
                                isinstance(r1, refactorings.Rename) and r1.has_type_change == False]
            f1 = fun_refactorings[0]
            r.improved_commit_message = f"{f1.type}: `{f1.old_name}` -> `{f1.new_name}` on line {f1.start_line}"
        with open(refagent.data_folder.joinpath("monitoring/for_patches.json"), 'w') as f:
            json.dump([i.to_json() for i in filtered_renames], f, indent=4)
        no_replication_fake_commits = []
        for i in filtered_renames:
            no_replication_fake_commits.append(
                {
                    "id": i.ref_id,
                    "response": {
                        "changes": [],
                        "commit_hash": i.v2_hash,
                        "trajectory": [],
                        "performed_refactorings": {}
                    }
                }
            )
        with open(refagent.data_folder.joinpath("results/patches-june-9/no-replication.json"), 'w') as f:
            json.dump(no_replication_fake_commits, f, indent=4)

        return self.get_renames_in_last_week(filtered_renames) # return new names to run the agent on.


    def get_renames_in_last_week(self, renames: List[bm_load.BenchmarkItem]) -> List[bm_load.BenchmarkItem]:
        filtered_renames: List[bm_load.BenchmarkItem] = []
        for i in renames:
            project = pm.EvalProject(i.project_name)
            commit = project.git_repo.commit(i.v2_hash)
            if commit.committed_datetime > datetime.now(UTC) - timedelta(days=7):
                filtered_renames.append(i)
        return filtered_renames


    def run_agent(self, new_renames: List[bm_load.BenchmarkItem]):
        for i in new_renames:
            if i.v2_hash not in self.previously_analysed:

                try:
                    # TODO: Run the agent, minus the IDE parts here
                    pass
                except:
                    print("Failed to run agent")


                self.previously_analysed.append(i.v2_hash)

            with open(self.cache_path, 'w') as f:
                json.dump(self.previously_analysed, f, indent=4)

if __name__ == '__main__':
    PatchCurator(data_file_path=sys.argv[1]).main()