import json
import refagent
import refagent.benchmark.load as bm_load
import refagent.utils.project_manager as pm
from typing import List


def main():
    with open(refagent.data_folder.joinpath("renas/renas_oracle.json")) as f:
        data = json.load(f)
    benchmark: List[bm_load.RenameItem] = bm_load.load_benchmark(
        data, bm_load.RenameItem
    )

    for i in benchmark:
        project = pm.EvalProject(i.project_name)
        if i.seed_hash is not None:
            print(f"Pushing branch for {i.ref_id}")
            project.checkout(i.seed_hash, force=True)
            branch_name = f"seed-{i.ref_id}"
            project.create_branch(branch_name)
            project.push_upstream_branch(branch_name)


if __name__ == "__main__":
    main()
