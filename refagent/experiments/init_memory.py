from pydantic import BaseModel
from pathlib import Path
import os

import refagent.benchmark.load as benchmark_load
from agents.memory.orm_memory import ORMRefactoringMemory
import refactoring_types.refactorings as refactorings


class InitMemory(BaseModel):
    benchmark_item: benchmark_load.RenameItem
    do_replication: bool
    use_seed: bool

    def init_memory(self, memory_db_path: str):
        if self.do_replication:
            return # nothing to do because it is assumed that memory will be used from previous session
        else:
            # delete it to run it again.
            if Path(memory_db_path).exists():
                os.remove(memory_db_path)

            memory_url = f"sqlite:///{memory_db_path}"
            orm_db = ORMRefactoringMemory(memory_url)

            if self.use_seed:
                seed = self.benchmark_item.seed_example
                # assert isinstance(seed, refactorings.Rename)
                seed_old_name = seed.old_name
                seed_new_name = seed.new_name
                orm_db.set_positive_example((seed_old_name, seed_new_name))

                orm_db.add_suggestion(
                    benchmark_id=self.benchmark_item.ref_id,
                    file_path=self.benchmark_item.starting_file,
                    old_name=seed_old_name,
                    new_name=seed_new_name,
                    line_num=seed.start_line,
                    code_element_type=seed.type,
                    is_valid=True,
                    feedback="First rename from the developer",
                    critique_reason="",
                    confidence_score=1.0,
                    agent_iteration=0,
                    llm_iteration=0
                )
