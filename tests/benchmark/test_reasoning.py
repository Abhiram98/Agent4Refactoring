from pathlib import Path
import os
from grazie_langchain_utils.language_models.grazie import ChatGrazie
from pydantic.v1 import SecretStr
from grazie.api.client.gateway import GrazieApiGatewayUrls, AuthType

import refagent.agents.refactrix.planning as planning
import refagent.utils.project_manager as pm


def test_reasoning():
    project = pm.EvalProject('flink')
    project.checkout('21403e31f4761bdddf5e4e802e0e5eb9b4533202')

    rel_file_path = Path("flink-runtime/src/test/java/org/apache/flink/"
                         "runtime/scheduler/exceptionhistory/FailureHandlingResultSnapshotTest.java")
    grazie_llm = ChatGrazie(grazie_jwt_token=SecretStr(os.getenv("GRAZIE_JWT_TOKEN")),
                            client_auth_type=AuthType.APPLICATION,
                            client_url=GrazieApiGatewayUrls.STAGING,
                            profile="openai-gpt-4o-mini",
                            client_agent_name='ref-agent',
                            client_agent_version='0.1'
                            )
    compiled_flow = planning.PlanningComponent(
        model=grazie_llm,
        initial_intent="please split up methods into reusable code fragments",
        source_code=project.get_file_contents(rel_file_path)
    ).compile()

    result = compiled_flow.invoke({
        'messages': []
    })
    print(result)

def test_reasoning2():
    project = pm.EvalProject('flink')
    project.checkout('21403e31f4761bdddf5e4e802e0e5eb9b4533202')

    rel_file_path = Path("flink-runtime/src/test/java/org/apache/flink/"
                         "runtime/scheduler/exceptionhistory/ExceptionHistoryEntryTest.java")
    grazie_llm = ChatGrazie(grazie_jwt_token=SecretStr(os.getenv("GRAZIE_JWT_TOKEN")),
                            client_auth_type=AuthType.APPLICATION,
                            client_url=GrazieApiGatewayUrls.STAGING,
                            profile="openai-gpt-4o-mini",
                            client_agent_name='ref-agent',
                            client_agent_version='0.1'
                            )
    compiled_flow = planning.PlanningComponent(
        model=grazie_llm,
        initial_intent="please split up methods into reusable code fragments",
        source_code=project.get_file_contents(rel_file_path)
    ).compile()

    result = compiled_flow.invoke({
        'messages': []
    })
    print(result)
