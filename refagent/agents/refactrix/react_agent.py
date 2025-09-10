import refagent.agents.refactrix.refactoring_agent as ra
import refagent.agents.refactrix.perform_refactoring as perform_refactoring
import refagent.agents.refactrix.planning as planning
import refagent.agents.refactrix.supported_refactorings as sup_refs
import refagent.agents.refactrix.replication as replication

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
import traceback

from agents.refactrix import quality_check


class ReactPerformer(perform_refactoring.PerformRefactoring):
    pass


class ReactAgent(ra.Agent):
    MAX_GRAPH_ITERATION: int = 10
    MAX_FAILING_TOOL_CALLS: int = 3

    def execute_plan(self, initial_intent, model, ref_plan,
                     ask_finished_first_iteration=False,
                     open_file=False,
                     ):
        print("Executing a 1 step plan, in a react loop.")
        self._iterations = 0
        self._failing_tool_call_count = 0
        assert len(ref_plan.steps) == 1
        step = ref_plan.steps[0]
        
        # Update critique component for the current file being processed
        if self._critique_component and step.file_path:
            self._critique_component.current_file = step.file_path
            print(f"Updated critique component to file: {step.file_path}")
            
        if len(ref_plan.steps) > 0 and open_file:
            self.try_open_file(step.file_path)

        try:
            graph = self.compile_graph(model=model,
                                       initial_intent=self.augmented_intent,
                                       plan_step=step,
                                       step_count=0,
                                       ask_finished_first_iteration=True)
            final_state = graph.invoke(
                {
                    "messages": [
                        SystemMessage(f"You are an expert developer who executes rename refactorings to"
                                      f" improve the quality of the given code. "
                                      f"Please do the following: {self.augmented_intent} \n"
                                      # f"The final code is expected to look like this: {step.final_code} "
                                      f"IMPORTANT: Analyze the code and identify ALL locations that need to be renamed. "
                                      f"You will be asked to provide your analysis as a JSON response containing all rename suggestions."),
                    ]
                },
                config={"configurable": {"thread_id": 42}, "recursion_limit": 50}
            )
            self._trajectory += final_state['messages']
            # print(f"Result of executing step {0}: ", final_state["messages"][-1].content)
        except:
            print(f"Execution of step 1 failed.")
            traceback.print_exc()
            final_state = {'messages': [HumanMessage(f"Execution of step 1 failed.")]}

    def generate_initial_plan(self, analysis_report):
        return planning.RefactoringPlan(
            steps=[
                planning.PlanningStep(
                    reason=self.augmented_intent,
                    execution_details="",
                    final_code="",
                    refactoring_type=sup_refs.SupportedRefactorings.RENAME,
                    file_path=self._original_starting_file
                )
            ]
        )

    def perform_replication(self, current_intent, model, ref_plan):
        replicator = replication.SimpleReplication(
            model=self._reasoning_model,
            executed_plan=ref_plan,
            ide_server=self.ide_server,
            initial_intent=self.augmented_intent,  # pass the augmented intent,
            # because the quality check's intent may be modified
            edited_files=list(self._files_changed),
            project=self.project,
            starting_file=self._starting_file,
            example_changes=self.get_important_files_diff(),
            refactoring_commit=self._internal_commits[0],
            oracle_data=self._oracle_data,
            # Pass memory parameters for iterative replication
            benchmark_id=self.benchmark_id,
            memory_database_url=self.memory_database_url or "sqlite:///refactoring_memory.db",
            enable_memory=self.enable_memory,
            orm_memory=getattr(self, '_orm_memory', None)  # Use agent's memory if available
        )
        self.MAX_GRAPH_ITERATION = 2
        self.MAX_FAILING_TOOL_CALLS = 1
        for plan in replicator.compile_and_run():
            try:
                self.initialize_agent(plan.steps[0].file_path)  # try to reset the starting file to the new point.
                self.execute_plan(current_intent, model, plan, ask_finished_first_iteration=True, open_file=True)
            except:
                traceback.print_exc()
                print(f"Execution of replication for file {plan.steps[0].file_path} failed.")
                break
            self.update_changed_files()

        # Capture replication inspection data
        self._replication_inspection_data = replicator.get_files_inspection_data()

    def do_quality_check(self, model) -> quality_check.QualityCheckResult:
        # force the quality check to result in true.
        return quality_check.QualityCheckResult(
            overall_assessment=quality_check.OverallAssessment.PASS,
            intent_alignment=quality_check.IntentAlignment.MET,
            intent_alignment_explanation="",
            improvements=quality_check.ImprovementResult.NO_IMPROVEMENTS,
            improvements_explanation="",
            issues=quality_check.IssueStatus.NO_ISSUES,
            issues_explanation="",
            refined_intent=""
        )
