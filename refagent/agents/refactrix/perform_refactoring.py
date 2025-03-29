from pydantic import BaseModel, Field
from typing import List, Callable
from langchain_core.language_models import BaseChatModel
from langgraph.graph.graph import CompiledGraph
from langgraph.graph import END, START, StateGraph, MessagesState
from langgraph.prebuilt import ToolNode
from langchain_core.messages import AIMessage

import refagent.agents.refactrix.supported_refactorings as sup_ref


class PerformRefactoring(BaseModel):
    tools: List = Field(description="refactoring tools that are available") # TODO: Type annotate with tool type.
    retry_count: int = Field(description="how many times to allow the LLM to retry", default=3)
    model: BaseChatModel = Field(description="Langchain Chat model")
    reason: str = Field(description="Reason to perform the refactoring. Usually provided by the LM.")
    refactoring_type: sup_ref.SupportedRefactorings = Field(description="The type of refactoring to be performed.")

    def compile(self) -> CompiledGraph:

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

        def retry_condition(state: MessagesState) -> bool:
            last_message = state['messages'][-1].content
            # False -> retry
            return 'success' in last_message.lower()  # retry in case tool call fails.

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
        workflow.add_node("success_handler", success_handler)
        workflow.add_node("failure_handler", failure_handler)
        workflow.add_node("llm_tool", llm_tool)
        llm_tool.__name__ = "llm_tool"

        retry_subgraph = RetrySubgraph(
            external_state_schema=MessagesState,
            condition_fn=retry_condition,
            action_node=llm_tool,
            success_node_name="success_handler",
            failure_node_name="failure_handler",
            max_steps=3,  # Retry up to 3 times
            # max_time=100_000,  # Optional timeout in milliseconds
            cleanup_on_failure=False  # Whether to clean up state on failure
        )
        workflow.add_edge(START, "retry_subgraph")

        retry_subgraph.integrate_into_graph(workflow, retry_subgraph_name="retry_subgraph")
        compiled_flow = workflow.compile()

        return compiled_flow


class RetrySubgraph:
    def __init__(self, **kwargs):
        raise Exception("To be implemented")

    def integrate_into_graph(self, workflow: StateGraph, retry_subgraph_name: str):
        raise Exception("To be implemented")