import json

from pydantic.v1 import BaseModel, Field, PrivateAttr
from langchain_core.language_models import BaseChatModel
from typing import List, Iterable
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph, MessagesState
from pathlib import Path
import os

import refagent.utils.project_manager as pm
import refagent.utils.intellij_server as ij
import refagent.agents.refactrix.planning as planning

class Replication(BaseModel):

    model: BaseChatModel = Field(description="Langchain Chat model")
    edited_files: List[Path] = Field(description="Files that have already been edited.")
    project: pm.EvalProject = Field(description="The project object. Used to read file contents")
    # example_changes: str = Field(description="The kinds of changes to replicate.")
    initial_intent: str = Field(description="Intent from the developer")
    ide_server: ij.IntellijServer = Field(description="intellij server to interract with")
    executed_plan: planning.RefactoringPlan = Field(description="executed plan that needs replication")

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
        files_to_inspect = [str(i) for i in self.edited_files if str(i).endswith('.java')]
        most_edited_file = files_to_inspect[0]
        # files_to_inspect += self.get_files_in_package(most_edited_file)
        files_to_inspect += self.get_linked_files(most_edited_file)
        inspected_files = []

        for i, file in enumerate(files_to_inspect):
            print(f"attempting to replicate change to {file}. ({i+1}/{len(files_to_inspect)})")
            if file in inspected_files:
                print(f"Skipping the replication to {file} "
                      f"as it was previously done.")
                continue
            if not self.project.file_exists(file):
                print("skipping because file does not exist.")
            # compile and run graph
            inspected_files.append(file)
            ask_replicate = self.compile(file)
            should_replicate = ask_replicate.invoke({"messages": []})['messages'][-1]
            print(should_replicate.content)

            if 'YES' in should_replicate.content: # should replicate the content
                plan = planning.PlanningComponent(
                    initial_intent=self.initial_intent + should_replicate.content,
                    model=self.model,
                    source_file_path=file,
                    source_code=self.project.get_file_contents(file),
                    project=self.project,
                    detail_steps=False # don't waste extra time detailing the steps.
                    # The examples are already good enough to do the job.
                ).run()
                yield plan


    def get_files_in_package(self, starting_file: str) -> List[str]:
        package_dir = Path(starting_file).parent
        return [str(package_dir.joinpath(i))
                for i in os.listdir(str(package_dir)) if i.endswith('.java')]

    def get_linked_files(self, starting_file: str) -> List[str]:
        self.ide_server.open_file(Path(starting_file))
        linked_files = json.loads(self.ide_server.call_tool_get('get_linked_files'))
        unique_files = [i for i in set(linked_files) if i.endswith('.java')]
        return unique_files


    def compile(self, file_to_inspect: str):
        """Compile the langgraph."""

        def ask_replicate(state: MessagesState):
            try:
                file_contents = self.project.get_file_contents(file_to_inspect)
            except FileNotFoundError:
                return {'messages': AIMessage("File not found. cannot replicate here.")}
            examples = '\n'.join([i.execution_details for i in self.executed_plan.steps])
            response = self.model.invoke(
                [
                    SystemMessage("You are an expert developer who decides whether a "
                                  "refactoring needs to be replicated in a certain file, "
                                  "for the sake of consistency. "),
                    HumanMessage(f"Here are the contents of the file: {file_contents}"),
                    HumanMessage(f"Here are some intent that need to be "
                                 f"replicated: {self.initial_intent}"
                                 f"Here are the EXACT kinds of refactorings that "
                                 f"need to be replicated:\n"
                                 f"{examples}"),
                    HumanMessage("Answer the following question: "
                                 f"Are there any code elements in {file_to_inspect}, "
                                 f"that could use a similar change? "
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



