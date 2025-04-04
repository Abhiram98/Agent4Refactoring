from pydantic.v1 import BaseModel, Field
from typing import List, Callable
from langchain_core.language_models import BaseChatModel
from langgraph.graph.graph import CompiledGraph
from langgraph.graph import END, START, StateGraph, MessagesState
from langgraph.prebuilt import ToolNode
from langchain_core.messages import AIMessage, HumanMessage
from pathlib import Path

import refagent.agents.refactrix.supported_refactorings as sup_ref
import refagent.utils.intellij_server as ij


class PerformRefactoring(BaseModel):
    tools: List = Field(description="refactoring tools that are available") # TODO: Type annotate with tool type.
    retry_count: int = Field(description="how many times to allow the LLM to retry", default=3)
    model: BaseChatModel = Field(description="Langchain Chat model")
    reason: str = Field(description="Reason to perform the refactoring. Usually provided by the LM.")
    refactoring_type: sup_ref.SupportedRefactorings = Field(description="The type of refactoring to be performed.")
    rel_file_path: str = Field(description="relative file path from repo root. file to be edited.")
    ide_server: ij.IntellijServer = Field(description="ide server object. Used to open files.")

    def compile(self) -> CompiledGraph:

        def open_file(state: MessagesState):
            response = self.ide_server.try_open_file(Path(self.rel_file_path))
            if response.startswith('tool call failed '):
                create_file = self.model.invoke(
                    state['messages'] +
                    [HumanMessage(f"{response}. Would you like to create this file? Answer YES/NO.")])

                if 'YES' in create_file.content:
                    create_response = self.ide_server.create_file(Path(self.rel_file_path))
                    if create_response == 'success':
                        open_response = self.ide_server.open_file(Path(self.rel_file_path))
                        return {"messages": [HumanMessage(f"Created and opened file successfully.")]}

                return {"messages": [HumanMessage(response)]}
            return {"messages": [HumanMessage("Opened file successfully.")]}

        def successful_file_open(state: MessagesState):
            return state['messages'][-1].content == "Opened file successfully."

        def call_llm(state: MessagesState):
            # if self.retry_count <=0:
            #     return {"messages": [AIMessage("Stopping as I was already called 3 times.")]}
            model_with_tools = self.model.bind_tools(tools=self.tools)
            messages = state['messages']
            response = model_with_tools.invoke(messages)
            self.retry_count -= 1
            return {"messages": [response]}

        def success_handler(state: MessagesState):
            print("Successfully performed the refactoring")
            return {'messages': [AIMessage("Successfully performed the refactoring.")]}

        def failure_handler(state: MessagesState):
            print("Failed to perform the refactoring.")
            return {"messages": [AIMessage("Cannot perform this refactoring.")]}

        def retry_condition(state: MessagesState) -> str:
            last_message = state['messages'][-1].content
            # False -> retry
            tool_call_success = 'success' in last_message.lower()  # retry in case tool call fails.

            if tool_call_success:
                return "success_handler"

            if self.retry_count <= 0:
                # retried more than threshold times
                return "failure_handler"

            return "llm_tool"  # retry the tool call


        llm_tool_workflow = StateGraph(MessagesState)
        tool_node = ToolNode(self.tools)
        llm_tool_workflow.add_node("call_llm", call_llm)
        llm_tool_workflow.add_node("tools", tool_node)
        llm_tool_workflow.add_edge(START, "call_llm")

        def has_tool_call(state: MessagesState) -> bool:
            return len(state['messages'][-1].tool_calls) > 0
        llm_tool_workflow.add_conditional_edges("call_llm", has_tool_call, {True: "tools", False: END})
        llm_tool = llm_tool_workflow.compile()

        workflow = StateGraph(MessagesState)
        workflow.add_node("open_file", open_file)
        workflow.add_node("success_handler", success_handler)
        workflow.add_node("failure_handler", failure_handler)
        workflow.add_node("llm_tool", llm_tool)
        llm_tool.__name__ = "llm_tool"

        workflow.add_edge(START, "open_file")
        workflow.add_conditional_edges("open_file", successful_file_open,
                                       {True: "llm_tool", False: END})
        workflow.add_conditional_edges("llm_tool", retry_condition)
        workflow.add_edge("success_handler", END)
        workflow.add_edge("failure_handler", END)

        compiled_flow = workflow.compile()

        return compiled_flow

