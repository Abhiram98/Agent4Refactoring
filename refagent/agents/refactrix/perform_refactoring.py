from collections import defaultdict
from json import JSONDecodeError
from time import sleep

from pydantic.v1 import BaseModel, Field, PrivateAttr  # to comply with grazie models
from typing import List, Dict, Optional
from langchain_core.output_parsers import PydanticOutputParser
import json
import re
from langchain_core.language_models import BaseChatModel
from langgraph.graph.graph import CompiledGraph
from langgraph.graph import END, START, StateGraph, MessagesState
from langgraph.prebuilt import ToolNode
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    ToolMessage,
    BaseMessage,
    ToolCall,
    SystemMessage,
)
from pathlib import Path


import refagent.agents.refactrix.supported_refactorings as sup_ref
import refagent.utils.intellij_server as ij
import refagent.utils.code_utils as code_utils
import refagent.agents.refactrix.review.critique as critique
import refagent.utils.cache.prompt_cache as prompt_cache
import refagent.agents.refactrix.analysis.scope as scope
from refagent.agents.refactrix.analysis.refine_intent import RefineIntent
from refagent.agents.refactrix.review.critique import CritiqueResult
from refagent.agents.refactrix.rename_suggestions import (
    RenameAnalysis,
    RenameSuggestion,
    ValidatedRenames,
    RenameSuggestionValidated,
    RenameAnalysisWithCommentStartLine,
    CodeElementType,
)
from refagent.agents.memory.orm_memory import ORMRefactoringMemory
from multiprocessing import Process


