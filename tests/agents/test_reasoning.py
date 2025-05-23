from pathlib import Path
import os
try:
    from grazie_langchain_utils.language_models.grazie import ChatGrazie
except ImportError:
    print("ChatGrazie not available. Please install `grazie-langchain-utils`.")
from pydantic.v1 import SecretStr
from grazie.api.client.gateway import GrazieApiGatewayUrls, AuthType
import refagent.agents.refactrix.planning as planning
import refagent.utils.project_manager as pm
from langchain_openai import ChatOpenAI
import refagent.utils.code_utils as code_utils
import refagent.agents.refactrix.analysis as analysis


def test_reasoning():
    project = pm.EvalProject('flink')
    project.checkout('21403e31f4761bdddf5e4e802e0e5eb9b4533202', force=True)

    rel_file_path = Path("flink-runtime/src/test/java/org/apache/flink/"
                         "runtime/scheduler/exceptionhistory/FailureHandlingResultSnapshotTest.java")
    grazie_llm = ChatGrazie(grazie_jwt_token=SecretStr(os.getenv("GRAZIE_JWT_TOKEN")),
                            client_auth_type=AuthType.APPLICATION,
                            client_url=GrazieApiGatewayUrls.STAGING,
                            profile="openai-gpt-4o-mini",
                            client_agent_name='ref-agent',
                            client_agent_version='0.1'
                            )
    refactoring_plan = planning.PlanningComponent(
        model=grazie_llm,
        initial_intent="please split up methods into reusable code fragments",
        source_code=project.get_file_contents(rel_file_path),
        source_file_path=str(rel_file_path)
    ).run()

    print(refactoring_plan)

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
    plan = planning.PlanningComponent(
        model=grazie_llm,
        initial_intent="please split up methods into reusable code fragments",
        source_code=project.get_file_contents(rel_file_path),
        source_file_path=str(rel_file_path)
    ).run()

    print(plan)


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
        source_file_path=str(rel_file_path),
        personalization_rules=["Include 'Impl' suffix for implementation classes."]
    ).run()

    print(refactoring_plan)

def test_reasoning_flink_4():
    project = pm.EvalProject('flink')
    project.checkout('cdf314d30b59994283e0bbf70f350618de02118c', force=True)

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
        initial_intent="Rename the concept Channel to Subpartition. "
                       "Rename variables, parameters, fields, classes",
        source_code=project.get_file_contents(rel_file_path),
        source_file_path=str(rel_file_path)
    ).run()

    print(refactoring_plan.json())




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


def test_reasoning_ratpack_520():
    project = pm.EvalProject('ratpack')
    file_path = Path('ratpack-core/src/main/java/ratpack/exec/Promise.java')
    file_content = project.get_file_content_by_sha('2e1847acf764b317a2f41353b6dad4e47e818d8b',
                                    str(file_path))
    v2_commit = project.git_repo.commit('0b0c2074e6359b44a4bcbbee712c7d7c9d02a31e')
    v1_commit = project.git_repo.commit('2e1847acf764b317a2f41353b6dad4e47e818d8b')
    diff = project.get_unified_file_diff_between_commits(str(v1_commit), str(v2_commit), str(file_path))
    print(diff)
    intent = """Rename Function Parameters for Clarity

When you find a method that uses a generic parameter name like function to produce one side of a Pair, rename it to be more descriptive based on what it computes:

    Use leftFunction if it computes the left value of the Pair.

    Use rightFunction if it computes the right value.

Also remember to:

    Update all internal references to the parameter.

    Update Javadoc/comments accordingly.

This improves clarity, ensures consistency with existing code (like left() and flatLeft()), and makes the API easier to understand."""

    grazie_llm = ChatGrazie(grazie_jwt_token=SecretStr(os.getenv("GRAZIE_JWT_TOKEN")),
                            client_auth_type=AuthType.APPLICATION,
                            client_url=GrazieApiGatewayUrls.STAGING,
                            profile="openai-gpt-4o-mini",
                            client_agent_name='ref-agent',
                            client_agent_version='0.1',
                            temperature=0.3
                            )
    critique_model = ChatGrazie(grazie_jwt_token=SecretStr(os.getenv("GRAZIE_JWT_TOKEN")),
                            client_auth_type=AuthType.APPLICATION,
                            client_url=GrazieApiGatewayUrls.STAGING,
                            profile="openai-o4-mini",
                            client_agent_name='ref-agent',
                            client_agent_version='0.1'
                            # temperature=0.3
                            )
    refactoring_plan = planning.PlanningComponent(
        model=critique_model,
        initial_intent=intent,
        source_code=file_content,
        source_file_path=str(file_path),
        critique_model=critique_model
    ).run()

    print(refactoring_plan)


