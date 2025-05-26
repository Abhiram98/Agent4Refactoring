import refagent.agents.refactrix.refactoring_agent as ra
import refagent.agents.refactrix.perform_refactoring as perform_refactoring
import refagent.agents.refactrix.planning as planning
import refagent.agents.refactrix.supported_refactorings as sup_refs


from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
import traceback

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
                                      f"Please do the following: {self.augmented_intent} "
                                      f"The final code is expected to look like this: {step.final_code}"
                                      f"ONLY make TOOL CALLS to perform actions."),
                    ]
                },
                config={"configurable": {"thread_id": 42}, "recursion_limit": 50}
            )
            self._trajectory += final_state['messages']
            print(f"Result of executing step {0}: ", final_state["messages"][-1].content)
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


