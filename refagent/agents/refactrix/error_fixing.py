from pydantic.v1 import BaseModel, Field, PrivateAttr
from typing import Set, List, Dict, Any
from pathlib import Path
import refagent.utils.intellij_server as ij_server
from langchain_core.language_models import BaseChatModel
import json
import refagent.agents.refactrix.fix_planning as fix_planning
from refagent.agents.refactrix.perform_refactoring import PerformRefactoring
from refagent.agents.refactrix.tools import RefactoringToolProvider
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
import time
import traceback
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.graph.state import CompiledStateGraph


class ErrorFixing(BaseModel):
    model: BaseChatModel = Field(description="The language model to use for error fixing")
    ide_server: ij_server.IntellijServer = Field(description="The IDE server to interact with")
    files_changed: Set[Path] = Field(description="Set of files that were changed during refactoring")
    _iterations: int = PrivateAttr(default=0)
    _trajectory: List[Any] = PrivateAttr(default=[])

    def compile_and_run(self):
        """Run code inspection on each changed file and fix any issues found."""
        for file_path in self.files_changed:
            # Open the file in the IDE
            self.ide_server.open_file(file_path)
            time.sleep(5)  # Give IDE time to open the file
            
            # Run code inspection on the current file
            inspection_response = self.ide_server.call_tool('run_code_inspection')
            
            try:
                # Parse the inspection results
                issues = json.loads(inspection_response)
                if not isinstance(issues, list):
                    issues = [issues]
                
                if not issues:
                    print(f"No issues found in {file_path}")
                    continue
                
                # Get the current source code
                source_code = self.ide_server.call_tool_get("get_source_code")
                
                # Handle each issue with FixPlanningComponent
                for issue in issues:
                    print(f"\nFixing issue in {file_path}:")
                    print(f"Line {issue.get('lineNum')}: {issue.get('problem')}")
                    
                    # Create a detailed issue description
                    issue_description = issue.get('problem')
                    
                    # Create and run the fix planning component
                    fix_planner = fix_planning.FixPlanningComponent(
                        issue_description=issue_description,
                        model=self.model,
                        source_file_path=str(file_path),
                        source_code=source_code
                    )
                    
                    # Get the fix plan
                    fix_plan = fix_planner.run()
                    
                    # Execute the plan using the same pattern as refactoring_agent.py
                    final_state = self.execute_plan(fix_plan)
                    
                    # Update source code after plan execution
                    source_code = self.ide_server.call_tool_get("get_source_code")
                    
                    # Save changes
                    self.ide_server.call_tool("save_all_changes")
                    time.sleep(2)  # Give time for changes to be saved
                
                # Verify fixes
                print(f"\nVerifying fixes in {file_path}...")
                verify_response = self.ide_server.call_tool('run_code_inspection')
                verify_issues = json.loads(verify_response)
                
                if isinstance(verify_issues, list) and len(verify_issues) > 0:
                    print(f"Warning: Found {len(verify_issues)} remaining issues:")
                    for issue in verify_issues:
                        print(f"  Line {issue.get('lineNum')}: {issue.get('problem')}")
                else:
                    print("No remaining issues found")
                
            except json.JSONDecodeError:
                print(f"Failed to parse inspection results for {file_path}")
                continue
            except Exception as e:
                print(f"Error processing {file_path}: {str(e)}")
                traceback.print_exc()
                continue

    def execute_plan(self, fix_plan):
        """Execute a fix plan using the same pattern as refactoring_agent.py"""
        last_file_opened = None
        for i, step in enumerate(fix_plan.steps):
            print(f"Executing step {i + 1}/{len(fix_plan.steps)} in plan.")
            self._iterations = 0
            
            if step.file_path != last_file_opened:
                try:
                    self.try_open_file(step.file_path)
                except:
                    traceback.print_tb()
                    print("Failed to open file. Skipping this execution step")
                    continue
                last_file_opened = step.file_path
            
            graph = self.compile_graph(step)
            final_state = graph.invoke(
                {
                    "messages": [
                        SystemMessage(f"You are an expert developer who can fix errors in the given code. "
                                      f"Please do the follow: {step.refactoring_type}: {step.reason}. {step.execution_details} "
                                      f"The final code is expected to look something like this: {step.final_code}"
                                      f"ONLY make TOOL CALLS to perform actions."),
                    ]
                },
                config={"configurable": {"thread_id": 42}}
            )
            self._trajectory += final_state['messages']
            print(f"Result of executing step {i}: ", final_state["messages"][-1].content)
        return final_state

    def try_open_file(self, rel_file_path: str):
        """Try to open a file, creating it if it doesn't exist"""
        response = self.ide_server.try_open_file(Path(rel_file_path))
        if response.startswith('tool call failed '):
            create_response = self.ide_server.create_file(Path(rel_file_path))
            if create_response == 'success':
                open_response = self.ide_server.open_file(Path(rel_file_path))
            else:
                raise Exception("Failed to open file and did not create one either.")
        time.sleep(5)  # Give IDE time to open the file

    def compile_graph(self, plan_step) -> CompiledStateGraph:
        """Compile the graph for executing a single step"""
        def perform_fixing(state: MessagesState):
            """Perform the refactoring step"""
            # Get the appropriate tools for this refactoring type
            tool_provider = RefactoringToolProvider(ide_server=self.ide_server)
            tools_dict = tool_provider.get()
            tools = list(tools_dict.values())

            # Create and execute the refactoring
            refactoring = PerformRefactoring(
                tools=tools,
                model=self.model,
                reason=plan_step.reason,
                refactoring_type=plan_step.refactoring_type,
                rel_file_path=plan_step.file_path,
                ide_server=self.ide_server
            )

            # Compile and run the refactoring
            refactoring_graph = refactoring.compile()
            observation = refactoring_graph.invoke({"messages": state["messages"]})
            last_message = observation['messages'][-1]
            messages = state["messages"]
            messages += [last_message]

            return {"messages": messages}

        def finished_fixing(state: MessagesState):
            """Check if refactoring is complete"""
            if self._iterations >= 5:
                return {'messages': [AIMessage('finished because iteration limit reached. DONE')]}

            if self.ide_server.call_tool_get("get_source_code") == '':
                return {'messages': [AIMessage('incomplete because the file is empty. INCOMPLETE')]}

            response = self.model.invoke(state['messages'] +
                         [HumanMessage('Please reflect whether the original ask has been completed successfully'
                                       f'Here was the original ask: {plan_step.refactoring_type}: {plan_step.reason}. {plan_step.execution_details}'
                                       f'Please reflect whether the task is complete, '
                                       f'by answering the following questions: '
                                       '1. Has the original ask been met? '
                                       f'2. Are there other locations within the file {plan_step.file_path} '
                                       f'where the same change can be applied? '
                                       'Finally say whether the task is complete '
                                       'using the word DONE/INCOMPLETE appropriately.')])
            return {'messages': [response]}

        def has_finished_fixing(state: MessagesState) -> bool:
            return (state['messages'][-1].content.endswith('DONE') or
                    'INCOMPLETE' not in state['messages'][-1].content)

        # Create the workflow graph
        workflow = StateGraph(MessagesState)
        
        # Add nodes
        workflow.add_node("perform_fixing", perform_fixing)
        workflow.add_node("finished_fixing", finished_fixing)

        # Add edges
        workflow.add_edge(START, "perform_fixing")
        workflow.add_conditional_edges("perform_fixing", has_finished_fixing,
                                       {True: END, False: "finished_fixing"})
        workflow.add_edge("finished_fixing", END)

        # Compile the graph
        return workflow.compile()

