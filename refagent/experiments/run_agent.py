import argparse
from idlelib.configdialog import changes
from pathlib import Path
import json
from typing import Optional, List
import traceback
# import refagent.agents.simple_agent as simple_agent
import refagent.benchmark.load as bm_load
import refagent
import refagent.experiments.results_manager as rm
import refagent.utils.project_manager as pm
import argparse
import refagent.agents.refactrix.refactoring_agent as ra
import refagent.utils.intellij_server as ij
import refagent.agents.refactrix.planning as planning

import langsmith as ls


def setup_and_run(bench_point: bm_load.BenchmarkItem,
                  ij_server: ij.IntellijServer,
                  results_saver: rm.ResultsManager,
                  plan: Optional[planning.RefactoringPlan]):
    project = pm.EvalProject(bench_point.project_name)
    ij_server.reset_project_reload_counters()  # reset the counters, before checking out branch
    project.checkout(bench_point.v1_hash, force=True)
    # drop any unstaged changes
    project.restore_changes()

    ij_server.open_project(project_path=project.get_project_path())
    ij_server.reload_project()
    ij_server.open_file(rel_file_path=Path(bench_point.starting_file))
    if plan is not None:
        plan_type = planning.get_mock_planning_component(plan)
    else:
        plan_type = planning.PlanningComponent

    agent = ra.Agent(ide_server=ij_server,
                     model_name='openai:gpt-4o-mini',
                     reasoning_model_name='openai:o4-mini',
                     project=project,
                     plan_component=plan_type)
    try:
        final_message = agent.run(initial_intent=bench_point.improved_commit_message,
                                  starting_file=bench_point.starting_file)  # run the agent with commit message
    except Exception as e:
        print("Agent execution failed ;/")
        traceback.print_exc()

    internal_commits = agent.internal_commits()
    previous_commits = "\n".join([i.message for i in internal_commits])

    if len(internal_commits) > 0:
        project.reset_head(len(internal_commits))
    agent.update_changed_files()
    project.safe_add(agent.files_changed())
    new_hash = project.git_repo.index.commit(f"changes to solve benchmark id {bench_point.ref_id} \n\n {previous_commits}")

    results_saver.add(
        bench_point.ref_id,
        {
            "changes": [c.to_json() for c in project.get_changes(new_hash)],
            "commit_hash": str(new_hash),
            "trajectory": [i.to_json() for i in agent.get_trajectory()],
            "performed_refactorings": agent.get_performed_refactorings()
        }
    )
    results_saver.save()


def load_benchmark(filepath, bench_type) -> List[bm_load.BenchmarkItem]:
    item_type = bm_load.BenchmarkItem
    if bench_type == 'rename':
        item_type = bm_load.RenameItem

    with open(filepath) as f:
        benchmark_json = json.load(f)
    benchmark = bm_load.load_benchmark(benchmark_json, bench_type=item_type)
    return benchmark

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
    parser.add_argument('-planning_results_file', type=str, help='Use results from previous planning '
                                                                 'run to avoid double work.', default=None)
    parser.add_argument('--benchmark_file', type=str, help='Path to benchmark file', default=str(refagent.benchmark_full_file))
    parser.add_argument('--benchmark_type', type=str, help='default/rename',
                        default='default')
    args = parser.parse_args()

    selected_ref_ids = [int(i) for i in args.ref_ids.split(',')] if args.ref_ids is not None else None

    ij_server = ij.IntellijServer(server_url=args.ij_server_url)

    planning_results = {}
    if args.planning_results_file is not None:
        with open(refagent.data_folder.joinpath(args.planning_results_file)) as f:
            planning_results = {i['id']: planning.RefactoringPlan(**i['response']) for i in json.load(f)}

    use_previous = False

    benchmark = load_benchmark(args.benchmark_file, args.benchmark_type)
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

        with ls.trace(name=f"refactoring agent - {args.run_identifier}. bench point {bench_point.ref_id}",
                      tags=[args.run_identifier]) as tracer:
            setup_and_run(bench_point, ij_server, results_saver, plan=planning_results.get(bench_point.ref_id))
