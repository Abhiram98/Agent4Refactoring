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
        source_code=project.get_file_contents(rel_file_path),
        source_file_path=str(rel_file_path)
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
        source_code=project.get_file_contents(rel_file_path),
        source_file_path=str(rel_file_path)
    ).compile()

    result = compiled_flow.invoke({
        'messages': []
    })
    print(result)


def test_reasoning_flink_2():
    project = pm.EvalProject('flink')
    project.checkout('1d15930275545f16a94d19c4a9b67043d5667498')

    rel_file_path = Path("flink-core/src/main/java/org/apache/flink/api/common/TaskInfo.java")
    grazie_llm = ChatGrazie(grazie_jwt_token=SecretStr(os.getenv("GRAZIE_JWT_TOKEN")),
                            client_auth_type=AuthType.APPLICATION,
                            client_url=GrazieApiGatewayUrls.STAGING,
                            profile="openai-gpt-4o-mini",
                            client_agent_name='ref-agent',
                            client_agent_version='0.1',
                            temperature=0.3
                            )
    refactoring_plan = planning.PlanningComponent(
        model=grazie_llm,
        initial_intent="Introduce the interface and default implementation of TaskInfo",
        source_code=project.get_file_contents(rel_file_path),
        source_file_path=str(rel_file_path)
    ).run()

    print(refactoring_plan)

def test_reasoning_flink_4():
    project = pm.EvalProject('flink')
    project.checkout('cdf314d30b59994283e0bbf70f350618de02118c')

    rel_file_path = Path("flink-runtime/src/main/java/org/apache/flink/runtime/"
                         "io/network/partition/hybrid/tiered/storage/SortBufferAccumulator.java")
    grazie_llm = ChatGrazie(grazie_jwt_token=SecretStr(os.getenv("GRAZIE_JWT_TOKEN")),
                            client_auth_type=AuthType.APPLICATION,
                            client_url=GrazieApiGatewayUrls.STAGING,
                            profile="openai-gpt-4o-mini",
                            client_agent_name='ref-agent',
                            client_agent_version='0.1',
                            temperature=0.3
                            )
    refactoring_plan = planning.PlanningComponent(
        model=grazie_llm,
        initial_intent="Distinguish between channel and subpartition, "
                       "by renaming appropriate elements to use the word subpartition instead of channel",
        source_code=project.get_file_contents(rel_file_path),
        source_file_path=str(rel_file_path)
    ).run()

    print(refactoring_plan)


def test_reasoning_flink_5():

    project = pm.EvalProject('flink')
    project.checkout('c65d5f18ad5dfe91ca01bfda86d36f09ba11a78a')

    rel_file_path = Path("flink-runtime/src/main/java/org/apache/"
                         "flink/runtime/io/network/partition/ResultPartitionManager.java")
    grazie_llm = ChatGrazie(grazie_jwt_token=SecretStr(os.getenv("GRAZIE_JWT_TOKEN")),
                            client_auth_type=AuthType.APPLICATION,
                            client_url=GrazieApiGatewayUrls.STAGING,
                            profile="openai-gpt-4o-mini",
                            client_agent_name='ref-agent',
                            client_agent_version='0.1',
                            temperature=0.3
                            )
    refactoring_plan = planning.PlanningComponent(
        model=grazie_llm,
        initial_intent="Modify subpartitionIndex to subpartitionIndexSet (start to end index). "
                       "Encapsulate int in special object which contains start and end index information",
        source_code=project.get_file_contents(rel_file_path),
        source_file_path=str(rel_file_path)
    ).run()

    print(refactoring_plan)