class PerformRefactoring(BaseModel):
    tools: List = Field(
        description="refactoring tools that are available"
    )  # TODO: Type annotate with tool type.
    retry_count: int = Field(
        description="how many times to allow the LLM to retry", default=2
    )
    model: BaseChatModel = Field(description="Langchain Chat model")
    reason: str = Field(
        description="Reason to perform the refactoring. Usually provided by the LM."
    )
    refactoring_type: sup_ref.SupportedRefactorings = Field(
        description="The type of refactoring to be performed."
    )
    rel_file_path: str = Field(
        description="relative file path from repo root. file to be edited."
    )
    ide_server: ij.IntellijServer = Field(
        description="ide server object. Used to open files."
    )
    refactoring_success: bool = Field(
        description="whether the refactoring was successful or not.", default=False
    )
    critique_component: Optional[critique.CritiqueComponent] = Field(
        description="Critique component for validating suggestions", default=None
    )
    disable_scope_refinement: bool = Field(
        description="whether to disable scope refactoring", default=False
    )

    trigger_renames: bool = Field(
        description="whether to actually trigger renames from the agent side",
        default=True,
    )

    _file_open_status: bool = PrivateAttr(default=False)
    _active_tool_call: List = PrivateAttr(default="")
    _retry_iteration: int = PrivateAttr(default=1)
    _performed_refactorings: List = PrivateAttr(default=[])
    _tool_call_map: Dict = PrivateAttr(default=defaultdict(dict))
    _critique_retry_count: int = PrivateAttr(default=0)
    _auto_suggest_executor: Optional[Process] = PrivateAttr(default=None)

    benchmark_id: Optional[int] = Field(
        description="Current benchmark ID for memory isolation", default=None
    )
    memory_database_url: str = Field(
        description="Database URL for memory storage",
        default="sqlite:///refactoring_memory.db",
    )
    replication_enabled: Optional[bool] = Field(
        description="Whether replication is enabled for this run", default=None
    )
    enable_memory: bool = Field(
        description="Whether memory component is enabled for storing and retrieving suggestions",
        default=True,
    )

    _orm_memory: Optional[ORMRefactoringMemory] = PrivateAttr(default=None)

    class Config:
        arbitrary_types_allowed = True

    @property
    def orm_memory(self) -> ORMRefactoringMemory:
        if self._orm_memory is not None:
            return self._orm_memory
        self._orm_memory = ORMRefactoringMemory(self.memory_database_url)
        if self.benchmark_id:
            self.orm_memory.start_session(
                benchmark_id=self.benchmark_id,
                replication_enabled=self.replication_enabled,
            )
            if self.enable_memory:
                print(
                    f"[MEMORY INIT] Memory session started for benchmark {self.benchmark_id} - feedback enabled"
                )
            else:
                print(
                    f"[MEMORY INIT] Memory session started for benchmark {self.benchmark_id} - feedback disabled (storage only for evaluation)"
                )

        return self._orm_memory

    @property
    def new_intent(self) -> Optional[scope.RenameScope]:
        """return the new intent if generated, else none"""
        return self.orm_memory.get_latest_scope()

    def get_tool_call_str(self, tool_call: Optional[ToolCall] = None) -> str:
        if tool_call is None:
            if not self._active_tool_call:
                return "no tool calls"
            tool_call = self._active_tool_call[0]
        name = tool_call["name"]
        args = ", ".join([f"{k}={v}" for k, v in tool_call["args"].items()])
        tool_call_str = f"{name}({args})"
        return tool_call_str

    def compile(self) -> CompiledGraph:

        def open_file(state: MessagesState):
            response = self.ide_server.open_file(Path(self.rel_file_path))
            self.ide_server.call_tool(
                "/review/set_inspecting_file", rel_file_path=self.rel_file_path
            )

            self.ide_server.call_tool(
                "review/noop",
                status=f"Inspecting file : {self.rel_file_path.split('/')[-1]}",
            )

            if response.startswith("tool call failed "):
                return {"messages": HumanMessage("failed to open file")}
            self._file_open_status = True
            return {
                "messages": [
                    HumanMessage(
                        f"Opened file successfully. "
                        f"You are now editing {self.rel_file_path}"
                    )
                ]
            }

        def opened_file_message():
            return HumanMessage(
                f"Created and opened file successfully. "
                f"You are now editing {self.rel_file_path}"
            )

        def successful_file_open(state: MessagesState):
            return self._file_open_status

        def call_llm(state: MessagesState):
            """Call LLM with memory-enhanced feedback for retry attempts."""
            # Get current LLM iteration from memory (always track for evaluation purposes)
            current_llm_iteration = 0
            if self.orm_memory.current_session_id:
                try:
                    current_llm_iteration = self.orm_memory.get_current_llm_iteration()
                except Exception as e:
                    print(f"[LLM DEBUG] Error getting current LLM iteration: {e}")

            # Check if we've exceeded max LLM iterations (3 total across entire session)
            max_llm_iterations = 3
            if current_llm_iteration >= max_llm_iterations:
                print(
                    f"[LLM DEBUG] Max LLM iterations ({max_llm_iterations}) exceeded, stopping LLM calls"
                )

                # End memory session if we have one (always end since we always initialize for evaluation)
                if self.orm_memory.current_session_id:
                    self.orm_memory.end_session()

                return {
                    "messages": [
                        AIMessage(
                            f"Stopping LLM calls after {max_llm_iterations} total iterations. Unable to generate valid rename suggestions."
                        )
                    ]
                }

            # Increment LLM iteration counter in memory (always track for evaluation purposes)
            if self.orm_memory.current_session_id:
                try:
                    current_llm_iteration = self.orm_memory.increment_llm_iteration()
                    print(
                        f"[LLM DEBUG] LLM iteration {current_llm_iteration}/{max_llm_iterations} (feedback enabled)"
                    )

                except Exception as e:
                    print(f"[LLM DEBUG] Error tracking LLM iteration: {e}")
            else:
                print(
                    f"[LLM DEBUG] LLM call attempt {self._retry_iteration} (no memory tracking)"
                )

            # Get FRESH source code for every LLM call to avoid stale suggestions
            try:
                current_file_content = self.ide_server.call_tool_get("get_source_code")
                if current_file_content:
                    print(
                        f"[LLM DEBUG] Retrieved fresh source code ({len(current_file_content)} chars)"
                    )
                else:
                    print(
                        f"[LLM DEBUG] Warning: Could not get current source code, using original"
                    )
                    current_file_content = None
            except Exception as e:
                print(f"[LLM DEBUG] Error getting fresh source code: {e}")
                current_file_content = None

            # Add memory constraints if memory is enabled and available (not just on retry)
            memory_constraints = get_memory_constraints(current_llm_iteration)

            if current_llm_iteration > 1:
                retry_warning = (
                    f"\n\n LLM CALL #{current_llm_iteration}: Find what other elements are left to rename. "
                    f"Check the MEMORY info below: use AVOID lines to skip, COMPLETED lines to not repeat, "
                    f"and SUCCESS patterns as guidance."
                )
                state["messages"][-1].content += retry_warning

            # Create output parser for structured JSON response
            # parser = PydanticOutputParser(pydantic_object=RenameAnalysis)
            # METHOD = "method"
            # VARIABLE = "variable"
            # CLASS = "class"
            # PARAMETER = "parameter"
            # FIELD = "field"
            # Add JSON format instructions to the last message
            format_instructions = (
                # "\n\nIMPORTANT: Respond with a JSON object containing your analysis and rename suggestions. "
                f"Use this exact format: Json Object with two keys - 'analysis' and 'rename_suggestions'. "
                f"The `rename_suggestions` should be a json list of object with the keys - `old_name`, `new_name`, `line_num`, `code_element_type`(method/variable/class/parameter/field), `reason`)\n\n"
                f""
                f"Example: "
                """{
                  "analysis" : "REFACTORING_NEEDED: Found 1 more instance to rename.",
                  "rename_suggestions" : [ {
                    "old_name" : "<old_name>",
                    "new_name" : "<new_name>",
                    "line_num" : 120,
                    "code_element_type" : "method",
                    "reason" : "Renaming the method <old_name> satisfies the pattern, because <reason>"
                  } ]
                }"""
                f"\nNote:\n"
                # f"- If you find rename suggestions, include them in the 'rename_suggestions' array\n"
                # f"- If NO renames are needed (refactoring is complete), set 'rename_suggestions' to an empty array []\n"
                f"- When refactoring is complete, start your 'analysis' field with: 'REFACTORING_COMPLETE: '\n"
                f"- When more renames are needed, start your 'analysis' field with: 'REFACTORING_NEEDED: '\n"
                f"- For 'code_element_type', use only these values: 'method', 'variable', 'class', 'parameter', 'field'\n"
                # f"- DO NOT suggest renaming import statements - focus only on variables, methods, classes, fields, and parameters within the code\n"
                # f"- IGNORE import lines (lines starting with 'import') - only rename actual code elements\n"
                # f"Example for completion: {{\"analysis\": \"REFACTORING_COMPLETE: All instances have been renamed.\", \"rename_suggestions\": []}}\n"
                # f"Example for more work: {{\"analysis\": \"REFACTORING_NEEDED: Found 3 more instances to rename.\", \"rename_suggestions\": [...]}}"
            )

            # Only pass the system prompt to avoid prompt bloating
            messages: List[BaseMessage] = []
            if self.new_intent is not None:
                messages.append(self.generate_system_prompt())
            else:
                messages.append(state["messages"][0])

            example_message = self.get_examples_message()
            if example_message is not None:
                messages.append(example_message)

            file_contents_msg = opened_file_message()
            if current_file_content:
                numbered_code = code_utils.add_line_numbers(current_file_content)
                file_contents_msg.content += f"\n\n=== CURRENT SOURCE CODE (UPDATED) ===\n{numbered_code}\n=== END SOURCE CODE ===\n"
            if memory_constraints:
                file_contents_msg.content = (
                    file_contents_msg.content
                    + "\nIMPORTANT:\n"
                    + memory_constraints
                    + "\n"
                )
            file_contents_msg.content += format_instructions
            messages.append(file_contents_msg)

            self.ide_server.call_tool("review/noop", status="Prompting the LLM.")
            # Start showing auto-suggestions to UI in parallel
            self._auto_suggest_executor = Process(
                target=self.show_auto_suggestions_to_ui
            )
            self._auto_suggest_executor.start()

            # Run LLM prompt (main thread)
            response = prompt_cache.prompt_stream(
                self.model, messages, callback=self.analyse_chunk_deco()
            )

            # Shutdown the executor (don't wait for auto-suggestions to complete)
            self._auto_suggest_executor.terminate()

            return {"messages": [response]}

        def get_memory_constraints(current_llm_iteration):
            memory_constraints = ""
            if hasattr(self, "benchmark_id") and self.benchmark_id:
                try:
                    if current_llm_iteration <= 1:
                        # First LLM call: Get broader memory feedback from all files in this benchmark
                        print(
                            f"[MEMORY DEBUG] First LLM call - getting cross-file memory feedback"
                        )
                        memory_feedback = self.orm_memory.get_memory_feedback(
                            benchmark_id=self.benchmark_id,
                            file_path=None,  # No file constraint for broader context
                            use_line_numbers=False,
                        )
                    else:
                        # Subsequent LLM calls: Get file-specific memory feedback
                        print(
                            f"[MEMORY DEBUG] LLM call #{current_llm_iteration} - getting file-specific memory feedback"
                        )
                        memory_feedback = self.orm_memory.get_memory_feedback(
                            benchmark_id=self.benchmark_id, file_path=self.rel_file_path
                        )

                    if memory_feedback:
                        memory_constraints = memory_feedback
                        print(
                            f"[MEMORY DEBUG] Adding memory constraints: {memory_feedback}"
                        )
                except Exception as e:
                    print(f"[MEMORY DEBUG] Error getting memory feedback: {e}")
            elif not self.enable_memory:
                print(f"[MEMORY DEBUG] Memory disabled - skipping memory feedback")
            return memory_constraints

        def parse_json_response(state: MessagesState):
            """Parse and validate JSON response from LLM."""
            last_message = state["messages"][-1]

            # print(f"[JSON DEBUG] Parsing LLM response: {last_message.content[:200]}...")

            # Check if LLM gave up BEFORE trying to parse as JSON
            if llm_gave_up(state):
                print(
                    f"[JSON DEBUG] Detected LLM gave up message - not attempting JSON parsing"
                )
                return {
                    "messages": state["messages"]
                }  # Pass through the stopping message

            try:
                # Try to parse the JSON response
                parser = PydanticOutputParser(pydantic_object=RenameAnalysis)
                rename_analysis = parser.parse(last_message.content)

                print(
                    f"[JSON DEBUG] Successfully parsed {len(rename_analysis.rename_suggestions)} rename suggestions"
                )
                for i, suggestion in enumerate(rename_analysis.rename_suggestions):
                    print(
                        f"[JSON DEBUG] Suggestion {i}: {suggestion.old_name} → {suggestion.new_name} at line {suggestion.line_num} - type {suggestion.code_element_type}"
                    )

                # augment suggestions
                rename_analysis.rename_suggestions += self.get_auto_suggestions()

                rename_analysis.rename_suggestions = self.validate_rename_objects(
                    rename_analysis.rename_suggestions
                )
                # Store the parsed analysis in the message for the next step
                parsed_message = AIMessage(
                    content=f"Parsed rename analysis: {rename_analysis.analysis}",
                    additional_kwargs={"rename_analysis": rename_analysis.dict()},
                )

                return {"messages": state["messages"] + [parsed_message]}

            except Exception as e:
                print(f"[JSON DEBUG] Failed to parse JSON response: {e}")
                error_message = HumanMessage(
                    f"Failed to parse your JSON response. Error: {str(e)}. "
                    f"Please provide a valid JSON response following the exact format specified."
                )
                return {"messages": state["messages"] + [error_message]}

        def check_completion(state: MessagesState):
            """Check if there are more renames needed after successful tool calls."""
            print("[COMPLETION DEBUG] Checking if more renames are needed...")

            # Get current file content to analyze for remaining renames
            try:
                current_file_content = self.ide_server.call_tool_get("get_source_code")
                if not current_file_content:
                    print("[COMPLETION DEBUG] Could not get current file content")
                    return {
                        "messages": [
                            HumanMessage("Could not analyze file for remaining renames")
                        ]
                    }

                # Get memory information about what has already been tried (always available for evaluation)
                memory_context = ""
                if hasattr(self, "benchmark_id") and self.benchmark_id:
                    try:
                        # Get memory feedback to understand what was already attempted
                        memory_feedback = self.orm_memory.get_memory_feedback(
                            benchmark_id=self.benchmark_id,
                            file_path=self.rel_file_path,
                            limit=100,  # Get more context for completion check
                        )

                        # Get detailed memory stats
                        memory_stats = self.orm_memory.get_memory_stats(
                            self.benchmark_id, self.rel_file_path
                        )

                        if memory_feedback:
                            if self.enable_memory:
                                # Include memory context in LLM prompt when feedback is enabled
                                memory_context = (
                                    f"\n\nMEMORY CONTEXT:\n{memory_feedback}\n"
                                )
                                memory_context += f"MEMORY STATS: {memory_stats['total_attempts']} total suggestions tried, "
                                memory_context += f"{memory_stats['valid_count']} successful, {memory_stats['invalid_count']} failed.\n"
                                print(
                                    f"[COMPLETION DEBUG] Added memory context to LLM: {memory_stats['total_attempts']} suggestions tried"
                                )
                            else:
                                # Don't include memory context in LLM prompt, but log for evaluation
                                memory_context = "\n\nMEMORY CONTEXT: Memory feedback disabled for this run.\n"
                                print(
                                    f"[COMPLETION DEBUG] Memory available but feedback disabled: {memory_stats['total_attempts']} suggestions tried (not shared with LLM)"
                                )
                        else:
                            memory_context = "\n\nMEMORY CONTEXT: No previous attempts recorded for this file.\n"

                    except Exception as e:
                        print(f"[COMPLETION DEBUG] Error getting memory context: {e}")
                        memory_context = "\n\nMEMORY CONTEXT: Could not retrieve memory information.\n"

                # Add line numbers to current code for precise analysis
                numbered_code = code_utils.add_line_numbers(current_file_content)

                # Enhanced completion check message with memory context
                completion_check_message = HumanMessage(
                    f"Please analyze this code and determine if there are any remaining renames that need to be done "
                    f"based on the original refactoring intent: {self.reason}\n\n"
                    f"Current code (with line numbers):\n{numbered_code}\n"
                    f"{memory_context}\n"
                    f"INSTRUCTIONS:\n"
                    f"1. Review the memory context to see what renames have already been attempted\n"
                    f"2. Focus on parts of the code that haven't been addressed yet\n"
                    f"3. Look for any remaining instances that should be renamed but weren't suggested before\n"
                    # f"4. Ignore patterns that were already tried and failed (marked as FAILED in memory)\n"
                    f"4. Consider successful patterns as a guide for what works\n"
                    f"5. Use the line numbers to identify specific locations if suggesting renames\n\n"
                    f"If you find any remaining renames needed, respond with 'CONTINUE_REFACTORING' and explain what needs to be renamed. "
                    f"If all necessary renames have been completed, respond with 'REFACTORING_COMPLETE'."
                )

                completion_response = prompt_cache.prompt(
                    self.model, [completion_check_message]
                )
                print(
                    f"[COMPLETION DEBUG] Completion check response: {completion_response.content[:200]}..."
                )

                return {"messages": state["messages"] + [completion_response]}

            except Exception as e:
                print(f"[COMPLETION DEBUG] Error during completion check: {e}")
                # If we can't check, assume we're done
                return {
                    "messages": state["messages"]
                    + [HumanMessage("REFACTORING_COMPLETE")]
                }

        def success_handler(state: MessagesState):
            print(
                "The following refactorings have been performed successfully-> "
                f"{self.get_successfull_refactorings()}"
            )
            self.refactoring_success = True
            success_msg = state["messages"][-1].content

            tool_call_status = str(self._active_tool_call)
            if "replace_file_contents" in str(self._active_tool_call):
                tool_call_status = "replaced file contents."
            final_message = (
                "Successfully performed the refactoring. " f"{tool_call_status}"
            )
            if success_msg != "success":
                final_message += success_msg
            return {"messages": [HumanMessage(final_message)]}

        def failure_handler(state: MessagesState):
            # Check if any refactorings were successful before declaring complete failure
            successful_refactorings = self.get_successfull_refactorings()

            if successful_refactorings:
                # Partial success - some refactorings worked
                print(
                    f"Partial refactoring success. Some refactorings were completed: {successful_refactorings}"
                )
                self.refactoring_success = (
                    True  # Mark as success since some work was done
                )

                # Check if LLM gave up before generating tool calls
                if llm_gave_up(state):
                    return {
                        "messages": [
                            HumanMessage(
                                f"Partially completed the refactoring. "
                                f"Successfully performed: {successful_refactorings}. "
                                f"However, LLM was unable to complete all remaining suggestions after multiple attempts."
                            )
                        ]
                    }

                tool_call_str = self.get_tool_call_str()

                # Find the actual tool failure message from ToolMessages
                tool_failure_reason = "Unknown tool failure"
                for message in reversed(
                    state["messages"]
                ):  # Search backwards for most recent ToolMessage
                    if (
                        isinstance(message, ToolMessage)
                        and "success" not in message.content.lower()
                    ):
                        tool_failure_reason = message.content
                        break

                return {
                    "messages": [
                        HumanMessage(
                            f"Partially completed the refactoring. "
                            f"Successfully performed: {successful_refactorings}. "
                            f"However, the final attempt failed: {tool_call_str} - {tool_failure_reason}."
                        )
                    ]
                }
            else:
                # Complete failure - no refactorings succeeded
                print("Failed to perform the refactoring.")

                # Check if LLM gave up before generating tool calls
                if llm_gave_up(state):
                    return {
                        "messages": [
                            HumanMessage(
                                "Cannot perform this refactoring. "
                                "LLM was unable to generate valid rename suggestions after multiple attempts. "
                                "The code may not contain the expected patterns for this refactoring."
                            )
                        ]
                    }

                tool_call_str = self.get_tool_call_str()

                # Find the actual tool failure message from ToolMessages
                tool_failure_reason = "Unknown tool failure"
                for message in reversed(
                    state["messages"]
                ):  # Search backwards for most recent ToolMessage
                    if (
                        isinstance(message, ToolMessage)
                        and "success" not in message.content.lower()
                    ):
                        tool_failure_reason = message.content
                        break

                return {
                    "messages": [
                        HumanMessage(
                            "Cannot perform this refactoring. "
                            f"{tool_call_str} failed. "
                            f"Reason: {tool_failure_reason}. "
                            f"CALL the TOOL differently, next time."
                        )
                    ]
                }

        def should_continue_refactoring(state: MessagesState) -> bool:
            """Check if we should continue refactoring based on completion check."""
            last_message = state["messages"][-1]
            continue_refactoring = "CONTINUE_REFACTORING" in last_message.content

            if continue_refactoring:
                print(
                    "[COMPLETION DEBUG] More renames needed - continuing with next LLM iteration"
                )
            else:
                print("[COMPLETION DEBUG] Refactoring complete - finishing")

            return continue_refactoring

        def retry_condition(state: MessagesState) -> str:
            # Check for LLM completion signal first
            for message in reversed(state["messages"][-3:]):
                if (
                    isinstance(message, HumanMessage)
                    and message.content == "REFACTORING_COMPLETED_BY_LLM"
                ):
                    print(
                        f"[RETRY DEBUG] LLM detected completion - going to success handler"
                    )
                    return "success_handler"

            # Get recent ToolMessages from the state (these are the responses to tool calls)
            recent_tool_messages: List[ToolMessage] = []
            for message in reversed(state["messages"]):
                if isinstance(message, ToolMessage):
                    recent_tool_messages.append(message)
                    self.update_tool_call_map(message)
                else:
                    # Stop when we hit a non-ToolMessage (like AIMessage with tool calls)
                    break

            print(
                f"[RETRY DEBUG] Found {len(recent_tool_messages)} recent tool messages"
            )

            # Check if any tool calls succeeded
            tool_call_success = any(
                "success" in tool_response.content.lower()
                for tool_response in recent_tool_messages
            )

            print(f"[RETRY DEBUG] Tool call success: {tool_call_success}")

            if tool_call_success:
                print(f"[RETRY DEBUG] Some tools succeeded - checking completion")
                return "check_completion"  # Check if more renames are needed

            # Check if we've reached max LLM iterations (always check since we always track for evaluation)
            current_llm_iteration = 0
            try:
                current_llm_iteration = self.orm_memory.get_current_llm_iteration()
            except Exception as e:
                print(f"[RETRY DEBUG] Error getting current LLM iteration: {e}")

            if current_llm_iteration >= 3:  # Max 3 LLM iterations
                print(
                    f"[RETRY DEBUG] Max LLM iterations (3) exceeded - going to failure handler"
                )
                return "failure_handler"

            print(f"[RETRY DEBUG] No success, retrying LLM")
            return "llm_tool"  # retry the tool call

        def critique_json_suggestions(state: MessagesState):
            """Critique JSON rename suggestions and store results in memory."""
            last_message = state["messages"][-1]

            print(
                f"[CRITIQUE DEBUG] Critiquing JSON suggestions from message type: {type(last_message)}"
            )

            # If no critique component, proceed without validation
            if not self.critique_component:
                print(
                    f"[CRITIQUE DEBUG] No critique component available - accepting all suggestions"
                )

                # Extract rename analysis from message
                if (
                    not hasattr(last_message, "additional_kwargs")
                    or "rename_analysis" not in last_message.additional_kwargs
                ):
                    print(f"[CRITIQUE DEBUG] No rename analysis found in message")
                    return {
                        "messages": [
                            HumanMessage(
                                "No rename suggestions found to critique. Please provide rename suggestions in the correct JSON format."
                            )
                        ]
                    }

                # Parse the rename analysis
                rename_analysis_data = last_message.additional_kwargs["rename_analysis"]
                rename_analysis = RenameAnalysis(**rename_analysis_data)

                print(
                    f"[CRITIQUE DEBUG] Found {len(rename_analysis.rename_suggestions)} suggestions - accepting all without validation"
                )

                # When critique is disabled, mark ALL suggestions as valid
                valid_suggestions = rename_analysis.rename_suggestions
                invalid_suggestions = []

                # Create validated renames result with all suggestions marked as valid
                validated_result = ValidatedRenames(
                    valid_suggestions=valid_suggestions,
                    invalid_suggestions=invalid_suggestions,
                    critique_feedback=f"Critique disabled - accepted all {len(valid_suggestions)} suggestions without validation",
                )

                # Store validated result for tool call generation
                result_message = AIMessage(
                    content=f"Critique disabled: accepting all {len(valid_suggestions)} suggestions without validation",
                    additional_kwargs={"validated_renames": validated_result.dict()},
                )

                return {"messages": state["messages"] + [result_message]}

            # Extract rename analysis from message
            if (
                not hasattr(last_message, "additional_kwargs")
                or "rename_analysis" not in last_message.additional_kwargs
            ):
                print(f"[CRITIQUE DEBUG] No rename analysis found in message")
                return {
                    "messages": [
                        HumanMessage(
                            "No rename suggestions found to critique. Please provide rename suggestions in the correct JSON format."
                        )
                    ]
                }

            # Parse the rename analysis
            rename_analysis_data = last_message.additional_kwargs["rename_analysis"]
            rename_analysis = RenameAnalysisWithCommentStartLine(**rename_analysis_data)

            print(
                f"[CRITIQUE DEBUG] Found {len(rename_analysis.rename_suggestions)} suggestions to validate"
            )

            # Validate each rename suggestion
            valid_suggestions = []
            invalid_suggestions = []

            self.ide_server.call_tool(
                "/review/add_total_renames",
                count=len(rename_analysis.rename_suggestions),
            )

            for suggestion in rename_analysis.rename_suggestions:
                should_break = False
                print(
                    f"[CRITIQUE DEBUG] Validating: {suggestion.old_name} → {suggestion.new_name} at line {suggestion.start_line_comments or suggestion.line_num}"
                )

                # Check if this suggestion was previously invalid (memory check - only if memory enabled)
                previously_invalid = False
                if (
                    self.enable_memory
                    and hasattr(self, "benchmark_id")
                    and self.benchmark_id
                ):
                    try:
                        previously_invalid = (
                            self.orm_memory.is_suggestion_previously_invalid(
                                benchmark_id=self.benchmark_id,
                                file_path=suggestion.resolved_file_path
                                or self.rel_file_path,
                                old_name=suggestion.old_name,
                                new_name=suggestion.new_name,
                                line_num=suggestion.resolved_start_line
                                or suggestion.start_line_comments
                                or suggestion.line_num,
                            )
                        )
                        if previously_invalid:
                            print(
                                f"[MEMORY DEBUG] Suggestion '{suggestion.old_name}' → '{suggestion.new_name}' was previously invalid"
                            )
                            continue
                    except Exception as e:
                        print(
                            f"[MEMORY DEBUG] Error checking previous suggestions: {e}"
                        )

                critique_result = self.critique_component.validate_suggestion(
                    suggestion=suggestion, rel_file_path=self.rel_file_path
                )

                print(
                    f"[CRITIQUE DEBUG] Validation result: is_valid={critique_result.is_valid}, feedback='{critique_result.feedback}'"
                )

                self.store_critque_results(
                    critique_result, previously_invalid, rename_analysis, suggestion
                )

                if (
                    not self.disable_scope_refinement and not critique_result.is_valid
                ):  # go here only if scope refinement is enabled.
                    if (
                        self.orm_memory.get_uninspected_rejected_suggestions_count()
                        >= 3
                    ):
                        should_break = True
                        self.ide_server.call_tool(
                            "review/noop",
                            status="Refining scope based on rejected suggestions...",
                        )
                        self.ide_server.call_tool("/review/reset_rename_suggestions")
                        # refine intent only when are there are more than threshold number of rejections.
                        _new_scope = RefineIntent(
                            source_code=self.ide_server.call_tool_get(
                                "get_source_code"
                            ),
                            original_scope=self.new_intent,  # build on the new intent if needed.
                            model=self.model,
                            accepted_renames=self.orm_memory.get_all_successful_patterns(),
                            rejected_renames=self.orm_memory.get_all_rejected_patterns(),
                        ).get_new_scope()
                        reviewed_scope = self.critique_component.review_scope(
                            _new_scope
                        )
                        self.orm_memory.add_rename_scope(reviewed_scope)
                        self.orm_memory.set_all_inspected()

                # Categorize suggestion based on validation result
                if critique_result.is_valid:
                    valid_suggestions.append(suggestion)
                    print(
                        f"[CRITIQUE DEBUG] PASSED: {suggestion.old_name} → {suggestion.new_name}"
                    )
                else:
                    invalid_suggestions.append(suggestion)
                    print(
                        f"[CRITIQUE DEBUG] FAILED: {suggestion.old_name} → {suggestion.new_name}"
                    )

                if should_break:
                    break

            self.ide_server.call_tool(
                "/review/reset_rename_suggestions"
            )  # reset the IDE view panel,
            # after all suggestions have been dislayed and reviewed.

            # Create validated renames result
            validated_result = ValidatedRenames(
                valid_suggestions=valid_suggestions,
                invalid_suggestions=invalid_suggestions,
                critique_feedback=f"Validated {len(valid_suggestions)} valid and {len(invalid_suggestions)} invalid suggestions",
            )

            # In case there are no valid suggestions,
            #   capture errors and pass it back to the LLM
            # todo: move this code to the orm_memory file.
            if len(invalid_suggestions) > 0 and len(valid_suggestions) == 0:
                # All suggestions failed critique
                print(
                    f"[CRITIQUE DEBUG] All {len(invalid_suggestions)} suggestions failed critique"
                )

                failed_names = [
                    f"{s.old_name} → {s.new_name}" for s in invalid_suggestions
                ]

                # Enhanced feedback with memory context
                feedback_parts = [
                    f"CRITIQUE: All {len(invalid_suggestions)} rename suggestions were invalid: {', '.join(failed_names)}.",
                    "Do NOT suggest these same renames again. Try different rename suggestions by analyzing the code more carefully.",
                ]

                # Add memory-based guidance if available (only if memory enabled)
                if (
                    self.enable_memory
                    and hasattr(self, "benchmark_id")
                    and self.benchmark_id
                ):
                    try:
                        memory_stats = self.orm_memory.get_memory_stats(
                            self.benchmark_id, self.rel_file_path
                        )
                        if memory_stats["total_attempts"] > 0:
                            feedback_parts.append(
                                f"MEMORY STATS: {memory_stats['total_attempts']} total attempts, "
                                f"{memory_stats['success_rate']:.1f}% success rate in this benchmark."
                            )

                        # Get successful patterns if available
                        successful_patterns = (
                            self.orm_memory.get_most_successful_patterns(limit=3)
                        )
                        if successful_patterns:
                            pattern_examples = [
                                f"'{p['old_name']}' → '{p['new_name']}'"
                                for p in successful_patterns[:2]
                            ]
                            feedback_parts.append(
                                f"Try patterns like: {', '.join(pattern_examples)}"
                            )

                    except Exception as e:
                        print(f"[MEMORY DEBUG] Error getting memory stats: {e}")
                elif not self.enable_memory:
                    print(
                        f"[MEMORY DEBUG] Memory disabled - no memory-based guidance available"
                    )

                feedback = " ".join(feedback_parts)
                return {"messages": state["messages"] + [HumanMessage(feedback)]}

            # Store validated result for tool call generation
            result_message = AIMessage(
                content=f"Critique completed: {len(valid_suggestions)} valid suggestions, {len(invalid_suggestions)} invalid suggestions",
                additional_kwargs={"validated_renames": validated_result.dict()},
            )

            # Log memory statistics if available (always show since we always store for evaluation)
            if hasattr(self, "benchmark_id") and self.benchmark_id:
                try:
                    stats = self.orm_memory.get_memory_stats(
                        self.benchmark_id, self.rel_file_path
                    )
                    if self.enable_memory:
                        print(
                            f"[MEMORY DEBUG] Current stats for benchmark {self.benchmark_id}: {stats} (feedback enabled)"
                        )
                    else:
                        print(
                            f"[MEMORY DEBUG] Current stats for benchmark {self.benchmark_id}: {stats} (feedback disabled, storage only)"
                        )
                except Exception as e:
                    print(f"[MEMORY DEBUG] Error getting stats: {e}")

            return {"messages": state["messages"] + [result_message]}

        def generate_tool_calls(state: MessagesState):
            """Generate tool calls from validated JSON suggestions."""
            last_message = state["messages"][-1]

            # Extract validated renames from message
            if (
                not hasattr(last_message, "additional_kwargs")
                or "validated_renames" not in last_message.additional_kwargs
            ):
                print(f"[TOOL GEN DEBUG] No validated renames found")
                return {"messages": [AIMessage("No validated suggestions to execute")]}

            validated_data = last_message.additional_kwargs["validated_renames"]
            validated_renames = ValidatedRenames(**validated_data)

            print(
                f"[TOOL GEN DEBUG] Generating tool calls for {len(validated_renames.valid_suggestions)} valid suggestions"
            )

            if len(validated_renames.valid_suggestions) == 0:
                return {"messages": [AIMessage("No valid suggestions to execute")]}

            # Create tool calls from valid suggestions
            tool_calls = []
            for i, suggestion in enumerate(validated_renames.valid_suggestions):
                tool_call = {
                    "name": "rename",
                    "args": {
                        "old_name": suggestion.old_name,
                        "new_name": suggestion.new_name,
                        "line_num": suggestion.line_num,
                        "code_element_type": suggestion.code_element_type,
                    },
                    "id": f"call_rename_{i}_{suggestion.old_name}_{suggestion.line_num}",
                    "type": "tool_call",
                }
                if self.trigger_renames:
                    tool_calls.append(tool_call)
                    print(
                        f"[TOOL GEN DEBUG] Generated tool call: {suggestion.old_name} → {suggestion.new_name}"
                    )
                else:
                    print("Skipping tool call, because running agent with real human.")

            # Create AIMessage with tool calls
            tool_call_message = AIMessage(
                content=f"Executing {len(tool_calls)} validated rename operations",
                tool_calls=tool_calls,
            )

            # Update tool call map for success tracking
            self.update_tool_call_map(tool_call_message)

            # Set active tool call for retry logic
            self._active_tool_call = tool_calls

            print(f"[TOOL GEN DEBUG] Created message with {len(tool_calls)} tool calls")
            return {"messages": state["messages"] + [tool_call_message]}

        def critique_passed(state: MessagesState) -> bool:
            """Check if critique passed - now always proceeds since we filter invalid tool calls."""
            # Since we now filter out invalid tool calls instead of retrying,
            # we always proceed to tools (either with filtered tool calls or no tool calls)
            return True

        def has_tool_call(state: MessagesState) -> bool:
            if len(state["messages"][-1].tool_calls) > 0:
                self.update_tool_call_map(state["messages"][-1])
                if "replace_file_contents" in str(state["messages"][-1].tool_calls[0]):
                    self._active_tool_call = [
                        f"Replaced file contents of {self.rel_file_path}."
                    ]
                else:
                    self._active_tool_call = state["messages"][-1].tool_calls
                return True
            return False

        def debug_tool_node(state: MessagesState):
            """Debug wrapper for ToolNode to see what it receives."""
            last_message = state["messages"][-1]
            print(f"[TOOL DEBUG] ToolNode received message type: {type(last_message)}")
            print(
                f"[TOOL DEBUG] Message has tool_calls: {hasattr(last_message, 'tool_calls')}"
            )
            if hasattr(last_message, "tool_calls"):
                print(
                    f"[TOOL DEBUG] Number of tool calls to execute: {len(last_message.tool_calls)}"
                )
                for i, tc in enumerate(last_message.tool_calls):
                    print(f"[TOOL DEBUG] Tool call {i}: {tc}")
            else:
                print(f"[TOOL DEBUG] WARNING: No tool_calls attribute found!")

            # Execute the actual ToolNode
            tool_node = ToolNode(self.tools)
            result = tool_node.invoke(state)

            print(f"[TOOL DEBUG] ToolNode returned: {len(result['messages'])} messages")
            for i, msg in enumerate(result["messages"]):
                print(
                    f"[TOOL DEBUG] Result message {i}: {type(msg)} - {msg.content[:100]}..."
                )

            return result

        def json_response_valid(state: MessagesState) -> bool:
            """Check if we got a valid JSON response from LLM."""
            last_message = state["messages"][-1]
            return (
                hasattr(last_message, "additional_kwargs")
                and "rename_analysis" in last_message.additional_kwargs
            )

        def llm_gave_up(state: MessagesState) -> bool:
            """Check if LLM returned a stopping message due to max retries."""
            last_message = state["messages"][-1]
            return (
                isinstance(last_message, AIMessage)
                and "Stopping LLM calls after" in last_message.content
            )

        def has_valid_suggestions(state: MessagesState) -> bool:
            """Check if we have valid suggestions after critique."""
            last_message = state["messages"][-1]
            if (
                hasattr(last_message, "additional_kwargs")
                and "validated_renames" in last_message.additional_kwargs
            ):
                validated_data = last_message.additional_kwargs["validated_renames"]
                validated_renames = ValidatedRenames(**validated_data)
                return len(validated_renames.valid_suggestions) > 0
            return False

        def completion_message_handler(state: MessagesState):
            """Handle completion message from LLM."""
            print(
                "[COMPLETION MESSAGE] LLM detected refactoring completion - creating success message"
            )
            completion_msg = HumanMessage("REFACTORING_COMPLETED_BY_LLM")
            return {"messages": state["messages"] + [completion_msg]}

        llm_tool_workflow = StateGraph(MessagesState)
        llm_tool_workflow.add_node("call_llm", call_llm)
        llm_tool_workflow.add_node("parse_json_response", parse_json_response)
        llm_tool_workflow.add_node(
            "critique_json_suggestions", critique_json_suggestions
        )
        llm_tool_workflow.add_node("generate_tool_calls", generate_tool_calls)
        llm_tool_workflow.add_node("tools", debug_tool_node)
        llm_tool_workflow.add_node("completion_message", completion_message_handler)
        llm_tool_workflow.add_edge(START, "call_llm")

        def parse_and_decide(state: MessagesState) -> str:
            """Parse JSON and decide next step in one unified function."""

            if llm_gave_up(state):
                print(f"[FLOW DEBUG] LLM gave up - exiting workflow")
                return "END"

            if not json_response_valid(state):
                print(f"[FLOW DEBUG] JSON parsing failed - retrying LLM")
                return "call_llm"

            print(f"[FLOW DEBUG] JSON parsing successful - proceeding to critique")
            return "critique_json_suggestions"

        def critique_and_decide(state: MessagesState) -> str:
            """After critique, decide whether to execute tools or retry."""

            # Check for valid suggestions to execute
            if has_valid_suggestions(state):
                print(f"[FLOW DEBUG] Found valid suggestions - generating tool calls")
                return "generate_tool_calls"

            # No valid suggestions - retry LLM
            print(f"[FLOW DEBUG] No valid suggestions found - retrying LLM")
            return "call_llm"

        # Clean workflow: call_llm → parse_and_decide → critique_and_decide → tools
        llm_tool_workflow.add_edge("call_llm", "parse_json_response")
        llm_tool_workflow.add_conditional_edges(
            "parse_json_response",
            parse_and_decide,
            {
                "critique_json_suggestions": "critique_json_suggestions",
                "completion_message": "completion_message",
                "call_llm": "call_llm",
                "END": END,
            },
        )
        llm_tool_workflow.add_conditional_edges(
            "critique_json_suggestions",
            critique_and_decide,
            {"generate_tool_calls": "generate_tool_calls", "call_llm": "call_llm"},
        )
        llm_tool_workflow.add_edge("generate_tool_calls", "tools")
        llm_tool_workflow.add_edge("completion_message", END)
        llm_tool = llm_tool_workflow.compile()

        workflow = StateGraph(MessagesState)
        workflow.add_node("open_file", open_file)
        workflow.add_node("check_completion", check_completion)
        workflow.add_node("success_handler", success_handler)
        workflow.add_node("failure_handler", failure_handler)
        workflow.add_node("llm_tool", llm_tool)
        llm_tool.__name__ = "llm_tool"

        workflow.add_edge(START, "open_file")
        workflow.add_conditional_edges(
            "open_file", successful_file_open, {True: "llm_tool", False: END}
        )
        workflow.add_conditional_edges(
            "llm_tool",
            retry_condition,
            {
                "check_completion": "check_completion",
                "failure_handler": "failure_handler",
                "success_handler": "success_handler",
                "llm_tool": "llm_tool",
            },
        )
        workflow.add_conditional_edges(
            "check_completion",
            should_continue_refactoring,
            {True: "llm_tool", False: "success_handler"},
        )
        workflow.add_edge("success_handler", END)
        workflow.add_edge("failure_handler", END)

        compiled_flow = workflow.compile()

        return compiled_flow

    def get_performed_refactorings(self, messages: MessagesState):
        self._performed_refactorings = list(self._tool_call_map.values())
        return self._performed_refactorings

    def update_tool_call_map(self, message: BaseMessage):
        if hasattr(message, "tool_calls") and message.tool_calls:
            for tool_call in message.tool_calls:
                self._tool_call_map[tool_call["id"]]["tool_call"] = tool_call

        if isinstance(message, ToolMessage):
            self._tool_call_map[message.tool_call_id]["response"] = message.content

    def get_successfull_refactorings(self) -> str:
        success_refactorings = "\n".join(
            [
                self.get_tool_call_str(v["tool_call"])
                for k, v in self._tool_call_map.items()
                if "success" in v["response"].lower()
            ]
        )
        return success_refactorings

    def validate_rename_objects(
        self, rename_suggestions: List[RenameSuggestion]
    ) -> List[RenameSuggestionValidated]:
        valid_objs = []
        seen_suggestions = []
        for rename_suggestion in rename_suggestions:
            validated_json = self.ide_server.call_tool(
                "form-rename-object",
                old_name=rename_suggestion.old_name,
                new_name=rename_suggestion.new_name,
                line_num=rename_suggestion.line_num,
                code_element_type=rename_suggestion.code_element_type,
            )
            try:
                validated_json = json.loads(validated_json)
            except JSONDecodeError:
                validated_json = None
            if validated_json:
                validated_obj = RenameSuggestionValidated(**validated_json)
                validated_obj.reason = rename_suggestion.reason
                if validated_obj.line_num != rename_suggestion.line_num:
                    validated_obj.llm_start_line_num = rename_suggestion.line_num

                if (
                    validated_obj.resolved_start_line or validated_obj.line_num,
                    validated_obj.old_name,
                    validated_obj.new_name,
                ) not in seen_suggestions:
                    seen_suggestions.append(
                        (
                            validated_obj.resolved_start_line or validated_obj.line_num,
                            validated_obj.old_name,
                            validated_obj.new_name,
                        )
                    )
                    valid_objs.append(validated_obj)
                else:
                    print(f"Skipping duplicate rename suggestion -> {validated_obj}")
        return valid_objs

    def generate_system_prompt(self) -> SystemMessage:
        return SystemMessage(
            f"You are an expert developer who executes rename refactorings.\n"
            f"Please do the following: {self.new_intent} \n"
            f"IMPORTANT: Analyze the code and identify all occurrences of matching identifiers (methods, variables, fields, parameters, classes). that need to be renamed. "
            f"You will be asked to provide your analysis as a JSON response containing all rename suggestions."
        )

    def store_critque_results(
        self,
        critique_result: CritiqueResult,
        previously_invalid: bool,
        rename_analysis: RenameAnalysisWithCommentStartLine,
        suggestion: RenameSuggestionValidated,
    ):
        # Always store suggestion in memory for evaluation purposes (regardless of enable_memory flag)
        if hasattr(self, "benchmark_id") and self.benchmark_id:
            try:
                # Prepare context data for memory storage
                context_data = {
                    "analysis": rename_analysis.analysis,
                    "suggestion_reason": (
                        suggestion.reason
                        if hasattr(suggestion, "reason") and suggestion.reason
                        else ""
                    ),
                    "oracle_match": (
                        critique_result.oracle_match.model_dump()
                        if hasattr(critique_result, "oracle_match")
                        and critique_result.oracle_match
                        else None
                    ),
                    "previously_invalid": previously_invalid,
                    "retry_iteration": self._retry_iteration,
                    "memory_feedback_enabled": self.enable_memory,  # Track whether feedback was used
                }

                # Get current LLM iteration number
                current_llm_iteration = (
                    self.orm_memory.get_current_llm_iteration()
                    if self.orm_memory
                    else 0
                )

                # Add suggestion to memory
                memory_entry = self.orm_memory.add_suggestion(
                    benchmark_id=self.benchmark_id,
                    file_path=suggestion.resolved_file_path or self.rel_file_path,
                    old_name=suggestion.old_name,
                    new_name=suggestion.new_name,
                    line_num=suggestion.resolved_start_line
                    or suggestion.start_line_comments
                    or suggestion.line_num,
                    code_element_type=suggestion.code_element_type.value,
                    is_valid=critique_result.is_valid,
                    feedback=critique_result.feedback,
                    critique_reason=(
                        critique_result.reason
                        if hasattr(critique_result, "reason")
                        else ""
                    ),
                    confidence_score=(
                        critique_result.confidence_score
                        if hasattr(critique_result, "confidence_score")
                        else None
                    ),
                    agent_iteration=self._retry_iteration,
                    llm_iteration=current_llm_iteration,
                    context_data=context_data,
                    snippet=self.get_code_snippet(suggestion),
                )

                if self.enable_memory:
                    print(
                        f"[MEMORY DEBUG] Stored suggestion in memory successfully (with feedback enabled)"
                    )
                else:
                    print(
                        f"[MEMORY DEBUG] Stored suggestion in memory for evaluation (feedback disabled)"
                    )

            except Exception as e:
                print(f"[MEMORY DEBUG] Error storing suggestion in memory: {e}")
                # Continue processing even if memory storage fails

    def get_code_snippet(self, suggestion: RenameSuggestionValidated) -> str:
        return self.ide_server.call_tool(
            "get_source_code_snippet",
            name=suggestion.old_name,
            line_num=suggestion.resolved_start_line
            or suggestion.start_line_comments
            or suggestion.line_num,
            code_element_type=suggestion.code_element_type.value,
            file_path=suggestion.resolved_file_path or self.rel_file_path,
        )

    def show_auto_suggestions_to_ui(self):
        """Show auto-suggestions to UI while LLM is processing.

        This runs in a separate thread to provide immediate feedback to the user.
        """
        try:
            print("[AUTO-SUGGEST] Starting to fetch and display auto-suggestions")

            # query history to get rename patterns
            success_patterns = self.orm_memory.get_all_successful_patterns()
            print(
                f"[AUTO-SUGGEST] Found {len(success_patterns)} successful patterns from history"
            )
            pattern_old_name = self.new_intent.old_name
            if pattern_old_name is not None:
                ident_count_str = self.ide_server.call_tool(
                    "count_identifiers_keyword", keyword=self.new_intent.old_name
                )
            else:
                ident_count_str = self.ide_server.call_tool("count_identifiers")
            try:
                total_identifiers = int(ident_count_str)
                self.ide_server.call_tool(
                    "review/noop",
                    status=f"Inspecting: {self.rel_file_path.split('/')[-1]}. Analyzing {total_identifiers} identifiers in file.",
                )
            except Exception as e:
                total_identifiers = None

            for i, pattern in enumerate(success_patterns):
                # attempt to create objects for all previously successful patterns
                rename_json = self.ide_server.call_tool(
                    "form-rename-object-all",
                    old_name=pattern.old_name,
                    new_name=pattern.new_name,
                )

                try:
                    rename_objs = json.loads(rename_json)
                    total_identifiers_str = (
                        len(rename_objs)
                        if total_identifiers is None
                        else total_identifiers
                    )
                    self.ide_server.call_tool(
                        "review/noop",
                        status=f"Inspecting: {self.rel_file_path.split('/')[-1]}. Analyzing {total_identifiers_str} identifiers in file.",
                    )
                    sleep(2)

                    auto_suggestion_str = "\n"
                    for i, obj in enumerate(rename_objs):
                        suggestion = RenameSuggestion(**obj)
                        # Send each suggestion to UI immediately
                        auto_suggestion_str += f"Analyzing identifier: {suggestion.code_element_type.value.capitalize()} {suggestion.old_name} at line {suggestion.line_num} \n"
                        self.ide_server.call_tool(
                            "review/noop",
                            status=f"Inspecting: {self.rel_file_path.split('/')[-1]}. Analyzing {i+1} locations. \n{auto_suggestion_str}",
                        )
                        sleep(2)
                        print(
                            f"[AUTO-SUGGEST] Sent to UI: {suggestion.old_name} → {suggestion.new_name} Code Element: {suggestion.code_element_type.value.capitalize()} at line {suggestion.line_num}"
                        )
                except JSONDecodeError:
                    print(f"[AUTO-SUGGEST] Pattern {pattern} not found in file")
                except Exception as e:
                    print(f"[AUTO-SUGGEST] Error processing pattern {pattern}: {e}")

            print(f"[AUTO-SUGGEST] Completed displaying suggestions")

        except Exception as e:
            print(f"[AUTO-SUGGEST] Error in show_auto_suggestions_to_ui: {e}")

    def get_auto_suggestions(self) -> List[RenameSuggestion]:
        # query history to get rename patterns
        if self.new_intent.condition is not None:
            return []
        history_based_patterns = []
        success_patterns = self.orm_memory.get_all_successful_patterns()
        for pattern in success_patterns:
            # attempt to create objects for all previously successful patterns
            rename_json = self.ide_server.call_tool(
                "form-rename-object-all",
                old_name=pattern.old_name,
                new_name=pattern.new_name,
            )
            try:
                rename_objs = json.loads(rename_json)
                for obj in rename_objs:
                    history_based_patterns.append(RenameSuggestion(**obj))
            except JSONDecodeError:
                print(f"pattern {pattern} was not found in file")

        if self.new_intent.condition is not None:
            return self.filter_auto_suggestions(history_based_patterns)
        return history_based_patterns

    def get_examples_message(self) -> Optional[HumanMessage]:
        """Create few shot examples based on memory content"""
        message = ["Here are a few examples:\n"]

        success_renames = self.orm_memory.get_all_successful_patterns()
        failed_renames = self.orm_memory.get_all_rejected_patterns()

        if len(success_renames) + len(failed_renames) == 0:
            return None

        for rename in success_renames:
            message.append(f"=== Code ===")
            message.append("...")
            message.append(rename.snippet)  # add snippet
            message.append("...")
            message.append(f"=== End of Code ===")

            message.append("")
            message.append("Example response:")
            expected_response = RenameAnalysis(
                analysis=f"REFACTORING_NEEDED: Rename {rename.old_name} -> {rename.new_name}, and also Rename ...",
                rename_suggestions=[
                    RenameSuggestion(
                        old_name=rename.old_name,
                        new_name=rename.new_name,
                        line_num=rename.line_num,
                        code_element_type=CodeElementType(rename.code_element_type),
                        reason="This suggestion fits the scope.",
                    )
                ],
            )
            example_str = json.dumps(expected_response.dict(), indent=4)
            example_str = example_str.replace("}\n    ]\n}", "},\n    ...\n    ]\n}")
            message.append(example_str)
            message.append("")

        for rename in failed_renames:
            message.append(f"=== Code ===")
            message.append("...")
            message.append(rename.snippet)  # add snippet
            message.append("...")
            message.append(f"=== End of Code ===")

            message.append("")
            message.append("Example response:")
            expected_response = RenameAnalysis(
                analysis=f"REFACTORING_COMPLETE. Reason: "
                f"Renaming {rename.old_name} -> {rename.new_name} does not fit the renaming scope.",
                rename_suggestions=[],
            )
            message.append(json.dumps(expected_response.dict(), indent=4))
            message.append("")

        return HumanMessage("\n".join(message))

    def filter_auto_suggestions(
        self, history_based_patterns: List[RenameSuggestion]
    ) -> List[RenameSuggestion]:
        filtered_patterns = []
        current_file_content = self.ide_server.call_tool_get("get_source_code")
        numbered_file_content = code_utils.add_line_numbers(current_file_content)
        for suggestion in history_based_patterns:
            response = prompt_cache.prompt(
                self.model,
                [
                    self.generate_system_prompt(),
                    HumanMessage(numbered_file_content),
                    HumanMessage(
                        f"Answer YES or NO: Should {suggestion.old_name} on line {suggestion.line_num} be renamed?"
                    ),
                ],
            )
            if "YES" in response.content:
                filtered_patterns.append(suggestion)
        return filtered_patterns

    def analyse_chunk_deco(self):
        all_chunks = []

        def analyse_chunk(chunk):
            # Kill the auto-suggestion thread when we start receiving LLM responses
            if len(all_chunks) == 0 and hasattr(self, "_auto_suggest_executor"):
                try:
                    self._auto_suggest_executor.terminate()
                    self._auto_suggest_executor.join(1)
                    print(
                        "[STREAMING] Stopped auto-suggestion thread, LLM is responding"
                    )
                except Exception as e:
                    print(f"[STREAMING] Error stopping auto-suggest executor: {e}")

            # Extract content from AIMessageChunk
            chunk_content = chunk.content if hasattr(chunk, "content") else str(chunk)
            all_chunks.append(chunk_content)
            partial_response = "".join(all_chunks)

            # Try to parse partial JSON and extract suggestions
            try:
                suggestions = self._extract_suggestions_from_partial(partial_response)
                suggestion_str = ""
                # Send new suggestions to UI
                for suggestion in suggestions:
                    suggestion_key = (
                        suggestion.get("old_name"),
                        suggestion.get("new_name"),
                        suggestion.get("line_num"),
                    )

                    suggestion_str += f"{suggestion['old_name']} → {suggestion['new_name']} at line {suggestion['line_num']} \n"

                self.ide_server.call_tool(
                    "review/noop",
                    status=f"Inspecting: {self.rel_file_path.split('/')[-1]}. Found {len(suggestions)} suggestions: \n{suggestion_str}",
                )

            except Exception:
                # Parsing errors are expected for incomplete JSON, just continue
                pass

        return analyse_chunk

    def _extract_suggestions_from_partial(self, partial_response: str) -> List[Dict]:
        suggestions = []

        # Look for individual suggestion objects in the partial response
        suggestion_pattern = re.compile(
            r'\{\s*"old_name"\s*:\s*"([^"]+)"\s*,\s*'
            r'"new_name"\s*:\s*"([^"]+)"\s*,\s*'
            r'"line_num"\s*:\s*(\d+)\s*,\s*'
            r'"code_element_type"\s*:\s*"([^"]+)"',
            re.DOTALL,
        )

        for match in suggestion_pattern.finditer(partial_response):
            suggestion = {
                "old_name": match.group(1),
                "new_name": match.group(2),
                "line_num": int(match.group(3)),
                "code_element_type": match.group(4),
            }
            suggestions.append(suggestion)
            print(
                f"[PARTIAL PARSE] Found suggestion: {suggestion['old_name']} → {suggestion['new_name']} at line {suggestion['line_num']} ({suggestion['code_element_type']})"
            )

        if suggestions:
            print(
                f"[PARTIAL PARSE] Total {len(suggestions)} suggestions extracted from partial response"
            )

        return suggestions
