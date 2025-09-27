import copy
import json
import traceback
from collections import defaultdict
from concurrent.futures import as_completed
from json import JSONDecodeError

from langsmith.utils import ContextThreadPoolExecutor

from git import Commit
from pydantic.v1 import BaseModel, Field, PrivateAttr
from langchain_core.language_models import BaseChatModel
from typing import List, Iterable, Tuple, ClassVar, Any, Dict
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, BaseMessage
from langgraph.graph import END, START, StateGraph, MessagesState
from pathlib import Path
from typing import Optional, Set
import os
import re
import sqlite3

import refagent
import refagent.utils.project_manager as pm
import refagent.utils.intellij_server as ij
import refagent.agents.refactrix.planning as planning
import refagent.agents.refactrix.supported_refactorings as sup_ref
import refagent.refactoring_types.refactorings as refactoring_types
import refagent.utils.cache.prompt_cache as prompt_cache
import refagent.agents.memory.orm_memory as orm_memory
import refagent.agents.refactrix.analysis.scope as scope
from agents.memory.memory_models import RefactoringSuggestion


class CodeElement(BaseModel):
    file_path: str = Field(description="The file that was edited.")
    line_num: int = Field(description="The line number that was edited.")

class SearchResult(BaseModel):
    file_path: str
    line_nums: List[int]
    hit_count: int

    def __hash__(self):
        return hash(self.file_path)

class DataFlowResult(BaseModel):
    file_path: str
    depth: int


