import json
from pathlib import Path
from typing import List, Literal, Union, Optional

from pydantic import BaseModel, Field


class BaseScorecardCheck(BaseModel):
    """Base model holding common fields for all checks."""
    weight: float = Field(default=1.0, description="Weighting for calculating recall score")
    expected: bool = Field(default=True, description="If False, the condition is inverted (must NOT be true)")


class RefactoringMinerCheck(BaseScorecardCheck):
    """Check matching a RefactoringMiner operation occurrence and description."""
    type: Literal["refactoring_miner"]
    operation_type: str = Field(
        description="The exact RefactoringMiner operation type (e.g., 'Extract Class', 'Move Method')"
    )
    description_regex: str = Field(
        description="Regex pattern to match against the RefactoringMiner description"
    )


class FilePresenceCheck(BaseScorecardCheck):
    """Check verifying the presence or absence of a specific file by filename."""
    type: Literal["file_presence"]
    filename: str = Field(
        description="The exact name of the file WITHOUT the path"
    )
    expected_state: Literal["exists", "absent"] = Field(
        description="Whether the file should be present or deleted"
    )


# --- AST Parameterized Checks ---

class ASTCheckBase(BaseScorecardCheck):
    """Base for all structural AST checks."""
    target_file: str = Field(description="The exact name of the file to parse WITHOUT the path (e.g. 'StreamSpliterator.java')")
    target_class: str = Field(description="The name of the class within the file to check")


class ImplementsInterfaceCheck(ASTCheckBase):
    type: Literal["implements_interface"]
    interface_regex: str = Field(description="Regex matching the interface name")


class ExtendsClassCheck(ASTCheckBase):
    type: Literal["extends_class"]
    base_class_regex: str = Field(description="Regex matching the base class name")


class HasMethodCheck(ASTCheckBase):
    type: Literal["has_method"]
    method_name_regex: str = Field(description="Regex matching the method name")
    return_type_regex: Optional[str] = Field(default=None, description="Optional regex matching the return type")
    is_static: Optional[bool] = Field(default=None, description="Verify if the method is static")


class HasConstructorVisibilityCheck(ASTCheckBase):
    type: Literal["has_constructor_visibility"]
    visibility: Literal["public", "protected", "private", "package-private"] = Field(description="Expected access modifier")


class HasFieldCheck(ASTCheckBase):
    type: Literal["has_field"]
    field_type_regex: str = Field(description="Regex matching the data type of the field")
    visibility: Optional[Literal["public", "protected", "private", "package-private"]] = Field(default=None)
    is_final: Optional[bool] = Field(default=None)
    is_static: Optional[bool] = Field(default=None)


class InstantiatesClassCheck(ASTCheckBase):
    type: Literal["instantiates_class"]
    instantiated_class_regex: str = Field(description="Regex matching the explicitly constructed class (e.g. after 'new ')")


class CustomDynamicASTCheck(ASTCheckBase):
    """Escape hatch for complex structural logic."""
    type: Literal["custom_ast"]
    check_description: str = Field(description="Human readable description of the custom constraint")
    python_eval_code: str = Field(description="Raw Python code defining a function 'def evaluate_custom(root_node, source_bytes): -> bool'")


# The discriminator tells Pydantic to use the 'type' field to figure out which subclass to instantiate
CheckItem = Union[
    RefactoringMinerCheck, 
    FilePresenceCheck,
    ImplementsInterfaceCheck,
    ExtendsClassCheck,
    HasMethodCheck,
    HasConstructorVisibilityCheck,
    HasFieldCheck,
    InstantiatesClassCheck,
    CustomDynamicASTCheck
]


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
