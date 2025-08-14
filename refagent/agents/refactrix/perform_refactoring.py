from collections import defaultdict

from pydantic.v1 import BaseModel, Field, PrivateAttr
from typing import List, Callable, Dict, Optional, Any
from langchain_core.output_parsers import PydanticOutputParser
import json
from langchain_core.language_models import BaseChatModel
from langgraph.graph.graph import CompiledGraph
from langgraph.graph import END, START, StateGraph, MessagesState
from langgraph.prebuilt import ToolNode
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, BaseMessage, ToolCall
from pathlib import Path

import refagent.agents.refactrix.supported_refactorings as sup_ref
import refagent.utils.intellij_server as ij
from refagent.agents.refactrix.rename_suggestions import RenameAnalysis, RenameSuggestion, ValidatedRenames


class PerformRefactoring(BaseModel):
    tools: List = Field(description="refactoring tools that are available") # TODO: Type annotate with tool type.
    retry_count: int = Field(description="how many times to allow the LLM to retry", default=2)
    model: BaseChatModel = Field(description="Langchain Chat model")
    reason: str = Field(description="Reason to perform the refactoring. Usually provided by the LM.")
    refactoring_type: sup_ref.SupportedRefactorings = Field(description="The type of refactoring to be performed.")
    rel_file_path: str = Field(description="relative file path from repo root. file to be edited.")
    ide_server: ij.IntellijServer = Field(description="ide server object. Used to open files.")
    refactoring_success: bool = Field(description="whether the refactoring was successful or not.", default=False)
    critique_component: Optional[Any] = Field(description="Critique component for validating suggestions", default=None)
    _file_open_status: bool = PrivateAttr(default=False)
    _active_tool_call: List = PrivateAttr(default="")
    _retry_iteration: int = PrivateAttr(default=1)
    _performed_refactorings: List = PrivateAttr(default=[])
    _tool_call_map: Dict = PrivateAttr(default=defaultdict(dict))
    _critique_retry_count: int = PrivateAttr(default=0)

    def get_tool_call_str(self, tool_call: Optional[ToolCall]=None) -> str:
        if tool_call is None:
            if not self._active_tool_call:
                return "no tool calls"
            tool_call = self._active_tool_call[0]
        name = tool_call['name']
        args = ", ".join([f"{k}={v}" for k, v in tool_call['args'].items()])
        tool_call_str = f"{name}({args})"
        return tool_call_str

    def compile(self) -> CompiledGraph:

        def open_file(state: MessagesState):
            response = self.ide_server.try_open_file(Path(self.rel_file_path))
            if response.startswith('tool call failed '):
                create_file = self.model.invoke(
                    state['messages'] +
                    [HumanMessage(f"{response}. Would you like to create this file? Answer YES/NO.")])

                if 'YES' in create_file.content:
                    create_response = self.ide_server.create_file(Path(self.rel_file_path))
                    if create_response == 'success':
                        self._file_open_status = True
                        open_response = self.ide_server.open_file(Path(self.rel_file_path))
                        return {"messages": [HumanMessage(f"Created and opened file successfully. "
                                                          f"You are now editing {self.rel_file_path}")]}

                return {"messages": [HumanMessage(response)]}
            self._file_open_status = True
            return {"messages": [HumanMessage(f"Opened file successfully. "
                                              f"You are now editing {self.rel_file_path}")]}

        def successful_file_open(state: MessagesState):
            return self._file_open_status

        def call_llm(state: MessagesState):
            # Check if we've exceeded max retries (default is 3, but using retry_count field)
            max_retries = max(3, self.retry_count + 1)  # Ensure at least 3 retries, use field if higher
            if self._retry_iteration > max_retries:
                print(f"[LLM DEBUG] Max retries ({max_retries}) exceeded, stopping LLM calls")
                return {"messages": [AIMessage(f"Stopping LLM calls after {max_retries} attempts. Unable to generate valid rename suggestions.")]}
            
            print(f"[LLM DEBUG] LLM call attempt {self._retry_iteration}/{max_retries}")
            
            if self._retry_iteration > 1:
                # Add retry warning for JSON-based approach
                state['messages'][-1].content += (f"Your previous rename suggestions were invalid. "
                                                  f"DO NOT suggest the same renames again. Try different ones.")
            
            # Create output parser for structured JSON response
            parser = PydanticOutputParser(pydantic_object=RenameAnalysis)
            
            # Add JSON format instructions to the last message
            format_instructions = (
                "\n\nIMPORTANT: Respond with a JSON object containing your analysis and rename suggestions. "
                f"Use this exact format:\n{parser.get_format_instructions()}"
            )
            
            # Modify the last message to include format instructions
            messages = state['messages'].copy()
            if messages:
                last_msg = messages[-1]
                if hasattr(last_msg, 'content'):
                    last_msg.content += format_instructions
            
            # Use model without tools for JSON output
            response = self.model.invoke(messages)
            self._retry_iteration += 1
            return {"messages": [response]}

        def parse_json_response(state: MessagesState):
            """Parse and validate JSON response from LLM."""
            last_message = state['messages'][-1]
            
            print(f"[JSON DEBUG] Parsing LLM response: {last_message.content[:200]}...")
            
            # Check if LLM gave up BEFORE trying to parse as JSON
            if llm_gave_up(state):
                print(f"[JSON DEBUG] Detected LLM gave up message - not attempting JSON parsing")
                return {"messages": state['messages']}  # Pass through the stopping message
            
            try:
                # Try to parse the JSON response
                parser = PydanticOutputParser(pydantic_object=RenameAnalysis)
                rename_analysis = parser.parse(last_message.content)
                
                print(f"[JSON DEBUG] Successfully parsed {len(rename_analysis.rename_suggestions)} rename suggestions")
                for i, suggestion in enumerate(rename_analysis.rename_suggestions):
                    print(f"[JSON DEBUG] Suggestion {i}: {suggestion.old_name} → {suggestion.new_name} at line {suggestion.line_num}")
                
                # Store the parsed analysis in the message for the next step
                parsed_message = AIMessage(
                    content=f"Parsed rename analysis: {rename_analysis.analysis}",
                    additional_kwargs={"rename_analysis": rename_analysis.dict()}
                )
                
                return {"messages": state['messages'] + [parsed_message]}
                
            except Exception as e:
                print(f"[JSON DEBUG] Failed to parse JSON response: {e}")
                error_message = HumanMessage(
                    f"Failed to parse your JSON response. Error: {str(e)}. "
                    f"Please provide a valid JSON response following the exact format specified."
                )
                return {"messages": state['messages'] + [error_message]}
        

        def success_handler(state: MessagesState):
            print("The following refactorings have been performed successfully-> "
                  f"{self.get_successfull_refactorings()}")
            self.refactoring_success = True
            success_msg = state['messages'][-1].content

            tool_call_status = str(self._active_tool_call)
            if 'replace_file_contents' in str(self._active_tool_call):
                tool_call_status = "replaced file contents."
            final_message = ("Successfully performed the refactoring. "
                             f"{tool_call_status}")
            if success_msg != 'success':
                final_message += success_msg
            return {'messages': [HumanMessage(final_message)]}

        def failure_handler(state: MessagesState):
            print("Failed to perform the refactoring.")
            
            # Check if LLM gave up before generating tool calls
            if llm_gave_up(state):
                return {"messages": [HumanMessage("Cannot perform this refactoring. "
                                                  "LLM was unable to generate valid rename suggestions after multiple attempts. "
                                                  "The code may not contain the expected patterns for this refactoring.")]}
            
            tool_call_str = self.get_tool_call_str()
            
            # Find the actual tool failure message from ToolMessages
            tool_failure_reason = "Unknown tool failure"
            for message in reversed(state['messages']):  # Search backwards for most recent ToolMessage
                if isinstance(message, ToolMessage) and 'success' not in message.content.lower():
                    tool_failure_reason = message.content
                    break
            
            return {"messages": [HumanMessage("Cannot perform this refactoring. "
                                              f"{tool_call_str} failed. "
                                              f"Reason: {tool_failure_reason}. "
                                              f"CALL the TOOL differently, next time.")]}

        def retry_condition(state: MessagesState) -> str:
            responded_tool_calls: List[ToolMessage] = []
            for message in state['messages']:
                if (isinstance(message, ToolMessage) and
                        self._tool_call_map[message.tool_call_id].get('response') is None):
                    responded_tool_calls.append(message)
                    self.update_tool_call_map(message)

            # last_message = state['messages'][-1].content
            # False -> retry
            tool_call_success = any('success' in tool_response.content.lower()
                                    for tool_response in responded_tool_calls)  # retry in case any of the tool calls succeeded.

            if tool_call_success:
                return "success_handler"

            if self._retry_iteration > self.retry_count:
                # retried more than threshold times
                return "failure_handler"

            return "llm_tool"  # retry the tool call

        def critique_json_suggestions(state: MessagesState):
            """Critique JSON rename suggestions before creating tool calls."""
            last_message = state['messages'][-1]
            
            print(f"[CRITIQUE DEBUG] Critiquing JSON suggestions from message type: {type(last_message)}")
            
            # If no critique component, proceed without validation
            if not self.critique_component:
                return {"messages": [AIMessage("No critique component - proceeding with all suggestions")]}
            
            # Extract rename analysis from message
            if not hasattr(last_message, 'additional_kwargs') or 'rename_analysis' not in last_message.additional_kwargs:
                print(f"[CRITIQUE DEBUG] No rename analysis found in message")
                return {"messages": [HumanMessage("No rename suggestions found to critique. Please provide rename suggestions in the correct JSON format.")]}
            
            # Parse the rename analysis
            rename_analysis_data = last_message.additional_kwargs['rename_analysis']
            rename_analysis = RenameAnalysis(**rename_analysis_data)
            
            print(f"[CRITIQUE DEBUG] Found {len(rename_analysis.rename_suggestions)} suggestions to validate")
            
            # Validate each rename suggestion
            valid_suggestions = []
            invalid_suggestions = []
            
            for suggestion in rename_analysis.rename_suggestions:
                print(f"[CRITIQUE DEBUG] Validating: {suggestion.old_name} → {suggestion.new_name} at line {suggestion.line_num}")
                
                critique_result = self.critique_component.validate_rename_suggestion(
                    suggestion.old_name, 
                    suggestion.new_name,
                    suggestion.line_num, 
                    suggestion.code_element_type.value
                )

                print(f"[CRITIQUE DEBUG] Validation result: is_valid={critique_result.is_valid}, feedback='{critique_result.feedback}'")

                if critique_result.is_valid:
                    valid_suggestions.append(suggestion)
                    print(f"[CRITIQUE DEBUG] PASSED: {suggestion.old_name} → {suggestion.new_name}")
                else:
                    invalid_suggestions.append(suggestion)
                    print(f"[CRITIQUE DEBUG] FAILED: {suggestion.old_name} → {suggestion.new_name}")
            
            # Create validated renames result
            validated_result = ValidatedRenames(
                valid_suggestions=valid_suggestions,
                invalid_suggestions=invalid_suggestions,
                critique_feedback=f"Validated {len(valid_suggestions)} valid and {len(invalid_suggestions)} invalid suggestions"
            )
            
            # Handle critique results
            if len(invalid_suggestions) > 0 and len(valid_suggestions) == 0:
                # All suggestions failed critique
                print(f"[CRITIQUE DEBUG] All {len(invalid_suggestions)} suggestions failed critique")
                
                failed_names = [f"{s.old_name} → {s.new_name}" for s in invalid_suggestions]
                feedback = (
                    f"CRITIQUE: All {len(invalid_suggestions)} rename suggestions were invalid: {', '.join(failed_names)}. "
                    f"Do NOT suggest these same renames again. Try different rename suggestions by analyzing the code more carefully."
                )
                
                return {"messages": state['messages'] + [HumanMessage(feedback)]}
            
            # Store validated result for tool call generation
            result_message = AIMessage(
                content=f"Critique completed: {len(valid_suggestions)} valid suggestions, {len(invalid_suggestions)} invalid suggestions",
                additional_kwargs={"validated_renames": validated_result.dict()}
            )
            
            return {"messages": state['messages'] + [result_message]}

        def generate_tool_calls(state: MessagesState):
            """Generate tool calls from validated JSON suggestions."""
            last_message = state['messages'][-1]
            
            # Extract validated renames from message
            if not hasattr(last_message, 'additional_kwargs') or 'validated_renames' not in last_message.additional_kwargs:
                print(f"[TOOL GEN DEBUG] No validated renames found")
                return {"messages": [AIMessage("No validated suggestions to execute")]}
            
            validated_data = last_message.additional_kwargs['validated_renames']
            validated_renames = ValidatedRenames(**validated_data)
            
            print(f"[TOOL GEN DEBUG] Generating tool calls for {len(validated_renames.valid_suggestions)} valid suggestions")
            
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
                        "code_element_type": suggestion.code_element_type
                    },
                    "id": f"call_rename_{i}_{suggestion.old_name}_{suggestion.line_num}",
                    "type": "tool_call"
                }
                tool_calls.append(tool_call)
                print(f"[TOOL GEN DEBUG] Generated tool call: {suggestion.old_name} → {suggestion.new_name}")
            
            # Create AIMessage with tool calls
            tool_call_message = AIMessage(
                content=f"Executing {len(tool_calls)} validated rename operations",
                tool_calls=tool_calls
            )
            
            # Update tool call map for success tracking
            self.update_tool_call_map(tool_call_message)
            
            # Set active tool call for retry logic
            self._active_tool_call = tool_calls
            
            print(f"[TOOL GEN DEBUG] Created message with {len(tool_calls)} tool calls")
            return {"messages": state['messages'] + [tool_call_message]}

        def critique_passed(state: MessagesState) -> bool:
            """Check if critique passed - now always proceeds since we filter invalid tool calls."""
            # Since we now filter out invalid tool calls instead of retrying,
            # we always proceed to tools (either with filtered tool calls or no tool calls)
            return True

        def has_tool_call(state: MessagesState) -> bool:
            if len(state['messages'][-1].tool_calls) > 0:
                self.update_tool_call_map(state['messages'][-1])
                if 'replace_file_contents' in str(state['messages'][-1].tool_calls[0]):
                    self._active_tool_call = [f"Replaced file contents of {self.rel_file_path}."]
                else:
                    self._active_tool_call = state['messages'][-1].tool_calls
                return True
            return False


        def debug_tool_node(state: MessagesState):
            """Debug wrapper for ToolNode to see what it receives."""
            last_message = state['messages'][-1]
            print(f"[TOOL DEBUG] ToolNode received message type: {type(last_message)}")
            print(f"[TOOL DEBUG] Message has tool_calls: {hasattr(last_message, 'tool_calls')}")
            if hasattr(last_message, 'tool_calls'):
                print(f"[TOOL DEBUG] Number of tool calls to execute: {len(last_message.tool_calls)}")
                for i, tc in enumerate(last_message.tool_calls):
                    print(f"[TOOL DEBUG] Tool call {i}: {tc}")
            else:
                print(f"[TOOL DEBUG] WARNING: No tool_calls attribute found!")
            
            # Execute the actual ToolNode
            tool_node = ToolNode(self.tools)
            result = tool_node.invoke(state)
            
            print(f"[TOOL DEBUG] ToolNode returned: {len(result['messages'])} messages")
            for i, msg in enumerate(result['messages']):
                print(f"[TOOL DEBUG] Result message {i}: {type(msg)} - {msg.content[:100]}...")
            
            return result

        def json_response_valid(state: MessagesState) -> bool:
            """Check if we got a valid JSON response from LLM."""
            last_message = state['messages'][-1]
            return hasattr(last_message, 'additional_kwargs') and 'rename_analysis' in last_message.additional_kwargs

        def llm_gave_up(state: MessagesState) -> bool:
            """Check if LLM returned a stopping message due to max retries."""
            last_message = state['messages'][-1]
            return isinstance(last_message, AIMessage) and "Stopping LLM calls after" in last_message.content

        def has_valid_suggestions(state: MessagesState) -> bool:
            """Check if we have valid suggestions after critique."""
            last_message = state['messages'][-1]
            if hasattr(last_message, 'additional_kwargs') and 'validated_renames' in last_message.additional_kwargs:
                validated_data = last_message.additional_kwargs['validated_renames']
                validated_renames = ValidatedRenames(**validated_data)
                return len(validated_renames.valid_suggestions) > 0
            return False

        llm_tool_workflow = StateGraph(MessagesState)
        llm_tool_workflow.add_node("call_llm", call_llm)
        llm_tool_workflow.add_node("parse_json_response", parse_json_response)
        llm_tool_workflow.add_node("critique_json_suggestions", critique_json_suggestions)
        llm_tool_workflow.add_node("generate_tool_calls", generate_tool_calls)
        llm_tool_workflow.add_node("tools", debug_tool_node)
        llm_tool_workflow.add_edge(START, "call_llm")

        def parse_json_or_retry(state: MessagesState) -> str:
            """Decide whether to parse JSON, retry LLM, or give up."""
            if llm_gave_up(state):
                print(f"[FLOW DEBUG] LLM gave up - exiting workflow")
                return "END"  # Exit if LLM gave up
            elif json_response_valid(state):
                print(f"[FLOW DEBUG] JSON parsing successful - proceeding to critique")
                return "critique_json_suggestions"
            else:
                print(f"[FLOW DEBUG] JSON parsing failed - retrying LLM")
                return "call_llm"  # Retry

        # New workflow: call_llm → parse_json → critique → generate_tool_calls → tools
        llm_tool_workflow.add_edge("call_llm", "parse_json_response")
        llm_tool_workflow.add_conditional_edges("parse_json_response",
                                                parse_json_or_retry,
                                                {"critique_json_suggestions": "critique_json_suggestions", 
                                                 "call_llm": "call_llm",
                                                 "END": END})
        def critique_or_retry(state: MessagesState) -> str:
            """Decide whether to generate tool calls, retry LLM, or give up."""
            if llm_gave_up(state):
                print(f"[FLOW DEBUG] LLM gave up - exiting workflow")
                return "END"  # Exit if LLM gave up
            elif has_valid_suggestions(state):
                print(f"[FLOW DEBUG] Critique found valid suggestions - generating tool calls")
                return "generate_tool_calls"
            else:
                print(f"[FLOW DEBUG] Critique rejected all suggestions - retrying LLM")
                return "call_llm"  # Retry

        llm_tool_workflow.add_conditional_edges("critique_json_suggestions",
                                                critique_or_retry,
                                                {"generate_tool_calls": "generate_tool_calls",
                                                 "call_llm": "call_llm",
                                                 "END": END})
        llm_tool_workflow.add_edge("generate_tool_calls", "tools")
        llm_tool = llm_tool_workflow.compile()

        workflow = StateGraph(MessagesState)
        workflow.add_node("open_file", open_file)
        workflow.add_node("success_handler", success_handler)
        workflow.add_node("failure_handler", failure_handler)
        workflow.add_node("llm_tool", llm_tool)
        llm_tool.__name__ = "llm_tool"

        workflow.add_edge(START, "open_file")
        workflow.add_conditional_edges("open_file", successful_file_open,
                                       {True: "llm_tool", False: END})
        workflow.add_conditional_edges("llm_tool", retry_condition)
        workflow.add_edge("success_handler", END)
        workflow.add_edge("failure_handler", END)

        compiled_flow = workflow.compile()

        return compiled_flow

    def get_performed_refactorings(self, messages: MessagesState):
        self._performed_refactorings = list(self._tool_call_map.values())
        return self._performed_refactorings

    def update_tool_call_map(self, message: BaseMessage):
        if hasattr(message, 'tool_calls') and message.tool_calls:
            for tool_call in message.tool_calls:
                self._tool_call_map[tool_call['id']]["tool_call"] = tool_call

        if isinstance(message, ToolMessage):
            self._tool_call_map[message.tool_call_id]['response'] = message.content

    def get_successfull_refactorings(self) -> str:
        success_refactorings = "\n".join([self.get_tool_call_str(v['tool_call'])
                                for k,v in self._tool_call_map.items() if 'success' in v['response'].lower()])
        return success_refactorings

