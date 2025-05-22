import json
import traceback

from git import Commit
from pydantic.v1 import BaseModel, Field, PrivateAttr
from langchain_core.language_models import BaseChatModel
from typing import List, Iterable, Tuple, ClassVar
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, BaseMessage
from langgraph.graph import END, START, StateGraph, MessagesState
from pathlib import Path
import os

import refagent.utils.project_manager as pm
import refagent.utils.intellij_server as ij
import refagent.agents.refactrix.planning as planning
import refagent.agents.refactrix.supported_refactorings as sup_ref


class CodeElement(BaseModel):
    file_path: str = Field(description="The file that was edited.")
    line_num: int = Field(description="The line number that was edited.")

class Replication(BaseModel):

    model: BaseChatModel = Field(description="Langchain Chat model")
    edited_files: List[Path] = Field(description="Files that have already been edited.")
    project: pm.EvalProject = Field(description="The project object. Used to read file contents")
    example_changes: str = Field(description="The kinds of changes to replicate.")
    initial_intent: str = Field(description="Intent from the developer")
    ide_server: ij.IntellijServer = Field(description="intellij server to interract with")
    executed_plan: planning.RefactoringPlan = Field(description="executed plan that needs replication")
    starting_file: str = Field(description="The first file that was edited.")
    refactoring_commit: Commit = Field(description="The commit that was edited.")

    SUPPORTED_REPLICATIONS: ClassVar[List[sup_ref.SupportedRefactorings]] \
        = [sup_ref.SupportedRefactorings.RENAME,
                              # sup_ref.SupportedRefactorings.CHANGE_SIGNATURE,
                              sup_ref.SupportedRefactorings.TYPE_CHANGE]

    class Config:
        arbitrary_types_allowed = True

    def compile_and_run(self) -> Iterable[planning.RefactoringPlan]:
        """Two phases of replication.
                1. Within file.
                2. Across files
                    - find other relevant files (using call graph/other techniques)
                    - Ask if the change can be replicated here.
                    - Invoke planning to replicate changes.
        """
        # files_to_inspect = [str(i) for i in self.edited_files if str(i).endswith('.java')]
        diffs = self.project.get_changes(self.refactoring_commit.hexsha)
        elements_to_inspect: List[Tuple[CodeElement, int]] = []
        files_inspected: List[str] = []
        for diff in diffs:
            if diff.git_diff.b_path is None:
                # skipping, probably because file got deleted
                continue
            file_path = diff.git_diff.b_path
            if not file_path.endswith('.java'):
                continue
            if not self.project.file_exists(file_path):
                continue

            for hunk in diff.hunks:
                elements_to_inspect.append(
                    (CodeElement(file_path=file_path, line_num=hunk.get_first_edited_line()), 0)
                )

        should_replicate_msg = self.should_replicate()
        if not should_replicate_msg:
            # The change does not need replication to other files,
            # the developer did not ask for it.
            return []

        while len(elements_to_inspect) > 0:
            # breadth-first search through the repository
            print(f"{len(elements_to_inspect)=}")
            code_element, depth = elements_to_inspect.pop(0)

            if depth == 0:
                # increase the search space, only by one level.
                elements_to_inspect += [(i, depth+1) for i in self.get_linked_elements(code_element)]

            if code_element.file_path in files_inspected:
                print(f"Skipping the replication to {code_element.file_path} "
                      f"as it was previously done.")
                continue

            ask_replicate = self.compile(code_element.file_path)
            should_replicate = ask_replicate.invoke({"messages": []})['messages'][-1]
            print(should_replicate.content)

            if 'YES' in should_replicate.content:  # should replicate the content
                plan = planning.PlanningComponent(
                    initial_intent=self.initial_intent + should_replicate.content,
                    model=self.model,
                    source_file_path=code_element.file_path,
                    source_code=self.project.get_file_contents(code_element.file_path),
                    # project=self.project,
                    # detail_steps=False  # don't waste extra time detailing the steps.
                    # The examples are already good enough to do the job.
                ).run()
                yield plan

            files_inspected.append(code_element.file_path)
        return None

    def get_files_in_package(self, starting_file: str) -> List[str]:
        package_dir = Path(starting_file).parent
        return [str(package_dir.joinpath(i))
                for i in os.listdir(str(package_dir)) if i.endswith('.java')]

    def get_linked_files(self, starting_file: str) -> List[str]:
        self.ide_server.open_file(Path(starting_file))
        linked_files = json.loads(self.ide_server.call_tool_get('get_linked_files'))
        unique_files = [i for i in set(linked_files) if i.endswith('.java')]
        return unique_files

    def get_linked_elements(self, code_element: CodeElement) -> List[CodeElement]:
        self.ide_server.open_file(Path(code_element.file_path))
        try:
            linked_elements_json = json.loads(
                self.ide_server.call_tool('get_linked_elements', line_num=code_element.line_num)
            )
        except:
            print("Failed to get linked element")
            traceback.print_exc()
            return []
        return [CodeElement(**i) for i in linked_elements_json]

    def should_replicate(self) -> bool:
        contains_supported_type = [i.refactoring_type in Replication.SUPPORTED_REPLICATIONS for i in self.executed_plan.steps]
        return any(contains_supported_type)

        # file_contents = self.project.get_file_contents(self.starting_file)
        #
        # response = self.model.invoke(
        #     [
        #         SystemMessage("You are an expert developer who decides whether a "
        #                       "refactoring needs to be replicated in other files "
        #                       "for the sake of consistency, based on a user's request. "),
        #         HumanMessage(f"Here are the contents of the file: {file_contents}"),
        #         HumanMessage(f"Here was the request from the user: {self.initial_intent}"),
        #         HumanMessage("Answer the following question: "
        #                      f"Should this change be carried out in other files? Or is the current state of the file "
        #                      f"sufficient to complete the user's request?"
        #                      f"Then, add a YES/NO at the end of your reply,"
        #                      f" indicating whether to "
        #                      f"replicate the refactoring concept to other files.")
        #     ]
        # )
        # return response

    def compile(self, file_to_inspect: str):
        """Compile the langgraph."""

        def ask_replicate(state: MessagesState):
            try:
                file_contents = self.project.get_file_contents(file_to_inspect)
            except FileNotFoundError:
                return {'messages': AIMessage("File not found. cannot replicate here.")}

            filtered_steps = [i for i in self.executed_plan.steps
                              if i.refactoring_type in Replication.SUPPORTED_REPLICATIONS]
            examples = '\n'.join([i.execution_details for i in filtered_steps])
            examples += self.example_changes
            response = self.model.invoke(
                state['messages'] +
                [
                    SystemMessage("You are an expert developer who decides whether a "
                                  "refactoring needs to be replicated in a certain file, "
                                  "for the sake of consistency. "),
                    HumanMessage(f"Here are the contents of the file: {file_contents}"),
                    HumanMessage(
                                # f"Here are some intent that need to be "
                                #  f"replicated: {self.initial_intent}"
                                 f"Here are the EXACT kinds of refactorings that "
                                 f"need to be replicated. These refactorings were already performed:\n"
                                 f"{examples}"),
                    HumanMessage("Answer the following question: "
                                 f"Are there any code elements in {file_to_inspect}, "
                                 f"that could this exact change? "
                                 f"Then, add a YES/NO at the end of your reply,"
                                 f" indicating whether to "
                                 f"replicate the refactoring concept in this file.")
                 ]
            )

            return {'messages':[response]}

        workflow = StateGraph(MessagesState)
        workflow.add_node("ask_replicate", ask_replicate)
        workflow.add_edge(START, "ask_replicate")

        return workflow.compile()



