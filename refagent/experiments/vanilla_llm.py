import json
import os

import refagent
import langchain
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
import refagent.benchmark.load as bm_load
import refagent.experiments.project_manager as pm
import refagent.experiments.results_manager as results_manager

benchmark_lite = bm_load.load_benchmark(refagent.benchmark_lite_json)
print(benchmark_lite)

os.environ["OPENAI_API_KEY"] = refagent.OPENAI_KEY
model = ChatOpenAI(model="gpt-4o-mini")

rm = results_manager.ResultsManager()

for bench_point in benchmark_lite:
    if bench_point.ref_id!=13:
        continue
    print(f"processing benchmark - {bench_point.ref_id}")
    project = pm.EvalProject(bench_point.project_name)
    project.checkout_previous(bench_point.v2_hash)

    message = ""
    for fname in bench_point.starting_files:
        contents = project.get_file_contents(fname)
        message += f"{fname} - {contents}"

    system_message = "Suggest changes to improve the quality of this java code."
    if bench_point.necessary_context !='':
        system_message += f" Please perform the following action - {bench_point.necessary_context}"
    messages = [
        SystemMessage(system_message),
        HumanMessage(message),
    ]
    response = model.invoke(messages)
    rm.add(bench_point.ref_id, response.to_json())

rm.save()

