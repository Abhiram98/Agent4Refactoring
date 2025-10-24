import refagent.benchmark.creation.scrape_project as scrape
import refagent.utils.project_manager as pm
import os
from grazie_langchain_utils.language_models.grazie import ChatGrazie
from pydantic.v1 import SecretStr
from grazie.api.client.gateway import GrazieApiGatewayUrls, AuthType


def test_flink_1():

    project = pm.EvalProject("flink")
    grazie_llm = ChatGrazie(
        grazie_jwt_token=SecretStr(os.getenv("GRAZIE_JWT_TOKEN")),
        client_auth_type=AuthType.APPLICATION,
        client_url=GrazieApiGatewayUrls.STAGING,
        profile="openai-gpt-4o-mini",
        client_agent_name="ref-agent",
        client_agent_version="0.1",
    )

    processor = scrape.CommitProcessor(
        id_counter=1,
        commit=project.git_repo.commit("a6412b8"),
        project=project,
        model=grazie_llm,
    )

    bench_point = processor.process_commit()

    print(bench_point)


def test_flink_2():
    project = pm.EvalProject("flink")
    grazie_llm = ChatGrazie(
        grazie_jwt_token=SecretStr(os.getenv("GRAZIE_JWT_TOKEN")),
        client_auth_type=AuthType.APPLICATION,
        client_url=GrazieApiGatewayUrls.STAGING,
        profile="openai-gpt-4o",
        client_agent_name="ref-agent",
        client_agent_version="0.1",
    )

    processor = scrape.CommitProcessor(
        id_counter=1,
        commit=project.git_repo.commit("ae07b878"),
        project=project,
        model=grazie_llm,
    )

    bench_point = processor.process_commit()

    print(bench_point)


def test_kafka_1():
    project = pm.EvalProject("kafka")
    grazie_llm = ChatGrazie(
        grazie_jwt_token=SecretStr(os.getenv("GRAZIE_JWT_TOKEN")),
        client_auth_type=AuthType.APPLICATION,
        client_url=GrazieApiGatewayUrls.STAGING,
        profile="openai-gpt-4o",
        client_agent_name="ref-agent",
        client_agent_version="0.1",
    )

    processor = scrape.CommitProcessor(
        id_counter=1,
        commit=project.git_repo.commit("a1f74573895734110f309755f0a75b95046f0704"),
        project=project,
        model=grazie_llm,
    )

    bench_point = processor.process_commit()

    assert bench_point is None


def test_flink_4():
    project = pm.EvalProject("flink")
    grazie_llm = ChatGrazie(
        grazie_jwt_token=SecretStr(os.getenv("GRAZIE_JWT_TOKEN")),
        client_auth_type=AuthType.APPLICATION,
        client_url=GrazieApiGatewayUrls.STAGING,
        profile="openai-gpt-4o",
        client_agent_name="ref-agent",
        client_agent_version="0.1",
    )

    processor = scrape.CommitProcessor(
        id_counter=1,
        commit=project.git_repo.commit("2839d06559ccf2a0b63a7f61276d7bb546abca3d"),
        project=project,
        model=grazie_llm,
    )

    bench_point = processor.process_commit()

    assert bench_point is None
