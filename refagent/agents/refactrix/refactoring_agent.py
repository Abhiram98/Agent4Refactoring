import json

from langgraph.graph.state import CompiledStateGraph
from langgraph.graph import StateGraph, START, END
from langchain_core.tools import tool, BaseTool
from langchain_core.output_parsers import PydanticOutputParser
from langchain_openai import ChatOpenAI
import os
from pathlib import Path
from pydantic.v1 import Field, BaseModel, PrivateAttr, SecretStr
from langgraph.graph import MessagesState
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage, AIMessage, BaseMessage
from langchain_core.language_models import BaseChatModel

try:
    from grazie_langchain_utils.language_models.grazie import ChatGrazie
except ImportError:
    print("Warning: Could not import ChatGrazie. Ensure grazie_langchain_utils is installed.")
from grazie.api.client.endpoints import GrazieApiGatewayUrls
from grazie.api.client.gateway import AuthType
from grazie.api.client.chat.response import Credit

from typing import Annotated, Optional, Type


import refagent.utils.intellij_server as ij
import refagent.utils.code_utils as code_utils
import refagent.agents.refactrix.supported_refactorings as sup_refs
import refagent.agents.refactrix.perform_refactoring as perform_ref
import refagent.agents.refactrix.tools as ref_tools
import refagent.agents.refactrix.planning as planning
import refagent.agents.refactrix.analysis as analysis
import refagent.utils.project_manager as pm
import refagent.agents.refactrix.replication as replication
import refagent.agents.refactrix.error_fixing as error_fixing

class SelectedRefactoring(BaseModel):
    """
    Select a refactoring action to perform and provide a reason.
    """
    reason: str = Field(description="explanation for why the refactoring should be carried out")
    refactoring_type: sup_refs.SupportedRefactorings = Field(description=f"select the type of refactoring. ")



