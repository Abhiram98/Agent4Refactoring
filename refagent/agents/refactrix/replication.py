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
import re

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

    # Add tracking fields for files_to_inspect data
    _files_to_inspect_before_count: int = PrivateAttr(default=0)
    _files_to_inspect_after_count: int = PrivateAttr(default=0)
    _files_to_inspect_before_list: List[str] = PrivateAttr(default=[])
    _files_to_inspect_after_list: List[str] = PrivateAttr(default=[])

    SUPPORTED_REPLICATIONS: ClassVar[List[sup_ref.SupportedRefactorings]] \
        = [sup_ref.SupportedRefactorings.RENAME,
           # sup_ref.SupportedRefactorings.CHANGE_SIGNATURE,
           # sup_ref.SupportedRefactorings.TYPE_CHANGE
           ]

    class Config:
        arbitrary_types_allowed = True

    def get_files_inspection_data(self) -> dict:
        """Return the files inspection data for saving to results"""
        return {
            "files_to_inspect_before_count": self._files_to_inspect_before_count,
            "files_to_inspect_after_count": self._files_to_inspect_after_count,
            "files_to_inspect_before_list": self._files_to_inspect_before_list,
            "files_to_inspect_after_list": self._files_to_inspect_after_list,
        }

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
        elements_to_inspect += [(i, 1) for i in
                                self.get_linked_elements(CodeElement(file_path=self.starting_file, line_num=1))]

        # Always capture file inspection data, even if replication is skipped
        files_to_inspect = [i for i in set(i[0].file_path for i in elements_to_inspect)
                            # if i!=self.starting_file
                            ]

        files_to_inspect = list(set(files_to_inspect))

        # Capture data before filtering
        self._files_to_inspect_before_count = len(files_to_inspect)
        self._files_to_inspect_before_list = files_to_inspect.copy()

        if len(files_to_inspect) > 50:
            print(f"Limiting files to first 50 due to large number of files: {len(files_to_inspect)}")
            files_to_inspect = files_to_inspect[:50]

        # Capture data after filtering
        self._files_to_inspect_after_count = len(files_to_inspect)
        self._files_to_inspect_after_list = files_to_inspect.copy()

        should_replicate_msg = self.should_replicate()
        if not should_replicate_msg:
            # The change does not need replication to other files,
            # the developer did not ask for it.
            return []

        # print(f"files to inspect: {files_to_inspect}\n\n")

        # list_of_keywords = self.invokeLLM()
        # files_to_inspect = self.filterFilesWithLCS(files_to_inspect, list_of_keywords)

        # print(f"files to inspect after filtering: {files_to_inspect}\n\n")

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
            ask_replicate = self.compile(file_path)  # the edited file?
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
        linked_files_response = self.ide_server.call_tool_get('get_linked_files')
        
        # Validate response before parsing JSON
        if not linked_files_response:
            print(f"Failed to get linked files: Empty response from server for file {starting_file}")
            return []
        
        if linked_files_response.startswith("tool call failed"):
            print(f"Failed to get linked files: {linked_files_response}")
            return []
        
        try:
            linked_files = json.loads(linked_files_response.strip())
        except json.JSONDecodeError as e:
            print(f"Failed to parse linked files JSON: {e}")
            print(f"Raw response: '{linked_files_response}'")
            print(f"File: {starting_file}")
            return []
        except Exception as e:
            print(f"Unexpected error parsing linked files: {e}")
            traceback.print_exc()
            return []
        
        # Validate that the response is a list
        if not isinstance(linked_files, list):
            print(f"Expected list response but got {type(linked_files)}: {linked_files}")
            return []
            
        unique_files = [i for i in set(linked_files) if i.endswith('.java')]
        return unique_files

    def get_linked_elements(self, code_element: CodeElement) -> List[CodeElement]:
        self.ide_server.open_file(Path(code_element.file_path))
        linked_elements_response = self.ide_server.call_tool('get_linked_elements', line_num=code_element.line_num)
        # linked_elements_response = self.ide_server.call_tool('get_linked_elements_hybrid', line_num=code_element.line_num)
        # linked_elements_response = self.ide_server.call_tool('get_linked_files_hybrid', line_num=code_element.line_num)
        
        # Validate response before parsing JSON
        if not linked_elements_response:
            print(f"Failed to get linked elements: Empty response from server for file {code_element.file_path}, line {code_element.line_num}")
            return []
        
        if linked_elements_response.startswith("tool call failed"):
            print(f"Failed to get linked elements: {linked_elements_response}")
            return []
        
        try:
            linked_elements_json = json.loads(linked_elements_response.strip())
        except json.JSONDecodeError as e:
            print(f"Failed to parse linked elements JSON: {e}")
            print(f"Raw response: '{linked_elements_response}'")
            print(f"File: {code_element.file_path}, Line: {code_element.line_num}")
            return []
        except Exception as e:
            print(f"Unexpected error parsing linked elements: {e}")
            traceback.print_exc()
            return []
        
        # Validate that the response is a list
        if not isinstance(linked_elements_json, list):
            print(f"Expected list response but got {type(linked_elements_json)}: {linked_elements_json}")
            return []
            
        return [CodeElement(**i) for i in linked_elements_json]

    def should_replicate(self) -> bool:
        contains_supported_type = [i.refactoring_type in Replication.SUPPORTED_REPLICATIONS for i in
                                   self.executed_plan.steps]
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

            return {'messages': [response]}

        workflow = StateGraph(MessagesState)
        workflow.add_node("ask_replicate", ask_replicate)
        workflow.add_edge(START, "ask_replicate")

        return workflow.compile()

    def invokeLLM(self):
        filtered_steps = [i for i in self.executed_plan.steps
                          if i.refactoring_type in Replication.SUPPORTED_REPLICATIONS]
        examples = '\n'.join([i.execution_details for i in filtered_steps])
        examples += self.example_changes

        response = self.model.invoke([
            SystemMessage(
                "You are an expert developer who can extract pairs of old and new identifiers (variable, method, class names, etc.) that were renamed from code diffs. You will be given code diffs and should output a list of (old_name, new_name) pairs for all identifiers that were renamed."),
            HumanMessage(
                f"Here is the code diffs:\n"
                f"{examples}"),
            HumanMessage(
                "Extract all variable names, method names, class names, or other identifiers that were renamed. Output only a list of pairs in the format: old_name -> new_name, one pair per line. Do not include any explanation or extra text."
            )
        ])
        # Parse the response to extract pairs
        pairs = []
        content = response.content if hasattr(response, 'content') else str(response)
        if not isinstance(content, str):
            content = str(content)
        for line in content.strip().split('\n'):
            if '->' in line:
                old, new = line.split('->', 1)
                pairs.append((old.strip(), new.strip()))
        print(f"Extracted rename pairs: {pairs}")
        return pairs

    def normalize_identifier(self, identifier):
        """Normalize identifier by converting to lowercase and removing separators."""
        if not identifier:
            return ""
        # Convert to lowercase
        normalized = identifier.lower()
        # Remove separators: _, -, #, and numbers
        normalized = re.sub(r'[_\-#\d]', '', normalized)
        return normalized

    def extract_common_pattern(self, old_name, new_name):
        """Extract the common pattern between old_name and new_name using LCSubstring."""
        normalized_old = self.normalize_identifier(old_name)
        normalized_new = self.normalize_identifier(new_name)

        # Find LCSubstring between old and new names
        lcsubstring = self.lcsubstring_length(normalized_old, normalized_new)

        # Extract the actual common substring
        common_pattern = self.get_lcsubstring_sequence(normalized_old, normalized_new)

        return common_pattern, lcsubstring

    def lcsubstring_length(self, a, b):
        """Calculate the length of the longest common substring between two strings."""
        if not a or not b:
            return 0

        # Create a 2D DP table
        dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
        max_length = 0

        for i in range(1, len(a) + 1):
            for j in range(1, len(b) + 1):
                if a[i - 1] == b[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1] + 1
                    max_length = max(max_length, dp[i][j])
                else:
                    dp[i][j] = 0

        return max_length

    def get_lcsubstring_sequence(self, a, b):
        """Get the actual longest common substring between two strings."""
        if not a or not b:
            return ""

        # Create a 2D DP table
        dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
        max_length = 0
        end_pos = 0

        for i in range(1, len(a) + 1):
            for j in range(1, len(b) + 1):
                if a[i - 1] == b[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1] + 1
                    if dp[i][j] > max_length:
                        max_length = dp[i][j]
                        end_pos = i

        # Extract the substring
        start_pos = end_pos - max_length
        return a[start_pos:end_pos]

    def get_lcs_sequence(self, a, b):
        """Get the actual LCS sequence between two strings."""
        dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
        # Fill the DP table
        for i in range(len(a)):
            for j in range(len(b)):
                if a[i] == b[j]:
                    dp[i + 1][j + 1] = dp[i][j] + 1
                else:
                    dp[i + 1][j + 1] = max(dp[i][j + 1], dp[i + 1][j])

        # Backtrack to get the sequence
        lcs = []
        i, j = len(a), len(b)
        while i > 0 and j > 0:
            if a[i - 1] == b[j - 1]:
                lcs.append(a[i - 1])
                i -= 1
                j -= 1
            elif dp[i - 1][j] > dp[i][j - 1]:
                i -= 1
            else:
                j -= 1

        return ''.join(reversed(lcs))

    def calculate_pattern_similarity(self, identifier, pattern, threshold=0.5):
        """Calculate similarity between identifier and a pattern using LCSubstring."""
        normalized_identifier = self.normalize_identifier(identifier)
        if not pattern or not normalized_identifier:
            return False

        lcsubstring = self.lcsubstring_length(normalized_identifier, pattern)
        similarity = lcsubstring / len(pattern) if pattern else 0
        return similarity > threshold

    def lcs_length(self, a, b):
        dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
        for i in range(len(a)):
            for j in range(len(b)):
                if a[i] == b[j]:
                    dp[i + 1][j + 1] = dp[i][j] + 1
                else:
                    dp[i + 1][j + 1] = max(dp[i][j + 1], dp[i + 1][j])
        return dp[-1][-1]

    def is_similar(self, old_name, candidate, threshold=0.9):
        # Normalize both identifiers before comparison
        normalized_old = self.normalize_identifier(old_name)
        normalized_candidate = self.normalize_identifier(candidate)

        lcs = self.lcs_length(normalized_old, normalized_candidate)
        return lcs / len(normalized_old) > threshold if normalized_old else False

    def is_generic_word(self, word):
        """Check if a word is too generic to be useful for pattern matching."""
        generic_words = {
            'is', 'the', 'and', 'or', 'for', 'to', 'in', 'on', 'at', 'by', 'of', 'with',
            'from', 'into', 'during', 'including', 'until', 'against', 'among', 'throughout',
            'despite', 'towards', 'upon', 'concerning', 'about', 'between', 'through',
            'before', 'after', 'above', 'below', 'up', 'down', 'out', 'off', 'over', 'under',
            'again', 'further', 'then', 'once', 'here', 'there', 'when', 'where', 'why', 'how',
            'all', 'any', 'both', 'each', 'few', 'more', 'most', 'other', 'some', 'such',
            'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very',
            'can', 'will', 'just', 'don', 'should', 'now', 'get', 'go', 'come',
            'made', 'may', 'make', 'like', 'has', 'had', 'him', 'his', 'how', 'her',
            'my', 'me', 'more', 'she', 'an', 'do', 'did', 'we', 'would', 'you', 'your',
            'am', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'having', 'does',
            'doing', 'could', 'might', 'must', 'shall'
        }
        return word.lower() in generic_words

    def filterFilesWithLCS(self, files_to_inspect, rename_pairs, threshold=0.9):
        if not rename_pairs or len(rename_pairs) == 0:
            if len(files_to_inspect) < 100:
                return files_to_inspect
            else:
                return []

        filtered_files = set()

        # Strategy 1: Direct keyword matching (most precise)
        direct_matches = self.filter_by_direct_keywords(files_to_inspect, rename_pairs)
        filtered_files.update(direct_matches)
        print(f"Direct keyword matches: {len(direct_matches)}")

        # Strategy 2: LCSubstring with generic word filtering
        if len(direct_matches) == 0:  # If direct matching found zero files, try pattern matching
            lcs_matches = self.filter_by_lcsubstring_filtered(files_to_inspect, rename_pairs, threshold)
            filtered_files.update(lcs_matches)
            print(f"LCSubstring matches: {len(lcs_matches)}")

        result = list(filtered_files)
        print(f"Total filtered files: {len(result)} raw files: {len(files_to_inspect)}")
        return result

    def filter_by_direct_keywords(self, files_to_inspect, rename_pairs):
        """Filter files that contain the exact old identifiers from rename pairs."""
        filtered_files = []
        old_identifiers = {old_name for old_name, _ in rename_pairs}

        for file in files_to_inspect:
            try:
                file_contents = self.project.get_file_contents(file)
                # Check for exact matches of old identifiers
                for old_identifier in old_identifiers:
                    # Use word boundary to avoid partial matches
                    pattern = r'\b' + re.escape(old_identifier) + r'\b'
                    if re.search(pattern, file_contents, re.IGNORECASE):
                        filtered_files.append(file)
                        break
            except Exception as e:
                print(f"Error reading file {file}: {e}")
                continue

        return filtered_files

    def filter_by_lcsubstring_filtered(self, files_to_inspect, rename_pairs, threshold=0.9):
        """Filter files using LCSubstring but filter out generic patterns."""
        # Extract common patterns from rename pairs
        patterns = []
        for old_name, new_name in rename_pairs:
            pattern, lcs_score = self.extract_common_pattern(old_name, new_name)
            # Only consider meaningful patterns (not generic words and length > 3)
            if pattern and len(pattern) > 3 and not self.is_generic_word(pattern):
                patterns.append((pattern, lcs_score))

        print(f"Extracted meaningful patterns from rename pairs: {patterns}")

        if not patterns:
            return []

        filtered_files = []
        identifier_pattern = re.compile(r'\b\w+\b')

        for file in files_to_inspect:
            try:
                file_contents = self.project.get_file_contents(file)
                identifiers = set(identifier_pattern.findall(file_contents))

                # Check if any identifier matches any of the patterns
                for pattern, _ in patterns:
                    for candidate in identifiers:
                        if self.calculate_pattern_similarity(candidate, pattern, threshold):
                            filtered_files.append(file)
                            break
                    else:
                        continue
                    break
            except Exception as e:
                print(f"Error reading file {file}: {e}")
                continue

        return filtered_files


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
                            execution_details=""
                        )
                    ]
                )
                return plan
        except Exception as e:
            print(f"Error compiling and running replication for file {file_path}: {e}")
            traceback.print_exc()
        return None