def test_reasoning_ratpack_520():
    project = pm.EvalProject('ratpack')
    file_path = Path('ratpack-core/src/main/java/ratpack/exec/Promise.java')
    file_content = project.get_file_content_by_sha('2e1847acf764b317a2f41353b6dad4e47e818d8b',
                                                   str(file_path))
    v2_commit = project.git_repo.commit('0b0c2074e6359b44a4bcbbee712c7d7c9d02a31e')
    v1_commit = project.git_repo.commit('2e1847acf764b317a2f41353b6dad4e47e818d8b')
    diff = project.get_unified_file_diff_between_commits(str(v1_commit), str(v2_commit), str(file_path))
    print(diff)
    intent = """On line 769, `function` was changed to `rightFunction`."""

    grazie_llm = ChatGrazie(grazie_jwt_token=SecretStr(os.getenv("GRAZIE_JWT_TOKEN")),
                            client_auth_type=AuthType.APPLICATION,
                            client_url=GrazieApiGatewayUrls.STAGING,
                            profile="openai-gpt-4o-mini",
                            client_agent_name='ref-agent',
                            client_agent_version='0.1',
                            temperature=0.3
                            )
    critique_model = ChatGrazie(grazie_jwt_token=SecretStr(os.getenv("GRAZIE_JWT_TOKEN")),
                                client_auth_type=AuthType.APPLICATION,
                                client_url=GrazieApiGatewayUrls.STAGING,
                                profile="openai-o4-mini",
                                client_agent_name='ref-agent',
                                client_agent_version='0.1'
                                # temperature=0.3
                                )
    refactoring_plan = planning.PlanningComponent(
        model=critique_model,
        initial_intent=intent,
        source_code=file_content,
        source_file_path=str(file_path),
        critique_model=critique_model
    ).run()

    print(refactoring_plan)


def test_analysis_component_ratpack_500():
    project = pm.EvalProject('ratpack')
    project.checkout('1e485baf0b60c1456b3a8c53b9bd5f55e941d810')

    file_path = Path('ratpack-core/src/main/java/ratpack/handling/internal/DefaultContext.java')
    file_contents = code_utils.add_line_numbers(project.get_file_contents(file_path))

    augmented_intent = analysis.AnalysisComponent(
        source_code=file_contents,
        source_file_path=str(file_path),
        model=ChatOpenAI(model='o4-mini', temperature=1),
        initial_intent="Rename the method getPathTokens -> getPathBinding on line 290.",
        old_name="getPathTokens",
        new_name="getPathBindings"
    ).run()

    print(augmented_intent)

def test_analysis_component_ratpack_520():
    project = pm.EvalProject('ratpack')
    project.checkout('2e1847acf764b317a2f41353b6dad4e47e818d8b')

    file_path = Path('ratpack-core/src/main/java/ratpack/exec/Promise.java')
    file_contents = code_utils.add_line_numbers(project.get_file_contents(file_path))

    augmented_intent = analysis.AnalysisComponent(
        source_code=file_contents,
        source_file_path=str(file_path),
        model=ChatOpenAI(model='o4-mini', temperature=1),
        initial_intent="Rename the parameter function -> rightFunction on line 769.",
        old_name="function",
        new_name="rightFunction"
    ).run()

    print(augmented_intent)

