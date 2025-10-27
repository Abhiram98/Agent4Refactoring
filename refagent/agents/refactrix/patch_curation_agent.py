from typing import List, Tuple

import refagent.agents.refactrix.react_agent as react_agent
import refagent.agents.refactrix.perform_refactoring as perform_refactoring
import refagent.agents.refactrix.planning as planning
import refagent.agents.refactrix.supported_refactorings as sup_refs
import refagent.agents.refactrix.replication as replication


class PatchAgent(react_agent.ReactAgent):

    files_and_planning: List[Tuple[str, str]] = []

    def execute_plan(
        self,
        initial_intent,
        model,
        ref_plan,
        ask_finished_first_iteration=False,
        open_file=False,
    ):
        self.files_and_planning.append(
            (ref_plan.steps[0].file_path, ref_plan.steps[0].execution_details)
        )
        pass  # override to do nothing

    def perform_replication(self, current_intent, model, ref_plan):
        self.replication_strategy_class = replication.JarBasedReplication
        super().perform_replication(current_intent, model, ref_plan)
