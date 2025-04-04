import argparse
from pathlib import Path

# import refagent.agents.simple_agent as simple_agent
import refagent.benchmark.load as bm_load
import refagent
import refagent.experiments.results_manager as rm
import refagent.utils.project_manager as pm
import argparse
import refagent.agents.refactrix.refactoring_agent as ra
import refagent.utils.intellij_server as ij

import langsmith as ls


def setup_and_run(bench_point: bm_load.BenchmarkItem,
                  ij_server: ij.IntellijServer,
                  results_saver: rm.ResultsManager):
    project = pm.EvalProject(bench_point.project_name)
    project.checkout(bench_point.v1_hash)

    ij_server.open_project(project_path=project.get_project_path())
    ij_server.open_file(rel_file_path=Path(bench_point.starting_files[0]))
    # TODO: reload IJ project
    # ij_server.reload_project()

    agent = ra.Agent(ide_server=ij_server, model_name='grazie:openai-gpt-4o-mini')
    final_message = agent.run(initial_intent=bench_point.necessary_context + bench_point.hint,
                              starting_file=bench_point.starting_files[0])  # run the agent with commit message

    project.safe_add(agent.files_changed())
    new_hash = project.git_repo.index.commit(f"changes to solve benchmark id {bench_point.ref_id}")

    results_saver.add(
        bench_point.ref_id,
        {
            "changes": [c.to_json() for c in project.get_changes(new_hash)],
            "commit_hash": str(new_hash),
            "trajectory": [i.to_json() for i in agent.get_trajectory()['messages']]
        }
    )
    results_saver.save()

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Run the agent on the entire benchmark.')
    parser.add_argument('-ij_server_url', type=str, help='Url where IJ server is running.', default=refagent.IJ_SERVER_URL)
    parser.add_argument('-ref_ids', type=str, help='IDs to run the agent on. '
                                                   'To be called as a comma separated values.'
                                                   'e.g "1,2,3,4"',
                        default=None)
    parser.add_argument('-run_identifier', type=str, help='An identifier to '
                                                          'checkpoint the performance of the agent',
                        default="default")
    args = parser.parse_args()

    selected_ref_ids = [int(i) for i in args.ref_ids.split(',')] if args.ref_ids is not None else None

    ij_server = ij.IntellijServer(server_url=args.ij_server_url)

    use_previous = False
    benchmark = bm_load.load_benchmark(refagent.benchmark_lite_json)
    results_saver = rm.ResultsManager(run_identifier=args.run_identifier)

    for bench_point in benchmark:

        if (selected_ref_ids is not None and
                bench_point.ref_id not in selected_ref_ids):
            print(f"Skipping ref id {bench_point.ref_id} as it is not a selected one. "
                  f"Selected: {selected_ref_ids}")
            continue

        if results_saver.exists(bench_point.ref_id):
            print(f"skipping ref if {bench_point.ref_id} because it was previously worked upon.")
            continue

        with ls.trace(name=f"refactoring agent - {args.run_identifier}",
                      tags=[args.run_identifier]) as tracer:
            setup_and_run(bench_point, ij_server, results_saver)
