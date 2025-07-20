import json
import traceback
from concurrent.futures import as_completed
from langsmith.utils import ContextThreadPoolExecutor

from git import Commit
from pydantic.v1 import BaseModel, Field, PrivateAttr
from langchain_core.language_models import BaseChatModel
from typing import List, Iterable, Tuple, ClassVar
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, BaseMessage
from langgraph.graph import END, START, StateGraph, MessagesState
from pathlib import Path
from typing import Optional
import os

import refagent.utils.project_manager as pm
import refagent.utils.intellij_server as ij
import refagent.agents.refactrix.planning as planning
import refagent.agents.refactrix.supported_refactorings as sup_ref
import refagent.agents.refactrix.get_linked_elements_using_jar as jar_links

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
                              # sup_ref.SupportedRefactorings.TYPE_CHANGE
           ]

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
        elements_to_inspect = self.get_elements_to_inspect(diffs)
        elements_to_inspect += [(i,1) for i in
                                self.get_linked_elements(CodeElement(file_path=self.starting_file, line_num=1))]

        should_replicate_msg = self.should_replicate()
        if not should_replicate_msg:
            # The change does not need replication to other files,
            # the developer did not ask for it.
            return []

        files_to_inspect = [self.starting_file] + [i for i in set(i[0].file_path for i in elements_to_inspect)
                            if i!=self.starting_file
                            ]


        with ContextThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(self.handle_file, file_path): file_path for file_path in files_to_inspect}
            for i, future in enumerate(as_completed(futures)):
                print(f"completed planning for: {i + 1}/{len(futures)}")
                result = future.result()
                if result is not None:
                    yield result

        return None

    def handle_file(self, file_path) -> Optional[planning.RefactoringPlan]:
        try:
            ask_replicate = self.compile(file_path)
            should_replicate = ask_replicate.invoke({"messages": []})['messages'][-1]
            print(should_replicate.content)

            if 'YES' in should_replicate.content:  # should replicate the content
                plan = planning.PlanningComponent(
                    initial_intent=self.initial_intent + should_replicate.content,
                    model=self.model,
                    source_file_path=file_path,
                    source_code=self.project.get_file_contents(file_path),
                ).run()
                for step in plan.steps:
                    step.file_path = file_path  # hard code the file path, so that the correct file is opened.
                return plan
        except Exception as e:
            print(f"Error compiling and running replication for file {file_path}: {e}")
            traceback.print_exc()
        return None

    def get_elements_to_inspect(self, diffs):
        elements_to_inspect: List[Tuple[CodeElement, int]] = []
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
                this_element = CodeElement(file_path=file_path, line_num=hunk.get_first_edited_line())
                elements_to_inspect.append(
                    (this_element, 0)
                )
                elements_to_inspect += [(i, 1) for i in self.get_linked_elements(this_element)]
        return elements_to_inspect

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
        linked_elements_json = self.ide_server.call_tool('get_linked_elements', line_num=code_element.line_num)
        try:
            linked_elements_json = json.loads(
                linked_elements_json
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
            file_name = file_to_inspect.split('/')[-1]
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
                    HumanMessage(
                                f"Here is the intent of the developer: "
                                 f"{self.initial_intent}"
                                 # f"Here are the kinds of refactorings that "
                                 # f"need to be replicated. These refactorings were already performed:\n"
                                 # f"{examples}"
                    ),
                    HumanMessage(f"Here are the contents of the file: {file_contents}"),
                    HumanMessage("Answer the following question: "
                                 f"Are there ANY code elements in {file_name}, "
                                 f"that could change? "
                                 f"Then, say YES/NO at the end of your reply,"
                                 f" indicating whether to "
                                 f"there are any code elements that should change.")
                 ]
            )

            return {'messages':[response]}

        workflow = StateGraph(MessagesState)
        workflow.add_node("ask_replicate", ask_replicate)
        workflow.add_edge(START, "ask_replicate")

        return workflow.compile()



class SimpleReplication(Replication):

    def handle_file(self, file_path) -> Optional[planning.RefactoringPlan]:
        try:
            ask_replicate = self.compile(file_path)
            should_replicate = ask_replicate.invoke({"messages": []})['messages'][-1]
            print(should_replicate.content)
            if 'YES' in should_replicate.content:  # should replicate the content
                plan = planning.RefactoringPlan(
                    steps=[
                        planning.PlanningStep(
                            reason=self.initial_intent,
                            final_code="",
                            refactoring_type=sup_ref.SupportedRefactorings.RENAME,
                            file_path=file_path,
                            execution_details=should_replicate.content, # save the should replicate's response
                        )
                    ]
                )
                return plan
        except Exception as e:
            print(f"Error compiling and running replication for file {file_path}: {e}")
            traceback.print_exc()
        return None

class JarBasedReplication(SimpleReplication):
    def get_linked_elements(self, code_element: CodeElement) -> List[CodeElement]:
        # TODO: Call the jar here
        linked_elements = jar_links.get_linked_elements_from_project(
            project=self.project,
            file_path=code_element.file_path,
            line_number=code_element.line_num
        )

        return [CodeElement(file_path=i['file_path'], line_num=i['line_num']) for i in linked_elements]