class Agent(BaseModel):
    ide_server: ij.IntellijServer = Field(description="the url of the ide, to invoke")
    model_name: str = Field(description="model name")
    project: pm.EvalProject = Field(description="the evaluation project to run the agent on.")
    analysis_component: Type[analysis.AnalysisComponent] = Field(description="the kind of analysis component to use.",
                                                             default=analysis.AnalysisComponent)
    plan_component: Type[planning.Planner] = Field(description="the kind of planning component to use.",
                                                   default=planning.PlanningComponent)
    _files_changed: set[Path] = PrivateAttr(default=set())
    _directly_edited_files: set[Path] = PrivateAttr(default=set())
    _source_code: str = PrivateAttr(default="")
    _rel_file_path: str = PrivateAttr(default="")
    _tools: dict[str, BaseTool] = PrivateAttr(default=[])
    _iterations: int = PrivateAttr(default=0)
    _trajectory: list[BaseMessage] = PrivateAttr(default=[])
    _selected_refactoring: Optional[SelectedRefactoring] = PrivateAttr(default=None)
    class Config:
        arbitrary_types_allowed = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._tools: dict[str, BaseTool] = ref_tools.RefactoringToolProvider(ide_server=self.ide_server).get()

    def get_trajectory(self):
        for i in self._trajectory:
            if (isinstance(i, AIMessage)
                    and 'spent' in i.additional_kwargs
                    and isinstance(i.additional_kwargs['spent'], Credit)):
                i.additional_kwargs['spent'] = i.additional_kwargs['spent'].amount

        return self._trajectory

    def create_model(self) -> BaseChatModel:
        # Assumes that self.model_name looks like
        # 'openai:gpt-4o', or 'grazie:openai-gpt-4o', or 'anthropic:claude-sonnet'
        vendor, model_name = self.model_name.split(':')

        if vendor == 'grazie':
            # create grazie model
            return ChatGrazie(grazie_jwt_token=SecretStr(os.getenv("GRAZIE_JWT_TOKEN")),
                              client_auth_type=AuthType.APPLICATION,
                              client_url=GrazieApiGatewayUrls.STAGING,
                              profile=model_name,
                              client_agent_name='ref-agent',
                              client_agent_version='0.1',
                              temperature=0.3)
        if vendor == 'openai':
            return ChatOpenAI(model=model_name)
        raise Exception(f"Unknown AI vendor {vendor}")

    def files_changed(self) -> list[Path]:
        return list(self._files_changed)

    def try_open_file(self, rel_file_path: str):
        response = self.ide_server.try_open_file(Path(rel_file_path))
        if response.startswith('tool call failed '):
            # TODO: Ask agent if it would like to open a different file, or
            create_response = self.ide_server.create_file(Path(rel_file_path))
            if create_response == 'success':
                open_response = self.ide_server.open_file(Path(rel_file_path))
            else:
                raise Exception("Failed to open file and did not create one either.")
        self._rel_file_path = rel_file_path
        self._directly_edited_files.add(Path(rel_file_path))

    def run(self, initial_intent: str, starting_file: str):
        FAKE_LLM = True  # Change to False to invoke the real LLM.
        print("Starting refactoring-agent")
        self._source_code = starting_file  # TODO: Read the starting file
        self._iterations = 0
        self._files_changed.add(Path(starting_file))
        self._directly_edited_files.add(Path(starting_file)) # assuming the file will be changed.

        model = self.create_model()
        # tool_calling_model = self.create_model(model_name_="grazie:openai-gpt-4o-mini")

        analysis_report = self.analyze_developer_intent(initial_intent, model, starting_file)
        ref_plan = self.generate_initial_plan(analysis_report, model, starting_file)
        self._trajectory.append(AIMessage(content=str(ref_plan.steps)))

        final_state = self.execute_initial_plan(initial_intent, model, ref_plan)
        self.update_changed_files()

        # Run replication component
        replicator = replication.Replication(
            model=model,
            executed_plan=ref_plan,
            ide_server=self.ide_server,
            initial_intent=initial_intent,
            edited_files=list(self._files_changed),
            project=self.project,
            starting_file=starting_file,
            example_changes=self.get_important_files_diff()
        )
        for plan in replicator.compile_and_run():
            self.execute_plan(initial_intent, model, plan)
            self.update_changed_files()

        # Run error-fixing component
        error_fixing.ErrorFixing(
            model=model,
            ide_server=self.ide_server
        ).compile_and_run()

        return final_state["messages"][-1].content

    def get_important_files_diff(self):
        important_files = self.compute_most_important(self._files_changed)
        return "\n".join([self.project.get_git_diff(f) for f in important_files])

    def analyze_developer_intent(self, initial_intent, model, starting_file):
        """Analyze the developer intent and return the refactoring type and reason."""
        analysis_component = self.analysis_component(
            initial_intent=initial_intent,
            context_information="",
            source_code=self._source_code,
            source_file_path=starting_file,
            model=model
        )
        analysis_report = analysis_component.run()
        analysis_report = analysis_report.augmented_intent
        return analysis_report

    def generate_initial_plan(self, analysis_report, model, starting_file):
        planning_component = self.plan_component(
            initial_intent=analysis_report,
            # augmented_intent=analysis_report,
            model=model,
            source_code=self._source_code,
            source_file_path=starting_file
        )
        ref_plan = planning_component.run()
        return ref_plan

    def execute_initial_plan(self, initial_intent, model, ref_plan):
        final_state = self.execute_plan(initial_intent, model, ref_plan)
        return final_state

    def execute_plan(self, initial_intent, model, ref_plan):
        last_file_opened = None
        for i, step in enumerate(ref_plan.steps):
            print(f"Executing step {i + 1}/{len(ref_plan.steps)} in plan.")
            self._iterations = 0
            if step.file_path != last_file_opened:
                self.try_open_file(step.file_path)
                last_file_opened = step.file_path
            graph = self.compile_graph(model=model,
                                       initial_intent=initial_intent,
                                       plan_step=step)
            final_state = graph.invoke(
                {
                    "messages": [
                        SystemMessage(f"You are an expert developer who executes refactorings to"
                                      f" improve the quality of the given code. "
                                      f"Please do the follow: {step.refactoring_type}: {step.reason}. {step.execution_details} "
                                      f"The final could is expected to look something like this: {step.final_code}"
                                      f"ONLY make TOOL CALLS to perform actions."),
                    ]
                },
                config={"configurable": {"thread_id": 42}}
            )
            self._trajectory += final_state['messages']
            print(f"Result of executing step {i}: ", final_state["messages"][-1].content)
        return final_state

    def compute_most_important(self, file_changed):
        # Compute the relevant files that were changed.
        return list(self._directly_edited_files)

    def get_changed_file_contents(self) -> HumanMessage:
        self.ide_server.call_tool('save_all_changes')
        self.update_changed_files()

        current_source_code = "Here is the current state of files in the repository: \n"

        file_in_same_root = [i for i in self._files_changed if
                             str(Path(self._rel_file_path).parent) in str(i)]
        self.project.safe_add(self._files_changed)

        important_files = self.compute_most_important(self._files_changed)
        for rel_file_path in important_files:
            try:
                file_contents = self.project.get_file_contents(rel_file_path)
                source = code_utils.add_line_numbers(
                    "// This file is empty." if file_contents=="" else file_contents)

                diff = self.project.get_git_diff(str(rel_file_path))
                if diff!='':
                    changes = diff if len(diff) < len(source) else source
                else:
                    changes = source
            except FileNotFoundError:
                continue
            current_source_code += f"{rel_file_path}: \n{changes}"

        return HumanMessage(content=current_source_code)

    def update_changed_files(self):
        changed_files = set(self.project.get_changed_files())
        self._files_changed = self._files_changed.union(changed_files)

    def update_source_code(self) -> bool:
        """Call the environment to fetch the current version
         of the source code under operation"""

        new_source_code = self.ide_server.call_tool_get(
            "get_source_code",
        )
        source_code_changed = False
        if self._source_code != new_source_code:
            source_code_changed = True
        self._source_code = new_source_code
        self._rel_file_path = self.ide_server.call_tool_get("get_rel_file_path")
        return source_code_changed

    def get_available_tools(self,
                            refactoring_type: sup_refs.SupportedRefactorings) -> list[BaseTool]:
        print(f"getting tools for {refactoring_type}")

        GENERIC_EDITING_TOOLS = [self._tools.get('replace_method_contents'), self._tools.get('find_replace')]

        multi_map = {
            sup_refs.SupportedRefactorings.CHANGE_SIGNATURE:
                [self._tools[sup_refs.SupportedRefactorings.CHANGE_SIGNATURE.value],
                 self._tools['introduce_parameter_object'],
                 self._tools.get('replace_method_contents')],
            sup_refs.SupportedRefactorings.EXTRACT_CLASS:
                [self._tools[sup_refs.SupportedRefactorings.EXTRACT_CLASS.value],
                 self._tools['introduce_parameter_object']],
            sup_refs.SupportedRefactorings.MOVE: [self._tools['move_method']]
        }

        if self.current_file_empty():
            # Supply file rewrite when it is empty
            print("supplying file replace tool")
            self._directly_edited_files.add(Path(self._rel_file_path))
            return [self._tools.get('replace_file_contents')]

        if refactoring_type == sup_refs.SupportedRefactorings.UNSUPPORTED:
            return GENERIC_EDITING_TOOLS
        elif refactoring_type in multi_map:
            # In case there are multiple tools that can be invoked for a single refactoring type
            return multi_map[refactoring_type]
        else:
            special_tool = self._tools.get(refactoring_type.value)
            tools = []
            if special_tool is not None:
                tools += [special_tool]
                if self._iterations >= 2:
                    # more than one iteration on the same step. It means that tool calls are not working.
                    print("supplying generic tools, as tool calls are not working")
                    tools += GENERIC_EDITING_TOOLS
                return tools
            print(f"Since the {refactoring_type} has no specialised tools, supplying generic tools.")
            return GENERIC_EDITING_TOOLS

    def current_file_empty(self):
        return self._source_code == ''

    def compile_graph(self, model: BaseChatModel,
                      initial_intent: str,
                      plan_step: planning.PlanningStep) -> CompiledStateGraph:
        """Compile the graph with the given model and the given planning step"""

        def curate_tests(state: MessagesState):
            """Find appropriate test class, run the test, and note which ones are passing.
            This is useful to verify that refactoring hasn't broken the code later."""

            self.ide_server.call_tool("curate_test_class", file_path="")

        def run_tests(state: MessagesState):
            # TODO: add arguments, if necessary
            self.ide_server.call_tool("run_test_class", file_path="")

        def select_refactoring(state: MessagesState):
            """First LLM call to generate refactoring ideas"""
            self.update_source_code()
            if self._iterations == 0:
                # return the pre-selected refactoring type.
                self._selected_refactoring = SelectedRefactoring(
                    reason=plan_step.reason,
                    refactoring_type=plan_step.refactoring_type)
                self._iterations += 1
                return {'messages': [AIMessage(f"{plan_step.reason}. {plan_step.refactoring_type.value}")]}
            parser = PydanticOutputParser(pydantic_object=SelectedRefactoring)
            new_messages = state['messages'] + [
                self.get_changed_file_contents(),
                HumanMessage("Please choose a refactoring type, along with reason. "
                             "If nothing needs to be done, OR if there is no appropriate refactoring type,"
                             "please provide reasoning."
                             f"{parser.get_format_instructions()}")
            ]
            # try:
            response = model.invoke(
                new_messages
            )
            self._selected_refactoring = parser.invoke(response)
            self._iterations += 1
            # new_messages.append(response)
            return {"messages": [response]}

        def perform_selected_refactoring(state: MessagesState):
            """Perform refactoring in retry loop"""
            updated = self.update_source_code()
            if updated:
                # Change human message which has the source code.
                state['messages'][1] = HumanMessage(
                    code_utils.add_line_numbers(self._source_code))

            refactoring_type = self._selected_refactoring.refactoring_type
            reason = self._selected_refactoring.reason
            rel_file_path = self._rel_file_path
            self._files_changed.add(Path(rel_file_path))

            tools = self.get_available_tools(refactoring_type)
            perform_refactoring_graph = perform_ref.PerformRefactoring(
                tools=tools,
                model=model,
                reason=reason,
                refactoring_type=refactoring_type,
                rel_file_path=rel_file_path,
                ide_server=self.ide_server
            ).compile()
            messages = state['messages'] + [
                AIMessage(f"I would like to perform an {refactoring_type.value}, because: {reason}."),
                self.get_changed_file_contents()
            ]
            observation = perform_refactoring_graph.invoke({"messages": messages})
            last_message = observation['messages'][-1]
            messages = state["messages"]
            messages += [last_message]

            return {"messages": messages}

        def finished_refactoring(state: MessagesState):

            if self._iterations >= 5:
                # Stopping because limit has been reached.
                return {'messages': [AIMessage('finished because iteration limit reached. DONE')]}

            if self.ide_server.call_tool_get("get_source_code") == '':
                return {'messages': [AIMessage('incomplete because the file is empty. INCOMPLETE')]}

            response = model.invoke(state['messages'] +
                         [HumanMessage('Please reflect whether the original ask has been completed successfully'
                                       f'Here was the original ask: {plan_step.refactoring_type}: {plan_step.reason}. {plan_step.execution_details}'
                                       f'{self.get_changed_file_contents().content}'
                                       f'Please reflect whether the task is complete, '
                                       f'by answering the following questions: '
                                       '1. Has the original ask been met? '
                                       f'2. Are there other locations within the file {self._rel_file_path} '
                                       f'where the same change can be applied? '
                                       'Finally say whether the task is complete '
                                       'using the word DONE/INCOMPLETE appropriately.')])
            return {'messages': [response]}

        def has_finished_refactoring(state: MessagesState) -> bool:
            return (state['messages'][-1].content.endswith('DONE') or
                    'INCOMPLETE' not in state['messages'][-1].content)

        workflow = StateGraph(MessagesState)
        # Add nodes
        # workflow.add_node("curate_tests", curate_tests)
        workflow.add_node("select_refactoring", select_refactoring)
        workflow.add_node("perform_refactoring", perform_selected_refactoring)
        workflow.add_node("finished_refactoring", finished_refactoring)

        # Add edges to connect nodes
        workflow.add_edge(START, "finished_refactoring")
        def has_tool_call(state: MessagesState) -> bool:
            return self._selected_refactoring.refactoring_type!=sup_refs.SupportedRefactorings.UNSUPPORTED

        workflow.add_conditional_edges("finished_refactoring", has_finished_refactoring,
                                       {True: END, False: "select_refactoring"})
        workflow.add_conditional_edges(
            "select_refactoring", has_tool_call, {True: "perform_refactoring", False: END}
        )
        workflow.add_edge("perform_refactoring", "finished_refactoring")


        # Compile
        graph = workflow.compile()
        return graph
