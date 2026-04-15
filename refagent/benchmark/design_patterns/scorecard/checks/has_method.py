import re
from typing import Literal, Optional

from pydantic import Field

from .ast_base import ASTCheckBase
from .. import ast_utils


def _node_has_modifier(node, source_bytes: bytes, modifier: str) -> bool:
    """Returns True if the declaration node's modifiers contain the given keyword."""
    for child in node.children:
        if child.type == "modifiers":
            for mod in child.children:
                if source_bytes[mod.start_byte:mod.end_byte].decode("utf-8") == modifier:
                    return True
    return False


class HasMethodCheck(ASTCheckBase):
    type: Literal["has_method"]
    method_name_regex: str = Field(description="Regex matching the method name")
    return_type_regex: Optional[str] = Field(default=None, description="Optional regex matching the return type")
    is_static: Optional[bool] = Field(default=None, description="Verify if the method is static")

    def _ast_check(self, root_node, source_bytes: bytes, target_node) -> bool:
        query_str = """
        (method_declaration
            name: (identifier) @method_name
            type: (_) @return_type
        ) @method_decl
        """
        captures = ast_utils.execute_query(target_node, query_str)
        name_pattern = re.compile(self.method_name_regex)
        return_pattern = re.compile(self.return_type_regex) if self.return_type_regex else None

        method_nodes = captures.get("method_decl", []) if isinstance(captures, dict) \
            else [n for n, c in captures if c == "method_decl"]

        for method_node in method_nodes:
            sub = ast_utils.execute_query(method_node, query_str)
            names = sub.get("method_name", []) if isinstance(sub, dict) else [n for n, c in sub if c == "method_name"]
            types = sub.get("return_type", []) if isinstance(sub, dict) else [n for n, c in sub if c == "return_type"]

            if not names:
                continue

            m_name = source_bytes[names[0].start_byte:names[0].end_byte].decode("utf-8")
            if not name_pattern.search(m_name):
                continue

            if return_pattern:
                if not types:
                    continue
                m_type = source_bytes[types[0].start_byte:types[0].end_byte].decode("utf-8")
                if not return_pattern.search(m_type):
                    continue

            if self.is_static is not None:
                if _node_has_modifier(method_node, source_bytes, "static") != self.is_static:
                    continue

            return True
        return False
