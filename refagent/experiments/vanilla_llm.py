import json
import os

import refagent
import langchain
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
import refagent.benchmark.load as bm_load
import refagent.utils.project_manager as pm
import refagent.experiments.results_manager as results_manager
from grazie.api.client.endpoints import GrazieApiGatewayUrls
from grazie.api.client.gateway import AuthType
try:
    from grazie_langchain_utils.language_models.grazie import ChatGrazie
except ImportError:
    print("ChatGrazie not available. Please install `grazie-langchain-utils`.")

USE_SUMMARY = True

benchmark_lite = bm_load.load_benchmark(refagent.benchmark_lite_json)
print(benchmark_lite)

# os.environ["OPENAI_API_KEY"] = refagent.OPENAI_KEY
model = ChatOpenAI(model="gpt-4o-mini")
# model = ChatGrazie(grazie_jwt_token=os.getenv("GRAZIE_JWT_TOKEN"),
#                    client_auth_type=AuthType.APPLICATION,
#                    client_url=GrazieApiGatewayUrls.STAGING,
#                    profile="anthropic-claude-3-sonnet")

rm = results_manager.ResultsManager()

for bench_point in benchmark_lite:
    print(f"processing benchmark - {bench_point.ref_id}")
    project = pm.EvalProject(bench_point.project_name)
    project.git_repo.git.reset("--hard", "HEAD") # Perform a hard reset to drop any uncommit changes.
    project.checkout_previous(bench_point.v2_hash)

    message = ""
    contents = project.get_file_contents(bench_point.starting_file)
    message += f"{bench_point.starting_file} - {contents}"

    system_message = "Suggest changes to improve the quality of this java code."
    if bench_point.improved_commit_message != '':
        system_message += f" Please perform the following action - {bench_point.improved_commit_message}"
    if USE_SUMMARY and bench_point.change_summary!= '':
        system_message += f". {bench_point.change_summary}\n"
    messages = [
        SystemMessage(system_message),
        HumanMessage(message),
    ]
    response = model.invoke(messages)
    rm.add(bench_point.ref_id, response.content)

rm.save()
