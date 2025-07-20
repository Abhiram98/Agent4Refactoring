import os
from typing import Type

import refagent.agents.refactrix.refactoring_agent as ra
import refagent.agents.refactrix.perform_refactoring as perform_refactoring
import refagent.agents.refactrix.planning as planning
import refagent.agents.refactrix.supported_refactorings as sup_refs
import refagent.agents.refactrix.replication as replication


from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
import traceback

class ReactPerformer(perform_refactoring.PerformRefactoring):
    pass

class ReactAgent(ra.Agent):
    MAX_GRAPH_ITERATION: int = 10
    MAX_FAILING_TOOL_CALLS: int = 3
    replication_strategy_class: Type[replication.Replication] = replication.SimpleReplication

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

    def perform_replication(self, current_intent, model, ref_plan):
        replicator = self.replication_strategy_class(
            model=self._reasoning_model,
            executed_plan=ref_plan,
            ide_server=self.ide_server,
            initial_intent=self.augmented_intent,  # pass the augmented intent,
            # because the quality check's intent may be modified
            edited_files=list(self._files_changed),
            project=self.project,
            starting_file=self._starting_file,
            example_changes=self.get_important_files_diff(),
            refactoring_commit=self._internal_commits[0]
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

if __name__ == '__main__':
    import argparse
    import refagent.utils.intellij_server as ij
    import refagent.agents.refactrix.planning as planning


    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--project", help="Project name", required=True)
    parser.add_argument("-ij", "--ide-server", help="IdeServer address", default=os.getenv('IJ_SERVER_URL'))
    parser.add_argument("-s", "--starting-file", help="Starting file", required=True)
    parser.add_argument("-i", "--intent", help="Intent/prompt from the developer", required=True)

    args = parser.parse_args()
    vendor = 'grazie'
    ide_server = ij.IntellijServer(server_url=args.ide_server)

    agent = ReactAgent(
        ide_server=args.ide_server,
        model_name=f'{vendor}:gpt-4o-mini',
        reasoning_model_name = f'{vendor}:o4-mini',
        project = args.project,
        plan_component = planning.PlanningComponent,
        augmented_intent = args.intent,
        do_replication = True
    )
    # start session with the ide
    ide_server.call_tool("start_refactoring_session")

    try:
        agent.run(
            initial_intent=args.intent,
            starting_file=args.starting_file,
        )
    finally:
        ide_server.call_tool("end_refactoring_session")