class Replication(BaseModel):
    model: BaseChatModel = Field(description="Langchain Chat model")
    edited_files: List[Path] = Field(description="Files that have already been edited.")
    project: pm.EvalProject = Field(description="The project object. Used to read file contents")
    example_changes: str = Field(description="The kinds of changes to replicate.")
    ide_server: ij.IntellijServer = Field(description="intellij server to interact with")
    executed_plan: planning.RefactoringPlan = Field(description="executed plan that needs replication")
    starting_file: str = Field(description="The first file that was edited.")
    refactoring_commit: Commit = Field(description="The commit that was edited.")
    oracle_data: Optional[List[refactoring_types.RefminerOut]] = Field(description="Oracle refactoring data for filtering files", default=None)
    
    # Memory system parameters
    benchmark_id: Optional[int] = Field(description="Benchmark ID for memory isolation", default=None)
    memory_database_url: str = Field(description="Memory database URL")
    enable_memory: bool = Field(description="Whether memory component is enabled", default=True)

    _operated_files: set = PrivateAttr(default=set())
    _processed_files: set = PrivateAttr(default=set())
    _oracle_files: Optional[set] = PrivateAttr(default=None)
    _stopping: bool = PrivateAttr(default=False)

    SUPPORTED_REPLICATIONS: ClassVar[List[sup_ref.SupportedRefactorings]] \
        = [sup_ref.SupportedRefactorings.RENAME,
           # sup_ref.SupportedRefactorings.CHANGE_SIGNATURE,
           # sup_ref.SupportedRefactorings.TYPE_CHANGE
           ]

    class Config:
        arbitrary_types_allowed = True

    @property
    def orm_memory(self) -> orm_memory.ORMRefactoringMemory:
        return orm_memory.ORMRefactoringMemory(self.memory_database_url)

    def get_files_inspection_data(self) -> dict:
        """Return the files inspection data for saving to results"""
        return {
            "files_matching_oracle": list(self._operated_files.intersection(self.all_oracle_files)),
            "count_files_matching_oracle": len(self._operated_files.intersection(self.all_oracle_files)),
            "operated_files_count": len(self._operated_files),
            "operated_files_list": list(self._operated_files),
            "inspected_files_count": len(self._processed_files),
            "inspected_files_list": list(self._processed_files)
        }

    def compile_and_run(self) -> Iterable[planning.RefactoringPlan]:
        self.init_replication_db()

        success_renames = self.orm_memory.get_all_successful_patterns()
        initial_files_to_inspect = self.get_linked_files_data_flow(renames=success_renames)

        # Add new API to get linked files based on symbol changes
        if len(success_renames)>0:
            keyword_search_files = self.keyword_search(success_renames)
            # Add API results to files_to_inspect
            keyword_search_files_ = list({i.file_path for i in keyword_search_files})
            initial_files_to_inspect_ = keyword_search_files_ + [i for i in initial_files_to_inspect if i not in keyword_search_files_] # prioritize search files.
            initial_files_to_inspect = initial_files_to_inspect_
            print(f"Added {len(keyword_search_files)} files from initial API call, total: {len(initial_files_to_inspect)}")
        else:
            print("No initial rename pairs found, skipping new API call")

        if len(initial_files_to_inspect) > 100:
            initial_files_to_inspect = initial_files_to_inspect[:100]
            print("Pruned files to first 100.")
        _files_in_oracle = self.filter_files_by_oracle(initial_files_to_inspect)

        should_replicate_msg = self.should_replicate()
        if not should_replicate_msg:
            # The change does not need replication to other files,
            # the developer did not ask for it.
            return None

        # Start iterative replication
        yield from self.iterative_replication(initial_files_to_inspect, success_renames)

        return None

    def handle_file(self, file_path) -> Optional[planning.RefactoringPlan]:
        try:
            if not self.continue_replication():
                print("Stopping replication because continue_replication is False")
                return None

            ask_replicate = self.compile(file_path)  # the edited file?
            should_replicate = ask_replicate.invoke({"messages": []})['messages'][-1]
            print(should_replicate.content)

            if 'YES' in should_replicate.content:  # should replicate the content
                self.add_file_to_replication_db(file_path)
                plan = planning.PlanningComponent(
                    initial_intent=str(self.latest_scope) + should_replicate.content,
                    model=self.model,
                    source_file_path=file_path,
                    source_code=self.project.get_file_contents(file_path),
                    # Pass memory parameters to planning component
                    benchmark_id=self.benchmark_id,
                    memory_database_url=self.memory_database_url,
                    enable_memory=True,
                    orm_memory=self.orm_memory
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

    def get_linked_files_data_flow(self, renames: List[RefactoringSuggestion]) -> List[str]:
        all_results: Dict[str, int] = {}
        for rename in renames:
            data_flow_results = self._data_flow_files(rename)
            for i in data_flow_results:
                all_results[i.file_path] = min(i.depth, all_results.get(i.file_path, 10000))

        files = sorted(all_results.keys(), key=lambda x: all_results[x])
        return files


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

    def filter_files_by_oracle(self, files_to_inspect: List[str]) -> List[str]:
        """Filter files based on oracle data - only keep files that have expected refactorings."""
        if not self.oracle_data:
            print("No oracle data available - keeping all files")
            return files_to_inspect
        
        # Filter files_to_inspect to only include those in oracle
        filtered_files = []
        for file_path in files_to_inspect:
            if self._file_matches_oracle(file_path, self.all_oracle_files):
                filtered_files.append(file_path)
        
        print(f"Oracle filtering: {len(files_to_inspect)} -> {len(filtered_files)} files")
        print(f"Oracle has {len(self.all_oracle_files)} files with expected refactorings")
        
        return filtered_files

    @property
    def all_oracle_files(self) -> Set[str]:
        if self._oracle_files is not None:
            return self._oracle_files
        oracle_files = set()
        for oracle_entry in self.oracle_data:
            if hasattr(oracle_entry, 'leftSideLocations') and oracle_entry.leftSideLocations:
                oracle_file = oracle_entry.leftSideLocations[0].filePath
                oracle_files.add(oracle_file)
        self._oracle_files = oracle_files
        return oracle_files

    def _file_matches_oracle(self, file_path: str, oracle_files: set) -> bool:
        """Check if a file matches any oracle file (handles different path formats)."""
        from pathlib import Path
        
        # Direct match
        if file_path in oracle_files:
            return True
        
        # Compare normalized paths
        file_path_obj = Path(file_path)
        for oracle_file in oracle_files:
            oracle_path_obj = Path(oracle_file)
            
            # Compare full paths
            if str(file_path_obj) == str(oracle_path_obj):
                return True
            
            # Compare just the filename if paths are different
            if file_path_obj.name == oracle_path_obj.name:
                return True
        
        return False

    def get_linked_files_via_api(self, rename_pair, return_elements=False):
        """Get linked files using the new search_symbol_changed API endpoint.
        
        Args:
            rename_pair: Tuple of (old_name, new_name)
            return_elements: If True, returns CodeElement objects; if False, returns file paths only
        """
        if not rename_pair or len(rename_pair) != 2:
            print("Invalid rename pair provided to API")
            return []
        
        old_name, new_name = rename_pair
        
        try:
            # Use IntellijServer call_tool method instead of hardcoded requests
            response = self.ide_server.call_tool('search_symbol_changed', 
                                               old_name=old_name, 
                                               new_name=new_name)
            
            # Check if the tool call failed
            if not response:
                print(f"Failed to get linked files: Empty response from server for {old_name} -> {new_name}")
                return []
            
            if response.startswith("tool call failed"):
                print(f"Failed to get linked files: {response}")
                return []
            
            try:
                linked_results = json.loads(response.strip())
                if not isinstance(linked_results, list):
                    print(f"Expected list response but got {type(linked_results)}: {linked_results}")
                    return []
                
                # Extract file paths or CodeElements from the response objects
                results = []
                for result in linked_results:
                    if isinstance(result, dict) and 'file_path' in result:
                        file_path = result['file_path']
                        if file_path.endswith('.java'):
                            if return_elements:
                                # Create CodeElement with line_num if available, default to 1
                                line_num = result.get('line_num', 1)
                                results.append(CodeElement(file_path=file_path, line_num=line_num))
                            else:
                                results.append(file_path)
                    else:
                        print(f"Unexpected result format: {result}")
                
                result_type = "CodeElements" if return_elements else "file paths"
                print(f"Found {len(results)} linked Java {result_type} via API for {old_name} -> {new_name}")
                return results
                
            except json.JSONDecodeError as e:
                print(f"Failed to parse JSON response: {e}")
                print(f"Raw response: '{response}'")
                return []
                
        except Exception as e:
            print(f"Error calling search_symbol_changed API: {e}")
            traceback.print_exc()
            return []

    def keyword_search(self, success_renames: List[RefactoringSuggestion]) -> List[SearchResult]:

        results = []
        rename_pairs = [(i.old_name, i.new_name) for i in success_renames]
        unique_rename_pairs = list(set(rename_pairs))
        print(f"[Search File API] Processing {len(unique_rename_pairs)} unique rename pairs (from {len(success_renames)} total)")
        edited_files = {i.file_path for i in success_renames}

        for file in edited_files:
            self.ide_server.open_file(Path(file)) #open file to search for files in that directory.

            for rename_pair in unique_rename_pairs:
                if not rename_pair or len(rename_pair) != 2:
                    print("Invalid rename pair provided to API")
                    continue

                old_name, new_name = rename_pair
                if len(old_name) < 6:
                    continue
                print(f"[Search File API] Searching for {old_name}")

                try:
                    # Use IntellijServer call_tool method instead of hardcoded requests
                    response = self.ide_server.call_tool('search_symbol',
                                                         symbol=old_name)

                    # Check if the tool call failed
                    if not response:
                        print(f"Failed to get linked files: Empty response from server for {old_name} -> {new_name}")
                        continue

                    if response.startswith("tool call failed"):
                        print(f"Failed to get linked files: {response}")
                        continue

                    try:
                        linked_results = json.loads(response)['files']
                        if not isinstance(linked_results, list):
                            print(f"Expected list response but got {type(linked_results)}: {linked_results}")
                            continue
                            # return []

                        # Extract file paths or CodeElements from the response objects
                        for result in linked_results:
                            if isinstance(result, dict) and 'file_path' in result:
                                file_path = result['file_path']
                                if file_path.endswith('.java') and file_path not in results:
                                    results.append(SearchResult(**result))

                        print(f"[Search File API] Finished search for {old_name}. total files found: {len(results)}. files: {results} ")
                    except json.JSONDecodeError as e:
                        print(f"Failed to parse JSON response: {e}")
                        print(f"Raw response: '{response}'")
                        continue
                        # return []

                except Exception as e:
                    print(f"Error calling search_symbol_changed API: {e}")
                    traceback.print_exc()
                    continue
                    # return []

        return results

    def should_replicate(self) -> bool:
        contains_supported_type = [i.refactoring_type in Replication.SUPPORTED_REPLICATIONS for i in
                                   self.executed_plan.steps]
        return any(contains_supported_type)


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
            messages = state['messages'] + [
                    SystemMessage("You are an expert developer who decides whether a "
                                  "refactoring needs to be replicated in a certain file, "
                                  "for the sake of consistency. "),
                    HumanMessage(
                        f"Here is the intent of the developer: "
                        f"{self.latest_scope}"
                        # f"Here are the kinds of refactorings that "
                        # f"need to be replicated. These refactorings were already performed:\n"
                        # f"{examples}"
                    ),
                    HumanMessage(f"Here are the contents of the file: {file_contents}"),
                    HumanMessage("Answer the following question: "
                                 f"Are there ANY code elements in {file_name}, "
                                 f"that could change? "
                                 f"Then, say YES/NO at the end of your reply,"
                                 f" indicating whether "
                                 f"there are any code elements that should change.")
                ]
            response = prompt_cache.prompt(self.model, copy.copy(messages))
            return {'messages': [response]}

        workflow = StateGraph(MessagesState)
        workflow.add_node("ask_replicate", ask_replicate)
        workflow.add_edge(START, "ask_replicate")

        return workflow.compile()

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

    def iterative_replication(self, initial_files: List[str], success_renames: List[RefactoringSuggestion]) -> Iterable[planning.RefactoringPlan]:
        """Perform iterative replication with cascading file discovery."""
        inspected_files = set() # total files that were inspected.
        operated_files = set()  # Track files that were actually operated on
        iteration = 0
        max_iterations = 3  # Prevent runaway discovery
        THRESHOLD_FILES_PER_ITERATION = 25

        # Start with initial files
        files_to_process = initial_files.copy()
        
        while files_to_process and iteration < max_iterations:
            print(f"[ITERATIVE REPLICATION] Iteration {iteration + 1}, processing {len(files_to_process)} files")
            
            # Process current batch of files
            successful_renames_this_iteration: List[RefactoringSuggestion] = []
            count_inspected_files_i = 0
            self.clear_files_in_db()
            
            with ContextThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(self.handle_file, file_path): file_path for file_path in files_to_process}
                for i, future in enumerate(as_completed(futures)):
                    if count_inspected_files_i >= THRESHOLD_FILES_PER_ITERATION:
                        self._stopping = True
                        print(f"Stopping this iteration because more then {THRESHOLD_FILES_PER_ITERATION} "
                              f"were processed successfully.")
                        break
                    file_path = futures[future]
                    print(f"completed planning for: {i + 1}/{len(futures)} in iteration {iteration + 1}")
                    result = future.result()
                    if result is not None:
                        yield result
                        operated_files.add(file_path)
                        count_inspected_files_i += 1
                        # Extract successful renames from this file's operation
                        # todo: change this to have a just call all renames and fiter
                        file_renames = self.extract_successful_renames_from_completed_file(file_path)
                        successful_renames_this_iteration += file_renames

                    inspected_files.add(file_path)

            print(f"[ITERATIVE REPLICATION] Iteration {iteration + 1} completed. Found {len(successful_renames_this_iteration)} successful renames")
            print(f"[ITERATIVE REPLICATION] Rename instances {successful_renames_this_iteration} successful renames")
            
            # If no successful renames, stop iterating
            if len(successful_renames_this_iteration) == 0:
                print(f"[ITERATIVE REPLICATION] No successful renames in iteration {iteration + 1}, stopping")
                break
                
            # prioritize keyword search files because it searches in same directory.
            keyword_search_files = list({i.file_path for i in
                          self.keyword_search(successful_renames_this_iteration)})
            new_renames = [i for i in self.orm_memory.get_all_successful_patterns() if i not in success_renames]
            data_flow_files = [i for i in self.get_linked_files_data_flow(new_renames)
                               if i not in keyword_search_files]
            new_files = keyword_search_files + data_flow_files
            new_files = [f for f in new_files if f not in inspected_files]
            if len(new_files) > 100:
                new_files = new_files[:100]
                print("Pruned files to 100.")

            if not new_files:
                print(f"[ITERATIVE REPLICATION] No new files found in iteration {iteration + 1}, stopping")
                break
                
            print(f"[ITERATIVE REPLICATION] Found {len(new_files)} new files for next iteration")
            files_to_process = new_files
            current_rename_pairs = successful_renames_this_iteration
            iteration += 1
        
        print(f"[ITERATIVE REPLICATION] Completed after {iteration} iterations")
        print(f"[ITERATIVE REPLICATION] Total files processed: {len(inspected_files)}")
        print(f"[ITERATIVE REPLICATION] Files with operations: {len(operated_files)}")
        
        # Store operated files for potential saving/tracking
        self._operated_files = operated_files
        self._processed_files = inspected_files
        
        return None
    
    def extract_successful_renames_from_completed_file(self, file_path: str) -> List[RefactoringSuggestion]:
        try:
            # Try to get successful renames from memory for this file
            memory_renames = self.orm_memory.get_successful_renames_for_file(file_path)
            print(f"[RENAME EXTRACTION] Total successful renames extracted for {file_path}: {len(memory_renames)}")
            return memory_renames
        except Exception as e:
            print(f"[RENAME EXTRACTION] Error extracting from memory: {e}")
            return []

    def _data_flow_files(self, rename: RefactoringSuggestion) -> List[DataFlowResult]:

        # try to pick up the new file in case of rename class.
        if rename.code_element_type == 'class' and rename.old_name in rename.file_path:
            file_path = rename.file_path.replace(rename.old_name, rename.new_name)
        else:
            file_path = rename.file_path

        self.ide_server.open_file(Path(file_path))
        response = self.ide_server.call_tool('data-flow',
                                  old_name=rename.new_name, # we would like to search for the new name
                                  new_name=rename.new_name+'X', # throwaway param
                                  code_element_type=rename.code_element_type,
                                  line_num=rename.line_num
                                  )
        try:
            json_ = json.loads(response)
            return [DataFlowResult(**i) for i in json_]
        except JSONDecodeError:
            print("data-flow api threw error: {}".format(response))
            print(f"old_name={rename.old_name}, new_name={rename.new_name}, file_path={rename.file_path}")
            return []

    def continue_replication(self):
        """Check whether too many files have been edited."""

        return self.count_files_in_db() < 25

    def init_replication_db(self):
        conn = self.get_new_conn()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS replication_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE NOT NULL
            )
        """)
        conn.commit()

    def add_file_to_replication_db(self, file_path: str):
        conn = self.get_new_conn()
        cursor = conn.cursor()
        cursor.execute("""
                       INSERT
                       OR IGNORE INTO replication_files (file_path) VALUES (?)
                       """, (file_path,))
        conn.commit()

    def get_new_conn(self):
        conn = sqlite3.connect(refagent.repo_root.joinpath('.replication.db'))
        return conn

    def count_files_in_db(self) -> int:
        conn = self.get_new_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM replication_files")
        return cursor.fetchone()[0]

    def clear_files_in_db(self):
        conn = self.get_new_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM replication_files")
        conn.commit()

    @property
    def latest_scope(self) -> scope.RenameScope:
        latest_scope = self.orm_memory.get_latest_scope()
        assert latest_scope is not None
        return latest_scope



class SimpleReplication(Replication):

    def handle_file(self, file_path) -> Optional[planning.RefactoringPlan]:
        try:
            if not self.continue_replication():
                print("Stopping replication because continue_replication is False")
                return None

            ask_replicate = self.compile(file_path)
            should_replicate = ask_replicate.invoke({"messages": []})['messages'][-1]
            print(should_replicate.content)
            if 'YES' in should_replicate.content:  # should replicate the content
                self.add_file_to_replication_db(file_path)
                plan = planning.RefactoringPlan(
                    steps=[
                        planning.PlanningStep(
                            reason=str(self.latest_scope),
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

