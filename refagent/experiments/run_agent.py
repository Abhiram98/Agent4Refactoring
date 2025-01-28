import argparse

import refagent.agents.agent1 as agent1
import refagent.benchmark.load as bm_load
import refagent
import refagent.experiments.results_manager as rm
import refagent.utils.project_manager as pm


if __name__ == '__main__':
    use_previous = False
    benchmark = bm_load.load_benchmark(refagent.benchmark_lite_json)
    results_saver = rm.ResultsManager()

    for bench_point in benchmark:
        if bench_point.ref_id < 11:
            continue
        project = pm.EvalProject(bench_point.project_name)
        project.checkout(bench_point.v1_hash)
        agent = agent1.Agent()
        changes = agent.run(bench_point)
        # changes = project.get_unstaged_changes()
        # files_changed = [i.git_diff.b_rawpath.decode('utf-8') for i in changes]
        project.safe_add(agent.files_changed)
        # project.git_repo.git.add(agent.files_changed)
        new_hash = project.git_repo.index.commit(f"changes to solve benchmark id {bench_point.ref_id}")

        results_saver.add(
            bench_point.ref_id,
            {
                "changes": [c.to_json() for c in changes],
                "commit_hash": str(new_hash),
            }
        )
        results_saver.save()

