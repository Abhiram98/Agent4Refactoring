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
import refagent.agents.refactrix.react_agent as react_agent

import langsmith as ls


def setup_and_run(bench_point: bm_load.RenameItem,
                  ij_server: ij.IntellijServer,
                  results_saver: rm.ResultsManager,
                  do_replication: bool,
                  plan: Optional[planning.RefactoringPlan],
                  augmented_intent: Optional[str],
                  initial_commit: Optional[str]=None,
                  use_seed: bool=False,
                  ):
    project = pm.EvalProject(bench_point.project_name)
    ij_server.reset_project_reload_counters()  # reset the counters, before checking out branch
    if initial_commit is None:
        if use_seed:
            # In this case, we would like to start the agent from the seed changes.
            if bench_point.seed_hash is not None:
                print(f"seed_hash={bench_point.seed_hash} bench_id={bench_point.ref_id}")
                project.checkout(bench_point.seed_hash, force=True)
            else:
                project.checkout(bench_point.v1_hash, force=True)
            project.reset_head(1)
        else:
            project.checkout(bench_point.v1_hash, force=True)
            project.restore_changes()
    else:
        project.checkout(initial_commit, force=True)
        project.restore_changes()

    ij_server.open_project(project_path=project.get_project_path())
    ij_server.reload_project()
    ij_server.open_file(rel_file_path=Path(bench_point.starting_file))
    if plan is not None:
        plan_type = planning.get_mock_planning_component(plan)
    else:
        plan_type = planning.PlanningComponent

    vendor = 'grazie' # switch to `openai` to use the openai models directly
    # vendor = 'openai'

    enable_critique = args.enable_critique.lower() == "true"
    agent = react_agent.ReactAgent(ide_server=ij_server,
                     reasoning_model_name=f'{vendor}:openai-o4-mini',
                     model_name=f'{vendor}:openai-gpt-4o-mini',
                     project=project,
                     plan_component=plan_type,
                     augmented_intent=augmented_intent,
                     do_replication=do_replication,
                     enable_critique=enable_critique)
    
    try:
        if not do_replication:
            agent.initialize_agent(starting_file=bench_point.starting_file)
            if enable_critique:
                print("Critique Enabled")
                agent.initialize_critique_component(bench_point.refactoring_changes)
            final_message = agent.run(initial_intent=bench_point.improved_commit_message,
                                      starting_file=bench_point.starting_file)  # run the agent with commit message
        else:
            assert initial_commit is not None, "initial commit must be provided for replication"
            agent.add_internal_commit(project.git_repo.commit(initial_commit))
            agent.initialize_agent(starting_file=bench_point.starting_file)
            # Re-initialize critique component after agent initialization
            if enable_critique:
                agent.initialize_critique_component(bench_point.refactoring_changes)
            agent.perform_replication(augmented_intent, agent.create_model(f'{vendor}:openai-gpt-4o-mini'), agent.generate_initial_plan(augmented_intent))
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
    # new_hash = project.commit_all(f"changes to solve benchmark id {bench_point.ref_id} \n\n {previous_commits}")
    print(f"New hash: {new_hash}")

    results_saver.add(
        bench_point.ref_id,
        {
            "changes": [c.to_json() for c in project.get_changes(new_hash)],
            "commit_hash": str(new_hash),
            "trajectory": [i.to_json() for i in agent.get_trajectory()],
            "performed_refactorings": agent.get_performed_refactorings(),
            "internal_commits": [str(i) for i in internal_commits],
            "performed_refactorings": agent.get_performed_refactorings(),
            "internal_commits": [str(i) for i in internal_commits],
            "replication_inspection_data": agent.get_replication_inspection_data()
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
    parser.add_argument("--replication", type=str,
                        help="Whether to run the replication component or not. "
                             "If true, ONLY the replication is performed, starting from an initial commit. "
                             "If false, ONLY the initial agent is run (to edit only the starting file)", default=True
                        )
    parser.add_argument("--use_change_summary", type=str,
                        help="Whether to use the change summary or not. "
                             "If true, the change summary is used to improve the intent. "
                             "If false, the change summary is not used.", default=False)
    parser.add_argument("--use_seed", action='store_true')
    parser.add_argument("--enable_critique", type=str, 
                        help="Whether to enable oracle-based critique component. "
                             "If true, agent suggestions are validated against oracle data before execution.",
                        default="true")
    args = parser.parse_args()


    selected_ref_ids = [int(i) for i in args.ref_ids.split(',')] if args.ref_ids is not None else None

    ij_server = ij.IntellijServer(server_url=args.ij_server_url)

    planning_results = {}
    augmented_intents = {}
    if args.planning_results_file is not None:
        with open(refagent.data_folder.joinpath(args.planning_results_file)) as f:
            json_ = json.load(f)
            planning_results = {i['id']: planning.RefactoringPlan(**i['response']['plan']) if i['response']['plan'] is not None else None
                                for i in json_}
            planning_results = {i['id']: planning.RefactoringPlan(**i['response']['plan']) if i['response']['plan'] is not None else None
                                for i in json_}
            augmented_intents = {i['id']: i['response']['augmented_intent'] for i in json_}

    initial_save_file = rm.ResultsManager(run_identifier=args.run_identifier, save_file="no-replication.json").save_file_path
    initial_commits={}
    if initial_save_file.exists():
        with open(initial_save_file) as f:
            initial_run = json.load(f)
            initial_commits = {i['id']: i['response']['commit_hash'] for i in initial_run}
    initial_commits={}
    if initial_save_file.exists():
        with open(initial_save_file) as f:
            initial_run = json.load(f)
            initial_commits = {i['id']: i['response']['commit_hash'] for i in initial_run}

    use_previous = False

    do_replication = args.replication.lower() == "true"
    results_file = "no-replication.json" if not do_replication else "post-replication.json"
    benchmark = load_benchmark(args.benchmark_file, "rename")
    results_saver = rm.ResultsManager(run_identifier=args.run_identifier, save_file=results_file)

    for bench_point in benchmark:

        if args.use_change_summary.lower() == "true":
            print(f"Using change summary for {bench_point.change_summary}")
        else:
            print(args.use_change_summary)
            print(f"Using initial commit for {bench_point.improved_commit_message}")


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
            setup_and_run(bench_point, ij_server, results_saver, do_replication,
                          plan=planning_results.get(bench_point.ref_id),
                          augmented_intent=bench_point.change_summary if args.use_change_summary.lower() == "true" else augmented_intents.get(bench_point.ref_id),
                          initial_commit=initial_commits.get(bench_point.ref_id),
                          use_seed=args.use_seed)
