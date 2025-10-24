import shutil

from pydantic import BaseModel
from pathlib import Path
import os

import refagent.benchmark.load as benchmark_load
from refagent.agents.memory.orm_memory import ORMRefactoringMemory
import refagent.refactoring_types.refactorings as refactorings
from refagent.agents.refactrix.supported_refactorings import CodeElementType
from refagent.refactoring_types.refactorings import RefminerOut

import refagent.agents.refactrix.analysis.scope as scope


class InitMemory(BaseModel):
    benchmark_item: benchmark_load.RenameItem
    do_replication: bool
    use_seed: bool
    initial_intent: str
    snippet_code: str

    def init_memory(self, memory_db_path: Path) -> Path:
        no_replication_path = self.no_replication_path(memory_db_path)
        os.makedirs(no_replication_path.parent, exist_ok=True)
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
                    code_element_type=CodeElementType.get_rminer_str(seed.type),
                    is_valid=True,
                    feedback="First rename from the developer",
                    critique_reason="",
                    confidence_score=1.0,
                    agent_iteration=0,
                    llm_iteration=0,
                    snippet=self.snippet_code,
                )

                orm_db.add_rename_scope(scope.RenameScope(pattern=self.initial_intent))
            return no_replication_path

    def no_replication_path(self, memory_db_path) -> Path:
        extension = memory_db_path.suffix
        before_extension = memory_db_path.stem + "-no-replication"
        new_memory_db_path = Path(before_extension).with_suffix(extension)
        return memory_db_path.parent.joinpath(new_memory_db_path)
