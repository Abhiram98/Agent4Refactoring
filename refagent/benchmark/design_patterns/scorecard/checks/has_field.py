import re
from typing import Literal, Optional, Set

from pydantic import Field

from .ast_base import ASTCheckBase
from .. import ast_utils

_VISIBILITY_KEYWORDS = {"public", "protected", "private"}


class HasFieldCheck(ASTCheckBase):
    type: Literal["has_field"]
    field_type_regex: str = Field(description="Regex matching the data type of the field")
    field_name_regex: str = Field(description="Regex matching the field name")
    visibility: Optional[Literal["public", "protected", "private", "package-private"]] = Field(default=None)
    is_final: Optional[bool] = Field(default=None)
    is_static: Optional[bool] = Field(default=None)

    def _ast_check(self, root_node, source_bytes: bytes, target_node) -> bool:
        query_str = """
        (field_declaration
          type: (_) @field_type
          declarator: (variable_declarator
            name: (identifier) @field_name
          )
        ) @field_decl
        """
        captures = ast_utils.execute_query(target_node, query_str)
        type_pattern = re.compile(self.field_type_regex)
        name_pattern = re.compile(self.field_name_regex)

        field_nodes = captures.get("field_decl", []) if isinstance(captures, dict) \
            else [n for n, c in captures if c == "field_decl"]

        for field_node in field_nodes:
            sub = ast_utils.execute_query(field_node, query_str)
            ftypes = sub.get("field_type", []) if isinstance(sub, dict) else [n for n, c in sub if c == "field_type"]
            fnames = sub.get("field_name", []) if isinstance(sub, dict) else [n for n, c in sub if c == "field_name"]

            if not ftypes or not fnames:
                continue

            f_type = source_bytes[ftypes[0].start_byte:ftypes[0].end_byte].decode("utf-8")
            f_name = source_bytes[fnames[0].start_byte:fnames[0].end_byte].decode("utf-8")

            if not type_pattern.search(f_type) or not name_pattern.search(f_name):
                continue

            mods = self._get_modifiers(field_node, source_bytes)

            if self.visibility is not None:
                actual_vis = next((m for m in mods if m in _VISIBILITY_KEYWORDS), "package-private")
                if actual_vis != self.visibility:
                    continue

            if self.is_static is not None and ("static" in mods) != self.is_static:
                continue

            if self.is_final is not None and ("final" in mods) != self.is_final:
                continue

            return True
        return False

    @staticmethod
    def _get_modifiers(node, source_bytes: bytes) -> Set[str]:
        """Returns the set of modifier keyword strings on a declaration node."""
        mods: Set[str] = set()
        for child in node.children:
            if child.type == "modifiers":
                for mod in child.children:
                    mods.add(source_bytes[mod.start_byte:mod.end_byte].decode("utf-8"))
        return mods
