from langgraph.graph.state import CompiledStateGraph
from typing_extensions import Literal, TypedDict
from langchain_core.messages import HumanMessage, SystemMessage
from typing import Optional
from langgraph.graph import StateGraph, START, END
# from IPython.display import Image, display
from enum import Enum
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
import refagent
import os
from pathlib import Path
# from pydantic.v1 import Field, BaseModel, PrivateAttr
from pydantic import Field, BaseModel, PrivateAttr
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.graph import MessagesState
from langgraph.graph.graph import CompiledGraph
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage, AIMessage
from langchain_core.language_models import BaseChatModel
import requests

import refagent.utils.intellij_server as ij
import refagent.utils.code_utils as code_utils
import refagent.agents.supported_refactorings as sup_refs
import refagent.agents.perform_refactoring as perform_ref

class Agent(BaseModel):
    ide_server: ij.IntellijServer = Field(description="the url of the ide, to invoke")
    model_name: str = Field(description="model name")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._files_changed: list[Path] = []
        self.source_code: str = ""


    def create_model(self) -> BaseChatModel:
        return ChatOpenAI(self.model_name)

    def files_changed(self) -> list[Path]:
        return self._files_changed


    async def run(self, initial_intent: str, starting_file: str):
        FAKE_LLM = True  # Change to False to invoke the real LLM.
        print("Starting refactoring-agent")
        initial_message = initial_intent
        self.source_code = starting_file  # TODO: Read the starting file

        model = self.create_model()

        graph = self.compile_graph(model=model)
        final_state = await graph.ainvoke(  # TODO: edit these messages
            {
                "messages": [
                    SystemMessage("You are an expert developer who makes refactoring suggestions to "
                                  "improve the quality of the given code. ONLY make TOOL CALLS to perform actions."),
                ]
            },
            config={"configurable": {"thread_id": 42}}
        )
        print("Final message: ", final_state["messages"][-1].content)
        return final_state["messages"][-1].content



    async def update_source_code(self) -> bool:
        """Call the environment to fetch the current version
         of the source code under operation"""

        new_source_code = await self.ide_server.call_tool(
            "get_source_code",
            file_path=""
        )
        source_code_changed = False
        if self.source_code != new_source_code:
            source_code_changed = True
        self.source_code = new_source_code
        return source_code_changed

    def get_available_tools(self,
                            refactoring_type: sup_refs.SupportedRefactorings) -> list: # TODO: annotate return type with tools list.
        print(refactoring_type)

        # TODO: return the right tools for the job.

        if refactoring_type == sup_refs.SupportedRefactorings.EXTRACT_METHOD:
            return []
        elif refactoring_type == sup_refs.SupportedRefactorings.RENAME:
            return []
        elif refactoring_type == sup_refs.SupportedRefactorings.CUSTOM:
            return []
        # elif refactoring_type == refagent_utils.SupportedRefactorings.MOVE:
        #     # tools.append(move_method)
        #     pass
        else:
            raise Exception("Unknown refactoring type.")

    def compile_graph(self, model) -> CompiledStateGraph:
        """Compile the graph with the given model"""

        @tool
        def choose_refactoring(
                refactoring_type: sup_refs.SupportedRefactorings = Field(
                    description=f"select the type of refactoring. "
                                f"Choose `{sup_refs.SupportedRefactorings.CUSTOM.value}"
                                f" to perform refactorings not in the list.`"),
                reason: str = Field(description="explanation for why the refactoring should be carried out")
        ):
            """
            Select a refactoring action to perform and provide a reason.
            """
            # NOTE: This tools doesn't actually get called.
            # It is used to make sure the LLM output is formatted
            print(refactoring_type)
            print(reason)

        async def curate_tests(state: MessagesState):
            """Find appropriate test class, run the test, and note which ones are passing.
            This is useful to verify that refactoring hasn't broken the code later."""

            await self.ide_server.call_tool("curate_test_class", file_path="")

        async def run_tests(state: MessagesState):
            # TODO: add arguments, if necessary
            await self.ide_server.call_tool("run_test_class", file_path="")

        def select_refactoring(state: MessagesState):
            """First LLM call to generate refactoring ideas"""
            self.update_source_code()
            if self.iterations >= 3:  # stop after 3 iterations
                return
            llm_with_tools = model.bind_tools([
                choose_refactoring
            ])
            extra_message = "" if self.iterations == 0 else "Here's the modified source code: \n"
            new_messages = state['messages'] + [HumanMessage(content=
                                                             extra_message +
                                                             code_utils.add_line_numbers(self.source_code))]
            # try:
            response = llm_with_tools.invoke(
                new_messages
            )
            # except Exception as e:
            #     raise e
            self.iterations += 1
            new_messages.append(response)
            return {"messages": new_messages}

        async def perform_selected_refactoring(state: MessagesState):
            """Perform refactoring in retry loop"""
            # tools_by_name = {"choose_refactoring": choose_refactoring}
            result = []
            for tool_call in state["messages"][-1].tool_calls:
                updated = await self.update_source_code()
                if updated:
                    # Change human message which has the source code.
                    state['messages'][1] = HumanMessage(
                        code_utils.add_line_numbers(self.source_code))

                refactoring_type = sup_refs.SupportedRefactorings(
                    tool_call['args']['refactoring_type'])
                reason = tool_call['args']['reason']
                tools = await self.get_tools(self.get_available_tools(refactoring_type))
                perform_refactoring_graph = perform_ref.PerformRefactoring(
                    tools=tools,
                    model=model,
                    reason=reason,
                    refactoring_type=refactoring_type
                ).compile()
                messages = state['messages'][:-1] + [
                    AIMessage(f"I would like to perform an {refactoring_type.value}, because: {reason}")]
                observation = await perform_refactoring_graph.ainvoke({"messages": messages})
                last_message = observation['messages'][-1]
                result.append(ToolMessage(content=last_message.content,
                                          tool_call_id=tool_call["id"],
                                          name='choose_refactoring'))
            messages = state["messages"]
            messages += result
            # return {"messages_state": {"messages": messages}}
            return {"messages": messages}

        workflow = StateGraph(MessagesState)
        # Add nodes
        workflow.add_node("curate_tests", curate_tests)
        workflow.add_node("select_refactoring", select_refactoring)
        # select_refactoring_tool = ToolNode([choose_refactoring])
        workflow.add_node("perform_refactoring", perform_selected_refactoring)

        # Add edges to connect nodes
        # workflow.add_edge(START, "select_refactoring")
        workflow.add_edge(START, "curate_tests")
        workflow.add_edge("curate_tests", "select_refactoring")

        def has_tool_call(state: MessagesState) -> bool:
            return len(state['messages'][-1].tool_calls) != 0

        workflow.add_conditional_edges(
            "select_refactoring", has_tool_call, {True: "perform_refactoring", False: END}
        )

        workflow.add_edge("perform_refactoring", "select_refactoring")

        # Compile
        graph = workflow.compile()
        return graph