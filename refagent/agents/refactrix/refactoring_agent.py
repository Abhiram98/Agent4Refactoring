from langgraph.graph.state import CompiledStateGraph
from langgraph.graph import StateGraph, START, END
from langchain_core.tools import tool, BaseTool
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

from typing import Annotated


import refagent.utils.intellij_server as ij
import refagent.utils.code_utils as code_utils
import refagent.agents.refactrix.supported_refactorings as sup_refs
import refagent.agents.refactrix.perform_refactoring as perform_ref
import refagent.agents.refactrix.tools as ref_tools
import refagent.agents.refactrix.planning as planning



class Agent(BaseModel):
    ide_server: ij.IntellijServer = Field(description="the url of the ide, to invoke")
    model_name: str = Field(description="model name")
    _files_changed: list[Path] = PrivateAttr(default=[])
    _source_code: str = PrivateAttr(default="")
    _tools: dict[str, BaseTool] = PrivateAttr(default=[])
    _iterations: int = PrivateAttr(default=0)
    _trajectory: list[BaseMessage] = PrivateAttr(default=[])

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
                            client_agent_version='0.1')
        elif vendor == 'openai':
            return ChatOpenAI(model_name)
        raise Exception(f"Unknown AI vendor {vendor}")

    def files_changed(self) -> list[Path]:
        return self._files_changed

    def run(self, initial_intent: str, starting_file: str):
        FAKE_LLM = True  # Change to False to invoke the real LLM.
        print("Starting refactoring-agent")
        self._source_code = starting_file  # TODO: Read the starting file
        self._iterations = 0
        self._files_changed.append(Path(starting_file)) # assuming the file will be changed.

        model = self.create_model()

        graph = self.compile_graph(model=model, initial_intent=initial_intent)

        planning_component = planning.NaivePlanningComponent(
            initial_intent=initial_intent,
            model=model,
            source_code=self._source_code
        )
        plan_message = planning_component.run()
        self._trajectory.append(plan_message)

        final_state = graph.invoke(  # TODO: edit these messages
            {
                "messages": [
                    SystemMessage(f"You are an expert developer who aims to improve the quality of the given code. "
                                  f"Please do the follow: {plan_message.content}. "
                                  f"ONLY make TOOL CALLS to perform actions."),
                ]
            },
            config={"configurable": {"thread_id": 42}}
        )
        self._trajectory = final_state
        print("Final message: ", final_state["messages"][-1].content)
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
        return source_code_changed

    def get_available_tools(self,
                            refactoring_type: sup_refs.SupportedRefactorings) -> list[BaseTool]:
        print(refactoring_type)

        if refactoring_type == sup_refs.SupportedRefactorings.EXTRACT_METHOD:
            return [self._tools.get(sup_refs.SupportedRefactorings.EXTRACT_METHOD.value)]
        elif refactoring_type == sup_refs.SupportedRefactorings.RENAME:
            return [self._tools.get(sup_refs.SupportedRefactorings.RENAME.value)]
        elif refactoring_type == sup_refs.SupportedRefactorings.CUSTOM:
            return [self._tools.get('replace_file_contents'), self._tools.get('replace_method_contents')]
        else:
            raise Exception("Unknown refactoring type.")

    def compile_graph(self, model, initial_intent) -> CompiledStateGraph:
        """Compile the graph with the given model"""

        @tool
        def choose_refactoring(
                refactoring_type: Annotated[sup_refs.SupportedRefactorings, f"select the type of refactoring. "
                                f"Choose `{sup_refs.SupportedRefactorings.CUSTOM.value}"
                                f" to perform refactorings not in the list.`"],
                reason: Annotated[str, "explanation for why the refactoring should be carried out"]
        ):
            """
            Select a refactoring action to perform and provide a reason.
            """
            # NOTE: This _tools doesn't actually get called.
            # It is used to make sure the LLM output is formatted
            print(refactoring_type)
            print(reason)

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
            llm_with_tools = model.bind_tools([
                choose_refactoring
            ])
            extra_message = "" if self._iterations == 0 else "Here's the modified source code: \n"
            new_messages = state['messages'] + [HumanMessage(content=
                                                             extra_message +
                                                             code_utils.add_line_numbers(self._source_code))]
            # try:
            response = llm_with_tools.invoke(
                new_messages
            )
            # except Exception as e:
            #     raise e
            self._iterations += 1
            new_messages.append(response)
            return {"messages": new_messages}

        def perform_selected_refactoring(state: MessagesState):
            """Perform refactoring in retry loop"""
            # tools_by_name = {"choose_refactoring": choose_refactoring}
            result = []
            for tool_call in state["messages"][-1].tool_calls:
                updated = self.update_source_code()
                if updated:
                    # Change human message which has the source code.
                    state['messages'][1] = HumanMessage(
                        code_utils.add_line_numbers(self._source_code))

                refactoring_type = sup_refs.SupportedRefactorings(
                    tool_call['args']['refactoring_type'])
                reason = tool_call['args']['reason']
                tools = self.get_available_tools(refactoring_type)
                perform_refactoring_graph = perform_ref.PerformRefactoring(
                    tools=tools,
                    model=model,
                    reason=reason,
                    refactoring_type=refactoring_type
                ).compile()
                messages = state['messages'][:-1] + [
                    AIMessage(f"I would like to perform an {refactoring_type.value}, because: {reason}")]
                observation = perform_refactoring_graph.invoke({"messages": messages})
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
        # workflow.add_node("planning", planning_compiled)
        workflow.add_node("curate_tests", curate_tests)
        workflow.add_node("select_refactoring", select_refactoring)
        # select_refactoring_tool = ToolNode([choose_refactoring])
        workflow.add_node("perform_refactoring", perform_selected_refactoring)

        # Add edges to connect nodes
        # workflow.add_edge(START, "planning")
        workflow.add_edge(START, "curate_tests")
        workflow.add_edge("curate_tests", "select_refactoring")

        def has_tool_call(state: MessagesState) -> bool:
            return (hasattr(state['messages'][-1], 'tool_calls') and
                    len(state['messages'][-1].tool_calls) != 0)

        workflow.add_conditional_edges(
            "select_refactoring", has_tool_call, {True: "perform_refactoring", False: END}
        )

        workflow.add_edge("perform_refactoring", "select_refactoring")

        # Compile
        graph = workflow.compile()
        return graph
