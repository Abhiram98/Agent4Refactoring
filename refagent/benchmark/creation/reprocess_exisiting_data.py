import os
from typing import List

from grazie_langchain_utils.language_models.grazie import ChatGrazie
from pydantic.v1 import SecretStr

import refagent
import refagent.benchmark.creation.scrape_project as scrape
import refagent.benchmark.load as bm_load
import refagent.utils.project_manager as pm
from grazie.api.client.gateway import GrazieApiGatewayUrls, AuthType
import langsmith
import json


def process_benchmark() -> List[bm_load.BenchmarkItem]:
    new_data = []
    for bench_point in bench_data:
        project = pm.EvalProject(bench_point.project_name)

        processor = scrape.CommitProcessor(
            id_counter=bench_point.ref_id - 1,
            commit=project.git_repo.commit(bench_point.v2_hash),
            project=project,
            model=grazie_llm,
        )

        new_bench = processor.process_commit()
        new_data.append(new_bench)
    return new_data


if __name__ == "__main__":

    bench_data = bm_load.load_benchmark(refagent.benchmark_lite_json)
    grazie_llm = ChatGrazie(
        grazie_jwt_token=SecretStr(os.getenv("GRAZIE_JWT_TOKEN")),
        client_auth_type=AuthType.APPLICATION,
        client_url=GrazieApiGatewayUrls.STAGING,
        profile="openai-gpt-4o-mini",
        client_agent_name="ref-agent",
        client_agent_version="0.1",
    )
    with langsmith.trace(name="reprocess benchmark", tags=["reprocess"]) as tracer:
        new_benchmark = process_benchmark()

    with open(str(refagent.benchmark_lite_file) + "improved", "w") as f:
        json.dump([i.to_json() for i in new_benchmark], f, indent=4)
