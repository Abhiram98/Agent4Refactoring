import argparse
import langsmith as ls

try:
    from grazie_langchain_utils.language_models.grazie import ChatGrazie
except ImportError:
    print("Error: Could not import ChatGrazie. Please ensure the 'grazie_langchain_utils' package is installed.")
from pydantic.v1 import SecretStr
from grazie.api.client.endpoints import GrazieApiGatewayUrls
from grazie.api.client.gateway import AuthType
import os
import json
import refagent
from langchain_openai import ChatOpenAI
import refagent.agents.refactrix.planning as planning
import refagent.benchmark.load as bm_load
import refagent.experiments.results_manager as rm
import refagent.utils.project_manager as pm

import refagent.agents.refactrix.analysis as analysis

def get_git_diff(project_name, file_path_1, file_path_2, v1_hash, v2_hash):
    project = pm.EvalProject(project_name)
    return project.get_commit_diff(
        file_path_1=file_path_1,
        file_path_2=file_path_2,
        sha_1=v1_hash,
        sha_2=v2_hash,
        unified_context=1000)

def run_planning(bench_point: bm_load.RenameItem,
                 results_saver: rm.ResultsManager):
    project = pm.EvalProject(bench_point.project_name)
    project.checkout(bench_point.v1_hash, force=True)

    # model = ChatOpenAI(model="o4-mini",
    #                    temperature=1)

    grazie_token = os.getenv("GRAZIE_JWT_TOKEN")
    if not grazie_token:
        raise ValueError("GRAZIE_JWT_TOKEN environment variable is not set")

    model = ChatGrazie(grazie_jwt_token=SecretStr(grazie_token),
                       client_auth_type=AuthType.APPLICATION,
                       client_url=GrazieApiGatewayUrls.PRODUCTION,
                       profile='openai-gpt-4o-mini',
                       client_agent_name='ref-agent',
                       client_agent_version='0.1')

    # old_name = bench_point.improved_commit_message.split(" -> ")[0].split(" ")[-1]
    # new_name = bench_point.improved_commit_message.split(" -> ")[1].split(" ")[0]
    old_name = bench_point.hints[0].split(" -> ")[0].strip(" ")
    new_name = bench_point.hints[0].split(" -> ")[1].strip(" ")

    file_1 = bench_point.seed_example.leftSideLocations[0].filePath
    file_2 = bench_point.seed_example.rightSideLocations[0].filePath
    v1_hash = bench_point.v1_hash
    seed_hash = bench_point.seed_hash
    diff =  get_git_diff(bench_point.project_name, file_1, file_2, v1_hash, seed_hash)

    print(f"Difference: {diff}")

    augmented_intent = analysis.AnalysisComponent(
        model=model,
        source_file_path=file_1,
        source_code=project.get_file_contents(file_1),
        context_information=diff,
        initial_intent=bench_point.improved_commit_message,
        old_name=old_name,
        new_name=new_name
    ).run().augmented_intent

    # planner = planning.PlanningComponent(
    #     initial_intent=augmented_intent,
    #     model=model,
    #     source_file_path=bench_point.starting_file,
    #     source_code=project.get_file_contents(bench_point.starting_file)
    # )
    # ref_plan = planner.run()
    results_saver.add(bench_point.ref_id,
                      {
                          "plan": None,
                          "augmented_intent": augmented_intent
                      }
                      )
    results_saver.save()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run the agent on the entire benchmark.')
    parser.add_argument('-ref_ids', type=str, help='IDs to run the agent on. '
                                                   'To be called as a comma separated values.'
                                                   'e.g "1,2,3,4"',
                        default=None)
    parser.add_argument('-run_identifier', type=str, help='An identifier to '
                                                          'checkpoint the performance of the agent',
                        default="default")
    parser.add_argument('--benchmark_file', type=str, help='Path to benchmark file',
                        default=str(refagent.benchmark_full_file))
    args = parser.parse_args()

    selected_ref_ids = [int(i) for i in args.ref_ids.split(',')] if args.ref_ids is not None else None
    use_previous = False
    with open(args.benchmark_file) as f:
        benchmark_json = json.load(f)
    benchmark = bm_load.load_benchmark(benchmark_json, bench_type=bm_load.RenameItem)
    results_saver = rm.ResultsManager(run_identifier=args.run_identifier, save_file="planning.json")

    for bench_point in benchmark:

        if (selected_ref_ids is not None and
                bench_point.ref_id not in selected_ref_ids):
            print(f"Skipping ref id {bench_point.ref_id} as it is not a selected one. "
                  f"Selected: {selected_ref_ids}")
            continue

        if results_saver.exists(bench_point.ref_id):
            print(f"skipping ref if {bench_point.ref_id} because it was previously worked upon.")
            continue

        print(f"Running planning for {bench_point.ref_id}")

        with ls.trace(name=f"refactoring agent planning - {args.run_identifier}. ID {bench_point.ref_id}",
                      tags=[args.run_identifier]) as tracer:
            run_planning(bench_point, results_saver)