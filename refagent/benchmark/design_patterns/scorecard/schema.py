import json
from pathlib import Path
from typing import List, Union, Optional, Annotated

from pydantic import BaseModel, Field


class BaseScorecardCheck(BaseModel):
    """Base model holding common fields for all checks."""
    weight: float = Field(default=1.0, description="Weighting for calculating recall score")
    expected: bool = Field(default=True, description="If False, the condition is inverted (must NOT be true)")
    impacts_recall: bool = Field(default=True, description="If True, the check will be used to compute recall score. "
                                                           "If false, it will be used to calculate precision score.")

    def _check(self, commit_hash: str, project_path: Path, rm_refactorings=None) -> bool:
        """
        Raw check logic to be implemented by each concrete subclass.
        Should return the true/false result of the condition WITHOUT applying the `expected` inversion.
        """
        raise NotImplementedError(f"_check() not implemented for {type(self).__name__}")

    def check(self, commit_hash: str, project_path: Path, rm_refactorings=None) -> bool:
        """
        Evaluates this check against the repository state at the given commit.
        Applies the `expected` flag: if expected=False, inverts the raw result.

        :param commit_hash: The git commit SHA to evaluate against.
        :param project_path: Path to the local repository root.
        :param rm_refactorings: Optional pre-run RefactoringMiner output (list of RefminerOut).
                                If None, RefactoringMinerCheck will run RM internally.
        :return: True if the check passes.
        """
        raw = self._check(commit_hash, project_path, rm_refactorings)
        return raw if self.expected else not raw


# ---------------------------------------------------------------------------
# Concrete check classes — each lives in its own file under checks/
# Imported here after BaseScorecardCheck is fully defined to avoid circular
# imports (the checks/ modules import BaseScorecardCheck from this module).
# ---------------------------------------------------------------------------

from .checks.refactoring_miner import RefactoringMinerCheck       # noqa: E402
from .checks.file_presence import FilePresenceCheck                # noqa: E402
from .checks.ast_base import ASTCheckBase                          # noqa: E402
from .checks.implements_abstraction import (ImplementsInterfaceCheck,
                                            ExtendsClassCheck)  # noqa: E402
from .checks.has_method import HasMethodCheck                      # noqa: E402
from .checks.has_constructor_visibility import HasConstructorVisibilityCheck  # noqa: E402
from .checks.has_field import HasFieldCheck                        # noqa: E402
from .checks.instantiates_class import InstantiatesClassCheck      # noqa: E402
from .checks.custom_ast import CustomDynamicASTCheck               # noqa: E402

# The discriminator tells Pydantic to use the 'type' field to select a subclass.
CheckItem = Annotated[Union[
    RefactoringMinerCheck,
    FilePresenceCheck,
    ImplementsInterfaceCheck,
    ExtendsClassCheck,
    HasMethodCheck,
    HasConstructorVisibilityCheck,
    HasFieldCheck,
    InstantiatesClassCheck,
    CustomDynamicASTCheck,
], Field(discriminator="type")]


class CandidateScorecard(BaseModel):
    """Represents a full evaluation scorecard for a refactoring candidate."""
    candidate_id: str = Field(description="The unique ID matching the candidate")
    checks: List[CheckItem] = Field(
        description="A list of binary checks to evaluate against the agent's proposed refactoring"
    )

    @classmethod
    def from_json_file(cls, path: str | Path) -> "CandidateScorecard":
        """Loads, parses, and validates a scorecard from a JSON file."""
        path = Path(path)
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.model_validate(data)

    @classmethod
    def from_json_string(cls, json_str: str) -> "CandidateScorecard":
        """Loads and validates a scorecard from a JSON string."""
        return cls.model_validate_json(json_str)
