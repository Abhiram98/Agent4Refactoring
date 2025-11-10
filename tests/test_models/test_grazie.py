import os
import refagent

from grazie.api.client.endpoints import GrazieApiGatewayUrls
from grazie.api.client.gateway import AuthType

try:
    from grazie_langchain_utils.language_models.grazie import ChatGrazie
except ImportError:
    print("ChatGrazie not available. Please install `grazie-langchain-utils`.")
from grazie_langchain_utils.callbacks import GrazieInfoCallbackHandler
from pydantic.v1 import SecretStr
from langchain_core.messages import SystemMessage, AIMessage, ToolMessage, HumanMessage


def test_grazie():
    grazie_llm = ChatGrazie(
        grazie_jwt_token=SecretStr(os.getenv("GRAZIE_JWT_TOKEN")),
        client_auth_type=AuthType.APPLICATION,
        client_url=GrazieApiGatewayUrls.PRODUCTION,
        profile="openai-gpt-4o-mini",
        client_agent_name="ref-agent",
        client_agent_version="0.1",
    )

    print(grazie_llm.invoke("how can langsmith help with testing?"))


def test_grazie_with_tool_messages():
    messages = [
        SystemMessage(
            content="You are a calculator. ONLY make TOOL CALLS to perform actions.",
            id="17f70ce6-ae0e-478b-800f-dbda1b4d4816",
        ),
        HumanMessage(
            content="Compute 124 + 3124 + 12", id="5e149bc6-9e85-4fb5-a668-6521047527f7"
        ),
        AIMessage(
            content="Calling addition tool",
            id="run-50842ee2-b08d-4cc1-bc8c-3a4cfb224384-0",
            tool_calls=[
                {
                    "name": "add",
                    "args": {"operand1": "124", "operand2": "3124"},
                    "id": "call_add_676c9a12",
                    "type": "tool_call",
                }
            ],
            additional_kwargs={"function_call": "add"},
        ),
        ToolMessage(
            content="Sum is 3248",
            id="e6600920-11a8-4e98-90d5-84d6e107e86f",
            tool_call_id="call_add_676c9a12",
            name="add",
        ),
        HumanMessage(content="please continue your computation"),
    ]

    grazie_llm = ChatGrazie(
        grazie_jwt_token=SecretStr(os.getenv("GRAZIE_JWT_TOKEN")),
        client_auth_type=AuthType.APPLICATION,
        client_url=GrazieApiGatewayUrls.PRODUCTION,
        profile="openai-gpt-4o-mini",
        client_agent_name="ref-agent",
        client_agent_version="0.1",
    )

    print(grazie_llm.invoke(messages))


def test_grazie_streaming():
    grazie_llm = ChatGrazie(
        grazie_jwt_token=SecretStr(os.getenv("GRAZIE_JWT_TOKEN")),
        client_auth_type=AuthType.APPLICATION,
        client_url=GrazieApiGatewayUrls.PRODUCTION,
        profile="openai-gpt-4o-mini",
        client_agent_name="ref-agent",
        client_agent_version="0.1",
    )
    all_chunks = []
    for chunk in grazie_llm.stream("how can langsmith help with testing?"):
        all_chunks.append(chunk.content)
        print(chunk)
    print(f"{len(all_chunks)=}")
