import re
from pathlib import Path
from typing import Literal

from pydantic import Field

from .ast_base import ASTCheckBase
from .. import ast_utils


class CustomDynamicASTCheck(ASTCheckBase):
    """Escape hatch for complex structural logic that cannot be expressed parametrically."""
    type: Literal["custom_ast"]
    check_description: str = Field(description="Human readable description of the custom constraint")
    python_eval_code: str = Field(
        description="Raw Python code defining a function 'def evaluate_custom(root_node, source_bytes): -> bool'"
    )

    def _check(self, commit_hash: str, project_path: Path, rm_refactorings=None) -> bool:
        raise NotImplementedError(
            "CustomDynamicASTCheck._check() is not yet implemented. "
            f"Description: {self.check_description}"
        )
