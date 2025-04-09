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
from grazie_langchain_utils.language_models.grazie import ChatGrazie
from grazie.api.client.endpoints import GrazieApiGatewayUrls
from grazie.api.client.gateway import AuthType
from grazie.api.client.chat.response import Credit

from typing import Annotated, Optional


import refagent.utils.intellij_server as ij
import refagent.utils.code_utils as code_utils
import refagent.agents.refactrix.supported_refactorings as sup_refs
import refagent.agents.refactrix.perform_refactoring as perform_ref
import refagent.agents.refactrix.tools as ref_tools
import refagent.agents.refactrix.planning as planning


class SelectedRefactoring(BaseModel):
    """
    Select a refactoring action to perform and provide a reason.
    """
    reason: str = Field(description="explanation for why the refactoring should be carried out")
    refactoring_type: sup_refs.SupportedRefactorings = Field(description=f"select the type of refactoring. ")



class Agent(BaseModel):
    ide_server: ij.IntellijServer = Field(description="the url of the ide, to invoke")
    model_name: str = Field(description="model name")
    _files_changed: set[Path] = PrivateAttr(default=set())
    _source_code: str = PrivateAttr(default="")
    _rel_file_path: str = PrivateAttr(default="")
    _tools: dict[str, BaseTool] = PrivateAttr(default=[])
    _iterations: int = PrivateAttr(default=0)
    _trajectory: list[BaseMessage] = PrivateAttr(default=[])
    _selected_refactoring: Optional[SelectedRefactoring] = PrivateAttr(default=None)

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
                              temperature=0.7)
        elif vendor == 'openai':
            return ChatOpenAI(model_name)
        raise Exception(f"Unknown AI vendor {vendor}")

    def files_changed(self) -> list[Path]:
        return list(self._files_changed)

    def try_open_file(self, rel_file_path: str):
        response = self.ide_server.try_open_file(Path(rel_file_path))
        if response.startswith('tool call failed '):
            create_response = self.ide_server.create_file(Path(rel_file_path))
            if create_response == 'success':
                open_response = self.ide_server.open_file(Path(rel_file_path))
            else:
                raise Exception("Failed to open file and did not create one either.")
        self._rel_file_path = rel_file_path

    def run(self, initial_intent: str, starting_file: str):
        FAKE_LLM = True  # Change to False to invoke the real LLM.
        print("Starting refactoring-agent")
        self._source_code = starting_file  # TODO: Read the starting file
        self._iterations = 0
        self._files_changed.add(Path(starting_file)) # assuming the file will be changed.

        model = self.create_model()
        # tool_calling_model = self.create_model(model_name_="grazie:openai-gpt-4o-mini")

        planning_component = planning.PlanningComponent(
            initial_intent=initial_intent,
            model=model,
            source_code=self._source_code
        )
        ref_plan = planning_component.run()
        self._trajectory.append(AIMessage(content=str(ref_plan.steps)))

        for i, step in enumerate(ref_plan.steps):
            print(f"Executing step {i+1} in plan.")
            self.try_open_file(step.file_path)
            graph = self.compile_graph(model=model,
                                       initial_intent=initial_intent,
                                       plan_step=step)
            final_state = graph.invoke(
                {
                    "messages": [
                        SystemMessage(f"You are an expert developer who executes refactorings to"
                                      f" improve the quality of the given code. "
                                      f"Please do the follow: {step.refactoring_type}: {step.reason}. "
                                      f"The final could is expected to look something like this: {step.final_code}"
                                      f"ONLY make TOOL CALLS to perform actions."),
                    ]
                },
                config={"configurable": {"thread_id": 42}}
            )
            self._trajectory += final_state['messages']
            print("Result of executing step 1: ", final_state["messages"][-1].content)
        return final_state["messages"][-1].content

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
        print(refactoring_type)

        if refactoring_type == sup_refs.SupportedRefactorings.EXTRACT_METHOD:
            return [self._tools.get(sup_refs.SupportedRefactorings.EXTRACT_METHOD.value)]
        elif refactoring_type == sup_refs.SupportedRefactorings.RENAME:
            return [self._tools.get(sup_refs.SupportedRefactorings.RENAME.value)]
        elif refactoring_type == sup_refs.SupportedRefactorings.EXTRACT_CLASS:
            return [self._tools.get(sup_refs.SupportedRefactorings.EXTRACT_CLASS.value)]
        elif refactoring_type == sup_refs.SupportedRefactorings.CUSTOM:
            return [self._tools.get('replace_file_contents'), self._tools.get('replace_method_contents')]
        else:
            raise Exception("Unknown refactoring type.")

    def compile_graph(self, model: BaseChatModel,
                      initial_intent: str,
                      plan_step: planning.PlanningStep) -> CompiledStateGraph:
        """Compile the graph with the given model and the given planning step"""

        def open_file(state: MessagesState):
            """Open the required file. create it if it doesn't exist."""

            self.ide_server.call_tool("curate_test_class", file_path="")

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
            if self._iterations >= 5:  # stop after 3 _iterations
                return
            # llm_with_tools = model.bind_tools([
            #     choose_refactoring
            # ])
            extra_message = "" if self._iterations == 0 else "Here's the modified source code: \n"
            parser = PydanticOutputParser(pydantic_object=SelectedRefactoring)
            new_messages = state['messages'] + [
                # SystemMessage(f"Here is what the final code might look like: {plan_step.final_code}"),
                HumanMessage(
                    content=f"{self._rel_file_path}: {extra_message}"
                            f"\n {code_utils.add_line_numbers(self._source_code)}"),
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
                AIMessage(f"I would like to perform an {refactoring_type.value}, because: {reason}")]

            observation = perform_refactoring_graph.invoke({"messages": messages})
            last_message = observation['messages'][-1]
            messages = state["messages"]
            messages += [last_message]

            return {"messages": messages}

        def finished_refactoring(state: MessagesState) -> bool:

            if self.ide_server.call_tool_get("get_source_code") == '':
                return False

            response = model.invoke(state['messages'] +
                         [HumanMessage('Please reflect whether the original ask has been completed successfully.'
                                       f'Here was the original ask: {plan_step.refactoring_type}: {plan_step.reason}'
                                       f'Here is the modified code: {code_utils.add_line_numbers(self.ide_server.call_tool_get("get_source_code"))}'
                                       'If the task is complete say YES. Otherwise, say NO. Only respond with YES/NO')])
            if 'YES' in response.content:
                return True
            else:
                return False

        workflow = StateGraph(MessagesState)
        # Add nodes
        # workflow.add_node("planning", planning_compiled)
        workflow.add_node("open_file", open_file)
        workflow.add_node("curate_tests", curate_tests)
        workflow.add_node("select_refactoring", select_refactoring)
        # select_refactoring_tool = ToolNode([choose_refactoring])
        workflow.add_node("perform_refactoring", perform_selected_refactoring)

        # Add edges to connect nodes
        # workflow.add_edge(START, "planning")
        # workflow.add_edge(START, "curate_tests")
        workflow.add_conditional_edges(START, finished_refactoring,
                                       {True: END, False: "curate_tests"})
        workflow.add_edge("curate_tests", "select_refactoring")

        def has_tool_call(state: MessagesState) -> bool:
            return self._selected_refactoring.refactoring_type!=sup_refs.SupportedRefactorings.UNSUPPORTED

        workflow.add_conditional_edges(
            "select_refactoring", has_tool_call, {True: "perform_refactoring", False: END}
        )

        workflow.add_conditional_edges("perform_refactoring", finished_refactoring,
                                       {True: END, False: "select_refactoring"})

        # Compile
        graph = workflow.compile()
        return graph
