import refagent
from pydantic.v1 import BaseModel, Field, PrivateAttr
from typing import Callable, List, Optional, Type
from langchain_core.output_parsers import PydanticOutputParser, JsonOutputParser

from langgraph.graph import MessagesState
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage, AIMessage, BaseMessage
from langchain_core.language_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph
from langgraph.graph import StateGraph, START, END
from langchain_core.tools import tool, BaseTool

import refagent.agents.refactrix.supported_refactorings as sup_ref
import refagent.agents.refactrix.tools as tools
import refagent.utils.tool_documentation as td


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
    def run(self) -> RefactoringPlan:
        return RefactoringPlan(steps=[])

class PlanningComponent(Planner):
    initial_intent: str = Field(description="initial intent from the user")
    # developer_callback: Callable = Field(description="the function to call to get further"
    #                                                  " clarifications from the developer.")
    model: BaseChatModel = Field(description="model to use to generate the plan")
    source_file_path: str = Field(description="the file path to the starting source code.")
    source_code: str = Field(description="source code to work with")
    detail_steps: bool = Field(description="detail the execution steps", default=True)
    _ref_plan: Optional[RefactoringPlan] = PrivateAttr(default=None)
    _generation_count: int = PrivateAttr(default=0)
    _tools: dict[str, BaseTool] = PrivateAttr(default=tools.RefactoringToolProvider(ide_server=None).get())

    @property
    def generation_system_message(self) -> SystemMessage:
        parser = PydanticOutputParser(pydantic_object=RefactoringPlan)

        return SystemMessage( "You are an expert developer using a powerful IDE IntelliJ IDEA, "
                              "capable of performing refactorng."
                              "Please generate a step by step plan of IDE refactoring actions to "
                              f"perform the following: {self.initial_intent}. "
                              f"Please provide a plan ONLY to perform refactorings. "
                              f"Assume that other action steps will be taken care of by the developer."
                              f"Make sure that your plan is actionable on the given code. "
                              f"Do not include generic steps in this plan. "
                              f"{parser.get_format_instructions()}"
                              f"Here is some documentation for each refactoring type: {sup_ref.documentation}")


    def try_parsing(self, response: BaseMessage) -> Optional[PlanningStep]:
        try:
            json_ = JsonOutputParser().parse(response.content)
            return PlanningStep(**json_['properties'])
        except:
            return None

    def compile(self) -> CompiledStateGraph:
        def generate_plan(messages: MessagesState):
            parser = PydanticOutputParser(pydantic_object=RefactoringPlan)
            self._generation_count += 1
            # Set up a parser + inject instructions into the prompt template.

            response = self.model.invoke(
                messages['messages']
            )
            self._ref_plan = parser.invoke(response)
            messages_ret = []
            if self._generation_count !=1 or not self.detail_steps:
                messages_ret += [response]

            return {'messages': messages_ret}

        def detail_plan_steps(messages: MessagesState):
            if not self.detail_steps:
                return # don't detail the steps.

            parser = PydanticOutputParser(pydantic_object=PlanningStep)

            for i, cur_step in enumerate(self._ref_plan.steps):
                old_exec_details = cur_step.execution_details
                cur_step.execution_details = "to be determined."
                previous_steps = self._ref_plan.steps[:i+1]
                step_messages = "\n".join([f"step {i}: {s.json()}" for i, s in enumerate(previous_steps)])
                tool = self._tools.get(cur_step.refactoring_type.value)
                if tool is not None:
                    tool_description = td.get_tool_documentation(tool)
                    api_call_text = (f"Please refer to this API documentation of {cur_step.refactoring_type.value} "
                                     f"to detail the `execution_details` field. THIS IS IMPORTANT. "
                                     f"MAKE SURE the API can be called with the information you provide.: \n"
                                     f"{tool_description}\n")
                else:
                    api_call_text = ""

                messages_ = [
                    SystemMessage(f"You are a expert developer who adds details to an existing refactoring plan."),
                    HumanMessage(self.source_code),
                    AIMessage(f"Here are the steps in the refactoring plan: {step_messages}"),
                    HumanMessage(f"Please critique the last step, and improve it: {cur_step}. "
                                 f"{api_call_text}"
                                 f"Answer the following question: "
                                 f"Are there any missing details in the code? If yes, fill them out. "
                                 f"{parser.get_format_instructions()}")
                ]
                response = self.model.invoke(messages_)
                try:
                    new_step = parser.invoke(response)
                except:
                    print("Failed to parse the object :/.")
                    new_step = self.try_parsing(response)

                if new_step!=None:
                    self._ref_plan.steps[i] = new_step
                else:
                    cur_step.execution_details = old_exec_details # revert back the execution details

            return {'messages': [AIMessage(content=f"Here's the plan: \n{self._ref_plan.json()}")]}


        def critique_plan(messages: MessagesState):
            response = self.model.with_config(temperature=0.7).invoke(
                [
                    SystemMessage("You are an expert developer who critiques refactoring plans. "
                                  "You are aware of refactoring actions available in powerful IDEs "
                                  "like IntelliJ IDEA."
                                  "Critique the quality of the given plans. At the end of your critique, "
                                  "use the word ACCEPT/REJECT to indicate whether you accept the plan."),
                    HumanMessage(f"{self.initial_intent}"),
                    HumanMessage(self.source_code),
                    HumanMessage(f"Refactoring plan: {self._ref_plan.json()}")
                ]
            )

            return {'messages': [response]}

        def should_regenerate_plan(state: MessagesState) -> bool:
            last_message = state['messages'][-1]
            return 'REJECT' in last_message.content

        workflow = StateGraph(MessagesState)
        workflow.add_node("generate_plan", generate_plan)
        workflow.add_node("detail_plan", detail_plan_steps)
        workflow.add_node("critique_plan", critique_plan)

        workflow.add_edge(START, "generate_plan")
        # On the first generation, add more details to the plan.
        workflow.add_conditional_edges("generate_plan",
                                       lambda messages: self._generation_count == 1,
                                       {True: "detail_plan", False: "critique_plan"})
        workflow.add_edge("detail_plan", "critique_plan")
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


def get_mock_planning_component(plan: RefactoringPlan) -> Type[Planner]:

    class MockPlanningComponent(Planner):
        initial_intent: str = Field(description="initial intent from the user")
        model: BaseChatModel = Field(description="model to use to generate the plan")
        source_file_path: str = Field(description="the file path to the starting source code.")
        source_code: str = Field(description="source code to work with")
        def run(self) -> RefactoringPlan:
            return plan

    return MockPlanningComponent

