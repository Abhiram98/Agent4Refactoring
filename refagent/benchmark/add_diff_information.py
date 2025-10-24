import json

import git
import refagent.benchmark.load as bm_load
import refagent.utils.project_manager as pm


def add_diffs(benchmark_items: list[bm_load.BenchmarkItem]):
    for bench_item in benchmark_items:
        project = pm.EvalProject(bench_item.project_name)
        diffs = project.get_changes(bench_item.v2_hash)
        # diffs_json = [d.to_json() for d in diffs]
        bench_item.diffs = diffs
    final_data = [d.to_json() for d in benchmark_items]
    return final_data


if __name__ == "__main__":
    import refagent

    augmented_data = add_diffs(bm_load.load_benchmark(refagent.benchmark_lite_json))
    with open(str(refagent.benchmark_lite_file) + ".1", "w") as f:
        json.dump(augmented_data, f, indent=4)
