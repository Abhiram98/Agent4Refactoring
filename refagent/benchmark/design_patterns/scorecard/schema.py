import json
from pathlib import Path
from typing import List, Literal, Union

from pydantic import BaseModel, Field


class RefactoringMinerCheck(BaseModel):
    """Check matching a RefactoringMiner operation occurrence and description."""
    type: Literal["refactoring_miner"]
    operation_type: str = Field(
        description="The exact RefactoringMiner operation type (e.g., 'Extract Class', 'Move Method')"
    )
    description_regex: str = Field(
        description="Regex pattern to match against the RefactoringMiner description"
    )
    weight: float = Field(default=1.0, description="Weighting for calculating recall score")


class FilePresenceCheck(BaseModel):
    """Check verifying the presence or absence of a specific file by filename."""
    type: Literal["file_presence"]
    filename: str = Field(
        description="The exact name of the file WITHOUT the path"
    )
    expected_state: Literal["exists", "absent"] = Field(
        description="Whether the file should be present or deleted"
    )
    weight: float = Field(default=1.0, description="Weighting for calculating recall score")


# The discriminator tells Pydantic to use the 'type' field to figure out which subclass to instantiate
CheckItem = Union[RefactoringMinerCheck, FilePresenceCheck]


class CandidateScorecard(BaseModel):
    """Represents a full evaluation scorecard for a refactoring candidate."""
    candidate_id: str = Field(
        description="The unique ID matching the candidate"
    )
    checks: List[CheckItem] = Field(
        description="A list of binary checks to evaluate against the agent's proposed refactoring",
        discriminator="type"
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
