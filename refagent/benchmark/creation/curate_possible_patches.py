import json
import refagent
import sys
import refagent.benchmark.load as bm_load
import refagent.refactoring_types.refactorings as refactorings
from typing import List
import refagent.utils.project_manager as pm
from datetime import datetime, UTC, timedelta


def main():
    '''This script finds data from the monitoring results which are suitable to submit patches'''
    # monitor_results.jsonl
    file_path = sys.argv[1]
    with open(file_path) as f:
        data = [json.loads(i) for i in f.read().splitlines()]
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

        try:
            commit = project.git_repo.commit(i.v2_hash)
        except:
            continue
        if (2 >= len(fun_refactorings) > 0
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

if __name__ == '__main__':
    main()