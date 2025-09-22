import shutil

from pydantic import BaseModel
from pathlib import Path
import os

import refagent.benchmark.load as benchmark_load
from agents.memory.orm_memory import ORMRefactoringMemory
import refactoring_types.refactorings as refactorings
from refactoring_types.refactorings import RefminerOut


class InitMemory(BaseModel):
    benchmark_item: benchmark_load.RenameItem
    do_replication: bool
    use_seed: bool
    initial_intent: str
    source_code: str

    def init_memory(self, memory_db_path: Path) -> Path:
        no_replication_path = self.no_replication_path(memory_db_path)
        if self.do_replication:
            # copy from no-replication_file
            shutil.copyfile(no_replication_path, memory_db_path)
            return memory_db_path
        else:
            # delete it to run it again.
            if Path(no_replication_path).exists():
                os.remove(no_replication_path)
            memory_url = f"sqlite:///{no_replication_path}"
            orm_db = ORMRefactoringMemory(memory_url)

            if self.use_seed:
                seed = self.benchmark_item.seed_example
                # assert isinstance(seed, refactorings.Rename)
                seed_old_name = seed.old_name
                seed_new_name = seed.new_name

                orm_db.add_suggestion(
                    benchmark_id=self.benchmark_item.ref_id,
                    file_path=self.benchmark_item.starting_file,
                    old_name=seed_old_name,
                    new_name=seed_new_name,
                    line_num=seed.start_line,
                    code_element_type=self.get_code_element_type(seed),
                    is_valid=True,
                    feedback="First rename from the developer",
                    critique_reason="",
                    confidence_score=1.0,
                    agent_iteration=0,
                    llm_iteration=0,
                    snippet=self.get_code_on_line(seed.start_line),
                )
                orm_db.add_rename_scope(self.initial_intent)
            return no_replication_path

    def get_code_element_type(self, seed: RefminerOut):
        return seed.type.split('Rename ')[-1].lower()

    def no_replication_path(self, memory_db_path):
        extension = memory_db_path.suffix
        before_extension = memory_db_path.stem + '-no-replication'
        memory_db_path = Path(before_extension).with_suffix(extension)
        return memory_db_path

    def get_code_on_line(self, line_num: int, tolerance: int=10):
        half_tolerance = int(tolerance / 2)
        return "\n".join(self.source_code.splitlines(keepends=True)[line_num-half_tolerance : line_num+half_tolerance])

