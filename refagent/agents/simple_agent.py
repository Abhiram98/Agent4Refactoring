import os

from typing import Literal
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
# from langgraph.prebuilt import create_react_agent
from langgraph.graph import END, START, StateGraph, MessagesState
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
# from langchain_ollama import ChatOllama

from grazie.api.client.endpoints import GrazieApiGatewayUrls
from grazie.api.client.gateway import AuthType
try:
    from grazie_langchain_utils.language_models.grazie import ChatGrazie
except ImportError:
    print("ChatGrazie not available. Please install `grazie-langchain-utils`.")

# from pydantic import BaseModel, Field, root_validator

import refagent.benchmark.load as bm_load
import refagent.utils.project_manager as pm
import refagent

from pydantic import SecretStr

# Define the tools for the agent to use

current_project: pm.EvalProject
os.environ["OPENAI_API_KEY"] = refagent.OPENAI_KEY


class Agent:
    """Simple refactoring agent."""

    # model = ChatGrazie(grazie_jwt_token=os.getenv("GRAZIE_JWT_TOKEN"),
    #                    client_auth_type=AuthType.APPLICATION,
    #                    client_url=GrazieApiGatewayUrls.STAGING,
    #                    profile="openai-gpt-4o"
    #                    )
    # model = ChatGrazie(grazie_jwt_token=SecretStr(os.getenv("GRAZIE_JWT_TOKEN")),
    #                    client_auth_type=AuthType.APPLICATION,
    #                    client_url=GrazieApiGatewayUrls.STAGING,
    #                    profile="openai-gpt-4o-mini",
    #                    client_agent_name='vanilla-ref-agent',
    #                    client_agent_version='0.1'
    #                    )

    model = ChatOpenAI(model="gpt-4o-mini")
    # model = ChatOllama(model="llama3.1", temperature=0)

    def __init__(self):
        self.files_changed = []

    def run(self, bench_point: bm_load.BenchmarkItem) -> list[pm.MyDiff]:
        """run the agent for the benchmark_point"""
        global current_project
        project = pm.EvalProject(bench_point.project_name)
        current_project = project

        @tool
        def replace_file_contents(file_path: str, new_content: str) -> str:
            """Replace the entire contents of `file_path` with the `new_content`."""
            print(f"replacing file contents - {file_path}")
            status = current_project.replace_contents(file_path, new_content)
            self.files_changed.append(file_path)
            return 'SUCCESS' if status else 'FAIL'

        @tool
        def read_file_contents(file_path: str) -> str:
            """Read the contents of the `file_path` file."""
            print(f"reading file contents - {file_path}")
            return current_project.get_file_contents(file_path)

        @tool
        def ls(directory_path: str) -> str:
            """Run the ls command in the `directory_path` directory."""
            print(f"performing ls: {directory_path}")
            return str(current_project.run_ls(directory_path))

        tools = [replace_file_contents, ls, replace_file_contents]

        tool_node = ToolNode(tools)

        model = Agent.model.bind_tools(tools)

        # Define the function that determines whether to continue or not
        def should_continue(state: MessagesState) -> Literal["tools", END]:
            messages = state['messages']
            last_message = messages[-1]
            # If the LLM makes a tool call, then we route to the "tools" node
            if last_message.tool_calls:
                return "tools"
            # Otherwise, we stop (reply to the user)
            return END

        # Define the function that calls the model
        def call_model(state: MessagesState):
            messages = state['messages']
            response = model.invoke(messages)
            # We return a list, because this will get added to the existing list
            if 'spent' in response.additional_kwargs:
                del response.additional_kwargs['spent']
            return {"messages": [response]}

        # Define a new graph
        workflow = StateGraph(MessagesState)

        # Define the two nodes we will cycle between
        workflow.add_node("agent", call_model)
        workflow.add_node("tools", tool_node)

        # Set the entrypoint as `agent`
        # This means that this node is the first one called
        workflow.add_edge(START, "agent")

        # We now add a conditional edge
        workflow.add_conditional_edges(
            # First, we define the start node. We use `agent`.
            # This means these are the edges taken after the `agent` node is called.
            "agent",
            # Next, we pass in the function that will determine which node is called next.
            should_continue,
        )

        # We now add a normal edge from `tools` to `agent`.
        # This means that after `tools` is called, `agent` node is called next.
        workflow.add_edge("tools", 'agent')

        # Initialize memory to persist state between graph runs
        checkpointer = MemorySaver()

        # Finally, we compile it!
        # This compiles it into a LangChain Runnable,
        # meaning you can use it as you would any other runnable.
        # Note that we're (optionally) passing the memory when compiling the graph
        app = workflow.compile(checkpointer=checkpointer)

        system_message = "Suggest changes to improve the quality of this java code. "
        if bench_point.necessary_context != '':
            system_message += f"Please perform the following action - {bench_point.necessary_context}"
        if bench_point.hint != '':
            system_message += f". {bench_point.hint}\n"
        system_message += "ONLY USE TOOL CALLS to perform changes. "

        message = ""
        for fname in bench_point.starting_files:
            contents = project.get_file_contents(fname)
            message += f"{fname}: {contents}"

        # Use the agent
        final_state = app.invoke(
            {"messages":
                 [{"role": "system", "content": system_message},
                  {"role": "user", "content": message}]
             },
            config={"configurable": {"thread_id": 42}, "recursion_limit": 10}
        )
        print(final_state["messages"][-1].content)

        return project.get_unstaged_changes()
