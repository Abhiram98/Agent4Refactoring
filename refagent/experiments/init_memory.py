import shutil
from typing import Optional

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
    do_replication: bool
    use_seed: bool
    initial_intent: Optional[str]
    snippet_code: Optional[str]

    seed_old_name: Optional[str]
    seed_new_name: Optional[str]
    seed_line_number: Optional[int]
    seed_type: Optional[str]
    seed_file: Optional[str]
    ref_id: Optional[int]

    def init_memory(self, memory_db_path: Path) -> Path:
        no_replication_path = self.no_replication_path(memory_db_path)
        os.makedirs(no_replication_path.parent, exist_ok=True)
        if self.do_replication:
            # copy from no-replication_file
            shutil.copyfile(no_replication_path, memory_db_path)
            return memory_db_path
        else:
            assert self.initial_intent is not None, "Initial intent must be provided"
            assert self.snippet_code is not None, "Snippet code must be provided"

            assert self.seed_old_name is not None, "Seed old name must be provided"
            assert self.seed_new_name is not None, "Seed new name must be provided"
            assert (
                self.seed_line_number is not None
            ), "Seed line number must be provided"
            assert self.seed_type is not None, "Seed type must be provided"
            assert self.seed_file is not None, "Seed file must be provided"
            assert self.ref_id is not None, "Ref id must be provided"

            # delete it to run it again.
            if Path(no_replication_path).exists():
                os.remove(no_replication_path)
            memory_url = f"sqlite:///{no_replication_path}"
            orm_db = ORMRefactoringMemory(memory_url)

            if self.use_seed:
                # assert isinstance(seed, refactorings.Rename)
                orm_db.add_suggestion(
                    benchmark_id=self.ref_id,
                    file_path=self.seed_file,
                    old_name=self.seed_old_name,
                    new_name=self.seed_new_name,
                    line_num=self.seed_line_number,
                    code_element_type=self.seed_type,
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
