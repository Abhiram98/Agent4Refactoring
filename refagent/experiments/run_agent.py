import argparse
from pathlib import Path

# import refagent.agents.simple_agent as simple_agent
import refagent.benchmark.load as bm_load
import refagent
import refagent.experiments.results_manager as rm
import refagent.utils.project_manager as pm
import argparse
import refagent.agents.refactoring_agent as ra
import refagent.utils.intellij_server as ij

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Run the agent on the entire benchmark.')
    parser.add_argument('-ij_server_url', type=str, help='Url where IJ server is running.', default=refagent.IJ_SERVER_URL)
    args = parser.parse_args()

    ij_server = ij.IntellijServer(server_url=args.ij_server_url)

    use_previous = False
    benchmark = bm_load.load_benchmark(refagent.benchmark_lite_json)
    results_saver = rm.ResultsManager()

    for bench_point in benchmark:
        project = pm.EvalProject(bench_point.project_name)
        # TODO: setup environment -
        #  Launch IJ -- assumed to be already done
        #  open project,
        project.checkout(bench_point.v1_hash)

        ij_server.open_project(project_path=project.get_project_path())
        ij_server.open_file(rel_file_path=Path(bench_point.starting_files[0]))
        # ij_server.reload_project()

        agent = ra.Agent(ij_server=ij_server, model_name='gpt-4o-mini')
        changes = agent.run(intent=bench_point.hint, starting_file=bench_point.starting_files[0]) # run the agent with commit message
        # changes = project.get_unstaged_changes()
        # files_changed = [i.git_diff.b_rawpath.decode('utf-8') for i in changes]

        # TODO: ask the agent to list out the files changed.
        project.safe_add(agent.files_changed())
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

