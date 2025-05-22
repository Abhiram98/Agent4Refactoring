from pydantic.v1 import BaseModel, Field, PrivateAttr
from typing import List, Optional, Type
from langchain_core.output_parsers import PydanticOutputParser, JsonOutputParser

from langgraph.graph import MessagesState
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from langchain_core.language_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph
from langgraph.graph import StateGraph, START, END
from langchain_core.tools import BaseTool

import refagent.agents.refactrix.tools as tools
import refagent.utils.tool_documentation as td
import refagent.agents.refactrix.supported_refactorings as sup_ref


class PlanningStep(BaseModel):
    """An actionable step to improve the code-quality."""

    # step_number: int = Field(description="The ")
    reason: str = Field(description="The reason why this action should be applied.")
    final_code: str = Field(description="The improved, modified version of the source code.")
    execution_details: str = Field(description="Details about what needs to change. "
                                               "E.g. rename variable x->index, or "
                                               "move method `bark` to target class `Dog`")
    refactoring_type: sup_ref.SupportedRefactorings = Field(
        description="The type of change that is needed. "
        "Please refer to the Fowler catalog of refactorings and pick one.")
    file_path: str = Field(description="The path to the source code where the "
                                       "refactoring operation should be triggered.")



class RefactoringPlan(BaseModel):
    steps: List[PlanningStep] = Field(description="An ordered list of steps to carry out the plan")

# structured_llm = llm.with_structured_output(Joke)


class Planner(BaseModel):
    source_file_path: str = Field(description="the file path to the starting source code.")
    source_code: str = Field(description="source code to work with")
    initial_intent: str = Field(description="initial intent from the user")

    def run(self) -> RefactoringPlan:
        return RefactoringPlan(steps=[])

    @property
    def generation_system_message(self) -> SystemMessage:
        parser = PydanticOutputParser(pydantic_object=RefactoringPlan)
        documentation_str = "\n".join([f"{k.value}: {v}" for k,v in sup_ref.documentation.items()])

        return SystemMessage( "You are an expert developer using a powerful IDE IntelliJ IDEA, "
                              "capable of performing refactoring. "
                              "Please generate a step by step plan of IDE refactoring actions to "
                              f"perform the following: {self.initial_intent}. "
                              f"Please provide a plan ONLY to perform refactorings. "
                              f"Assume that other action steps will be taken care of by the developer."
                              f"Make sure that your plan is actionable on the given code. "
                              f"Do not include generic steps in this plan. "
                              f"{parser.get_format_instructions()}"
                              f"Here is some documentation for each refactoring type: {documentation_str}")


class PlanningComponent(Planner):
    model: BaseChatModel = Field(description="model to use to generate the plan")
    _ref_plan: Optional[RefactoringPlan] = PrivateAttr(default=None)
    _generation_count: int = PrivateAttr(default=0)
    _tools: dict[str, BaseTool] = PrivateAttr(default=tools.RefactoringToolProvider(ide_server=None).get())

    def compile(self) -> CompiledStateGraph:
        def generate_plan(messages: MessagesState):
            parser = PydanticOutputParser(pydantic_object=RefactoringPlan)
            self._generation_count += 1
            # Set up a parser + inject instructions into the prompt template.
            new_messages = messages['messages']
            if self._generation_count > 1:
                new_messages += [HumanMessage("FOLLOW THE CRITICAL ADVICE, and MODIFY your plan accordingly!")]
            response = self.model.invoke(
                new_messages
            )
            self._ref_plan = parser.invoke(response)
            return {'messages': [response]}

        def critique_plan(messages: MessagesState):

            rules_msg = ""
            response = self.model.with_config(temperature=0.3).invoke(
                [
                    SystemMessage("You are an expert developer who critiques refactoring plans. "
                                  "You are aware of refactoring actions available in powerful IDEs "
                                  f"like IntelliJ IDEA. {rules_msg}"
                                  "Critique the quality of the given plans. "
                                  f"Here is the refactoring intent: {self.initial_intent}. \n"
                                  "Keep a look out for the following: \n"
                                  "1. Renames that deviate from the original intent \n"
                                  "2. Redundant refactoring suggestions \n"
                                  "3. Unecessary and large amount of steps (>10 step plans) \n"
                                  "At the end of your critique, "
                                  "use the word ACCEPT/REJECT to indicate whether you accept the plan.")

                ] + messages['messages'][1:]  #everything after the system message.
            )

            return {'messages': [response]}

        def should_regenerate_plan(state: MessagesState) -> bool:
            last_message = state['messages'][-1]
            return 'REJECT' in last_message.content

        workflow = StateGraph(MessagesState)
        workflow.add_node("generate_plan", generate_plan)
        workflow.add_node("critique_plan", critique_plan)

        workflow.add_edge(START, "generate_plan")
        # On the first generation, add more details to the plan.
        workflow.add_conditional_edges("generate_plan",
                                       lambda messages: self._generation_count < 3, #critique only once, not indefinitely.
                                       {True: "critique_plan", False: END})
        workflow.add_conditional_edges("critique_plan",
                                       should_regenerate_plan, {True: "generate_plan", False: END})
        # workflow.add_edge("detail_plan", END)

        compiled_flow = workflow.compile()
        return compiled_flow

    def run(self) -> RefactoringPlan:
        compiled_flow = self.compile()
        messages = compiled_flow.invoke({'messages': [
            self.generation_system_message,
            HumanMessage(f"{self.source_file_path}: \n{self.source_code}")
        ]})
        return self._ref_plan


class NaivePlanningComponent(Planner):
    model: BaseChatModel = Field(description="model to use to generate the plan")
    _ref_plan: Optional[RefactoringPlan] = PrivateAttr(default=None)

    def compile(self) -> CompiledStateGraph:
        def generate_plan(messages: MessagesState):

            parser = PydanticOutputParser(pydantic_object=RefactoringPlan)
            messages1 = [
                self.generation_system_message,
                HumanMessage(f"{self.source_file_path}: \n{self.source_code}")
            ]

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


def get_mock_planning_component(plan: RefactoringPlan) -> Type[Planner]:

    class MockPlanningComponent(Planner):
        model: BaseChatModel = Field(description="model to use to generate the plan")
        def run(self) -> RefactoringPlan:
            return plan

    return MockPlanningComponent

