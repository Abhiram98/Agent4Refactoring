import refagent
from pydantic.v1 import BaseModel, Field, PrivateAttr
from typing import Callable, List, Optional
from langchain_core.output_parsers import PydanticOutputParser

from langgraph.graph import MessagesState
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage, AIMessage
from langchain_core.language_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph
from langgraph.graph import StateGraph, START, END
from langchain_core.tools import tool, BaseTool

import refagent.agents.refactrix.supported_refactorings as sup_ref


class PlanningStep(BaseModel):
    """An actionable step to improve the code-quality."""

    # step_number: int = Field(description="The ")
    reason: str = Field(description="The reason why this action should be applied.")
    final_code: str = Field(description="The improved, modified version of the source code.")
    refactoring_type: sup_ref.SupportedRefactorings = Field(
        description="The type of change that is needed. "
        "Please refer to the Fowler catalog of refactorings and pick one.")
    file_path: str = Field(description="The path to the source code where the change should be applied.")



class RefactoringPlan(BaseModel):
    steps: List[PlanningStep] = Field(description="An ordered list of steps to carry out the plan")

# structured_llm = llm.with_structured_output(Joke)


class PlanningComponent(BaseModel):
    initial_intent: str = Field(description="initial intent from the user")
    # developer_callback: Callable = Field(description="the function to call to get further"
    #                                                  " clarifications from the developer.")
    model: BaseChatModel = Field(description="model to use to generate the plan")
    source_code: str = Field(description="source code to work with")
    _ref_plan: Optional[RefactoringPlan] = PrivateAttr(default=None)

    def compile(self) -> CompiledStateGraph:
        def generate_plan(messages: MessagesState):
            parser = PydanticOutputParser(pydantic_object=RefactoringPlan)
            messages1 = [
                SystemMessage("Please generate a detailed step by step plan to "
                              f"perform the following: {self.initial_intent}. "
                              f"Please provide a plan ONLY to perform refactorings. "
                              f"Assume that other action steps will be taken care of by the developer."
                              f"Make sure that your plan is actionable on the given code. "
                              f"Do not include generic steps in this plan. "
                              f"{parser.get_format_instructions()}"
                              f"Here is some documentation for each refactoring type: {sup_ref.documentation}"),
                HumanMessage(self.source_code)
            ]
            # Set up a parser + inject instructions into the prompt template.

            response = self.model.invoke(
                messages1
            )
            self._ref_plan = parser.invoke(response)

            return {'messages': messages1 + [response]}

        def critique_plan_steps(messages: MessagesState):
            parser = PydanticOutputParser(pydantic_object=PlanningStep)

            for i, cur_step in enumerate(self._ref_plan.steps):
                previous_steps = self._ref_plan.steps[:i+1]
                step_messages = "\n".join([f"step {i}: {s}" for i, s in enumerate(previous_steps)])
                messages_  = [
                    SystemMessage(f"You are a expert developer who adds details to an existing refactoring plan."),
                    HumanMessage(self.source_code),
                    AIMessage(f"Here are the steps in the refactoring plan: {step_messages}"),
                    HumanMessage(f"Please critique the last step, and improve it: {cur_step}. "
                                 f"by answering the following question:"
                                 f"Are there any missing details in the code? If yes, fill them out."
                                 f"{parser.get_format_instructions()}")
                ]
                response = self.model.invoke(messages_)
                new_step = parser.invoke(response)
                self._ref_plan.steps[i] = new_step

            return {}

        workflow = StateGraph(MessagesState)
        workflow.add_node("generate_plan", generate_plan)
        workflow.add_node("critique_plan", critique_plan_steps)
        workflow.add_edge(START, "generate_plan")
        workflow.add_edge("generate_plan", "critique_plan")
        workflow.add_edge("critique_plan", END)

        compiled_flow = workflow.compile()
        return compiled_flow

    def run(self) -> RefactoringPlan:
        compiled_flow = self.compile()
        messages = compiled_flow.invoke({'messages': []})
        return self._ref_plan


class NaivePlanningComponent(BaseModel):
    initial_intent: str = Field(description="initial intent from the user")
    # developer_callback: Callable = Field(description="the function to call to get further"
    #                                                  " clarifications from the developer.")
    model: BaseChatModel = Field(description="model to use to generate the plan")
    source_code: str = Field(description="source code to work with")
    _ref_plan: Optional[RefactoringPlan] = PrivateAttr(default=None)

    def compile(self) -> CompiledStateGraph:
        def generate_plan(messages: MessagesState):

            parser = PydanticOutputParser(pydantic_object=RefactoringPlan)
            messages1 = [
                SystemMessage("Please generate a detailed step by step plan to "
                              f"perform the following: {self.initial_intent}. "
                              f"Please provide a plan ONLY to perform refactorings. "
                              f"Assume that other action steps will be taken care of by the developer."
                              f"Make sure that your plan is actionable on the given code. "
                              f"Do not include generic steps in this plan. "
                              f"{parser.get_format_instructions()}"
                              f"Here is some documentation for each refactoring type: {sup_ref.documentation}"),
                HumanMessage(self.source_code)
            ]
            # Set up a parser + inject instructions into the prompt template.

            response = self.model.invoke(
                messages1
            )
            self._ref_plan = parser.invoke(response)

            return {'messages': [response]}


        workflow = StateGraph(MessagesState)
        workflow.add_node("generate_plan", generate_plan)
        workflow.add_edge(START, "generate_plan")
        workflow.add_edge("generate_plan", END)

        compiled_flow = workflow.compile()
        return compiled_flow

    def run(self) -> RefactoringPlan:
        compiled_flow = self.compile()
        messages = compiled_flow.invoke({'messages':[]})
        return self._ref_plan
