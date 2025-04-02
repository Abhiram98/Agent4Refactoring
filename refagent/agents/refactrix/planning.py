import refagent
from pydantic.v1 import BaseModel, Field
from typing import Callable

from langgraph.graph import MessagesState
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage, AIMessage
from langchain_core.language_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph
from langgraph.graph import StateGraph, START, END
from langchain_core.tools import tool, BaseTool


class PlanningComponent(BaseModel):
    initial_intent: str = Field(description="initial intent from the user")
    # developer_callback: Callable = Field(description="the function to call to get further"
    #                                                  " clarifications from the developer.")
    model: BaseChatModel = Field(description="model to use to generate the plan")
    source_code: str = Field(description="source code to work with")

    def compile(self) -> CompiledStateGraph:
        def generate_plan(messages: MessagesState):

            messages1 = [
                SystemMessage("Please generate a detailed step by step plan to "
                              f"perform the following: {self.initial_intent}. "
                              f"Please provide a plan ONLY to perform refactorings. "
                              f"Assume that other action steps will be taken care of by the developer."
                              f"Make sure that your plan is actionable on the given code. "
                              f"Do not include generic steps in this plan. "),
                HumanMessage(self.source_code)
            ]
            response = self.model.invoke(
                messages1
            )

            return {'messages': [response]}

        def summarize_plan(messages: MessagesState):
            # use the last but one message, because that was tehe accepted plan
            return {'messages': messages['messages'][-2]}

        def critique_plan(messages: MessagesState):
            response = self.model.invoke(
                messages['messages'] +
                [HumanMessage('Please review the above plan. '
                              'If there are any steps which are not actionable '
                              'or specific to the code, highlight them. '
                              'If there are any steps which are generic (applicable to any code), highlight them. '
                              'Finally, use the word REJECT/ACCEPT to '
                              'reject or accept the plan based on the above criteria.')]
            )
            return {'messages': [response]}
        def should_replan(messages: MessagesState):
            return 'REJECT' in messages['messages'][-1].content


        workflow = StateGraph(MessagesState)
        workflow.add_node("generate_plan", generate_plan)
        workflow.add_node("summarize_plan", summarize_plan)
        workflow.add_node("critique_plan", critique_plan)
        workflow.add_edge(START, "generate_plan")
        workflow.add_edge("generate_plan", "critique_plan")
        workflow.add_conditional_edges("critique_plan", should_replan,
                                       {True: "generate_plan", False: "summarize_plan"})
        # workflow.add_edge("generate_plan", "summarize_plan")

        workflow.add_edge("summarize_plan", END)

        compiled_flow = workflow.compile()
        return compiled_flow

    def run(self):
        compiled_flow = self.compile()
        final_messages = compiled_flow.invoke({'messages':[]})
        return final_messages['messages'][-2].content
