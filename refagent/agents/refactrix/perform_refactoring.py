from pydantic.v1 import BaseModel, Field, PrivateAttr
from typing import List, Callable
from langchain_core.language_models import BaseChatModel
from langgraph.graph.graph import CompiledGraph
from langgraph.graph import END, START, StateGraph, MessagesState
from langgraph.prebuilt import ToolNode
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pathlib import Path

import refagent.agents.refactrix.supported_refactorings as sup_ref
import refagent.utils.intellij_server as ij


class PerformRefactoring(BaseModel):
    tools: List = Field(description="refactoring tools that are available") # TODO: Type annotate with tool type.
    retry_count: int = Field(description="how many times to allow the LLM to retry", default=2)
    model: BaseChatModel = Field(description="Langchain Chat model")
    reason: str = Field(description="Reason to perform the refactoring. Usually provided by the LM.")
    refactoring_type: sup_ref.SupportedRefactorings = Field(description="The type of refactoring to be performed.")
    rel_file_path: str = Field(description="relative file path from repo root. file to be edited.")
    ide_server: ij.IntellijServer = Field(description="ide server object. Used to open files.")
    refactoring_success: bool = Field(description="whether the refactoring was successful or not.", default=False)
    _file_open_status: bool = PrivateAttr(default=False)
    _active_tool_call: List = PrivateAttr(default="")
    _retry_iteration: int = PrivateAttr(default=1)
    _performed_refactorings: List = PrivateAttr(default=[])

    def get_tool_call_str(self):
        tool_call = self._active_tool_call[0]
        name = tool_call['name']
        args = ", ".join([f"{k}={v}" for k, v in tool_call['args'].items()])
        tool_call_str = f"{name}({args})"
        return tool_call_str

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
                        self._file_open_status = True
                        open_response = self.ide_server.open_file(Path(self.rel_file_path))
                        return {"messages": [HumanMessage(f"Created and opened file successfully. "
                                                          f"You are now editing {self.rel_file_path}")]}

                return {"messages": [HumanMessage(response)]}
            self._file_open_status = True
            return {"messages": [HumanMessage(f"Opened file successfully. "
                                              f"You are now editing {self.rel_file_path}")]}

        def successful_file_open(state: MessagesState):
            return self._file_open_status

        def call_llm(state: MessagesState):
            # if self.retry_count <=0:
            #     return {"messages": [AIMessage("Stopping as I was already called 3 times.")]}
            if self._retry_iteration > 1:
                state['messages'][-1].content += (f"The tool call {self.get_tool_call_str()} is failing. "
                                                  f"DO NOT MAKE THE SAME TOOL CALL AGAIN.")
            model_with_tools = self.model.bind_tools(tools=self.tools)
            messages = state['messages']
            response = model_with_tools.invoke(messages)
            self._retry_iteration += 1
            return {"messages": [response]}

        def success_handler(state: MessagesState):
            print("Successfully performed the following refactoring -> "
                  f"{self._active_tool_call}")
            self.refactoring_success = True
            success_msg = state['messages'][-1].content

            tool_call_status = str(self._active_tool_call)
            if 'replace_file_contents' in str(self._active_tool_call):
                tool_call_status = "replaced file contents."
            final_message = ("Successfully performed the refactoring. "
                             f"{tool_call_status}")
            if success_msg != 'success':
                final_message += success_msg
            return {'messages': [HumanMessage(final_message)]}

        def failure_handler(state: MessagesState):
            print("Failed to perform the refactoring.")
            tool_call_str = self.get_tool_call_str()
            return {"messages": [HumanMessage("Cannot perform this refactoring. "
                                              f"{tool_call_str} failed. "
                                              f"Reason: {state['messages'][-1].content}"
                                              f"CALL the TOOL differently, next time.")]}

        def retry_condition(state: MessagesState) -> str:
            last_message = state['messages'][-1].content
            # False -> retry
            tool_call_success = 'success' in last_message.lower()  # retry in case tool call fails.

            if tool_call_success:
                return "success_handler"

            if self._retry_iteration > self.retry_count:
                # retried more than threshold times
                return "failure_handler"

            return "llm_tool"  # retry the tool call


        llm_tool_workflow = StateGraph(MessagesState)
        tool_node = ToolNode(self.tools)
        llm_tool_workflow.add_node("call_llm", call_llm)
        llm_tool_workflow.add_node("tools", tool_node)
        llm_tool_workflow.add_edge(START, "call_llm")

        def has_tool_call(state: MessagesState) -> bool:
            if len(state['messages'][-1].tool_calls) > 0:
                if 'replace_file_contents' in str(state['messages'][-1].tool_calls[0]):
                    self._active_tool_call = [f"Replaced file contents of {self.rel_file_path}."]
                else:
                    self._active_tool_call = state['messages'][-1].tool_calls
                return True
            return False

        llm_tool_workflow.add_conditional_edges("call_llm",
                                                has_tool_call,
                                                {True: "tools", False: END})
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

    def get_performed_refactorings(self, messages: MessagesState):
        tool_call_map = {}
        for message in messages['messages']:
            if hasattr(message, 'tool_calls') and message.tool_calls:
                for tool_call in message.tool_calls:
                    tool_call_map[tool_call['id']] = {"tool_call": tool_call}
        for message in messages['messages']:
            if isinstance(message, ToolMessage):
                tool_call_map[message.tool_call_id] = message.content

        self._performed_refactorings = list(tool_call_map.values())
        return self._performed_refactorings

