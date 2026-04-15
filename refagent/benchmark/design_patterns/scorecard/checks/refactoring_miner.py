import re
import logging
from pathlib import Path
from typing import Literal, Optional, List

import refagent.refactoring_types.refactorings as refactoring_types
from pydantic import Field

from ..schema import BaseScorecardCheck

logger = logging.getLogger(__name__)


class RefactoringMinerCheck(BaseScorecardCheck):
    """Check matching a RefactoringMiner operation occurrence and description."""
    type: Literal["refactoring_miner"]
    operation_type: str = Field(
        description="The exact RefactoringMiner operation type (e.g., 'Extract Class', 'Move Method')"
    )
    ref_operation: refactoring_types.RefminerOut = Field(
        description="The exact RefactoringMiner Operation."
    )
    description_regex: str = Field(
        description="Regex pattern to match against the RefactoringMiner description"
    )

    def _check(self, commit_hash: str, project_path: Path,
               rm_refactorings: Optional[List] = None) -> bool:
        """
        Returns True if any RM operation matches the expected operation_type
        and description_regex.  Runs RefactoringMiner internally when
        rm_refactorings is None.
        """
        if rm_refactorings is None:
            from refagent.utils.refminer_utils import default_runner
            logger.info(f"Running RefactoringMiner on {commit_hash} ...")
            rm_refactorings = default_runner.run(
                project_path=str(project_path), commit_hash=commit_hash
            )

        pattern = re.compile(self.description_regex)
        for op in rm_refactorings:
            # Support both Pydantic model objects and plain dicts
            op_type = op.type if hasattr(op, "type") else op.get("type", "")
            op_desc = op.description if hasattr(op, "description") else op.get("description", "")
            if op_type == self.operation_type and pattern.search(op_desc):
                return True
        return False
