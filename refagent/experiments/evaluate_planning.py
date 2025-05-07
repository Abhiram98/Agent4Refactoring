import argparse
import langsmith as ls
from grazie_langchain_utils.language_models.grazie import ChatGrazie
from pydantic.v1 import SecretStr
from grazie.api.client.gateway import GrazieApiGatewayUrls, AuthType
import os
import json

import refagent
import refagent.agents.refactrix.planning as planning
import refagent.benchmark.load as bm_load
import refagent.experiments.results_manager as rm
import refagent.utils.project_manager as pm


def run_planning(bench_point: bm_load.BenchmarkItem,
                 results_saver: rm.ResultsManager):
    project = pm.EvalProject(bench_point.project_name)
    model = ChatGrazie(grazie_jwt_token=SecretStr(os.getenv("GRAZIE_JWT_TOKEN")),
                       client_auth_type=AuthType.APPLICATION,
                       client_url=GrazieApiGatewayUrls.STAGING,
                       profile="openai-gpt-4o-mini",
                       client_agent_name='ref-agent',
                       client_agent_version='0.1',
                       temperature=0.3)

    planner = planning.PlanningComponent(
        initial_intent=f"{bench_point.improved_commit_message}. {bench_point.change_summary}",
        model=model,
        source_file_path=bench_point.starting_file,
        source_code=project.get_file_contents(bench_point.starting_file)
    )
    ref_plan = planner.run()
    results_saver.add(bench_point.ref_id, json.loads(ref_plan.json()))
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
    args = parser.parse_args()

    selected_ref_ids = [int(i) for i in args.ref_ids.split(',')] if args.ref_ids is not None else None

    args.run_identifier = f"planning-{args.run_identifier}"

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
            run_planning(bench_point, results_saver)
