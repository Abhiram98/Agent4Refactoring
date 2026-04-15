from typing import Literal

from pydantic import Field

from .ast_base import ASTCheckBase
from .. import ast_utils

_VISIBILITY_KEYWORDS = {"public", "protected", "private"}


class HasConstructorVisibilityCheck(ASTCheckBase):
    type: Literal["has_constructor_visibility"]
    visibility: Literal["public", "protected", "private", "package-private"] = Field(
        description="Expected access modifier on the constructor"
    )

    def _ast_check(self, root_node, source_bytes: bytes, target_node) -> bool:
        query_str = "(constructor_declaration) @ctor_decl"
        captures = ast_utils.execute_query(target_node, query_str)

        ctor_nodes = captures.get("ctor_decl", []) if isinstance(captures, dict) \
            else [n for n, c in captures if c == "ctor_decl"]

        for ctor_node in ctor_nodes:
            actual = self._get_visibility(ctor_node, source_bytes)
            if actual == self.visibility:
                return True
        return False

    @staticmethod
    def _get_visibility(node, source_bytes: bytes) -> str:
        """Returns the visibility keyword of a constructor_declaration node."""
        for child in node.children:
            if child.type == "modifiers":
                for mod in child.children:
                    text = source_bytes[mod.start_byte:mod.end_byte].decode("utf-8")
                    if text in _VISIBILITY_KEYWORDS:
                        return text
        return "package-private"
