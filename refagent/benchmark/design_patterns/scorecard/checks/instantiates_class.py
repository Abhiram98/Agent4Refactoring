import re
from typing import Literal

from pydantic import Field

from .ast_base import ASTCheckBase
from .. import ast_utils


class InstantiatesClassCheck(ASTCheckBase):
    type: Literal["instantiates_class"]
    instantiated_class_regex: str = Field(
        description="Regex matching the explicitly constructed class (e.g. after 'new ')"
    )

    def _ast_check(self, root_node, source_bytes: bytes, target_node) -> bool:
        query_str = """
        (object_creation_expression
          type: (_) @created_type
        )
        """
        captures = ast_utils.execute_query(target_node, query_str)
        pattern = re.compile(self.instantiated_class_regex)

        nodes = captures.get("created_type", []) if isinstance(captures, dict) \
            else [n for n, c in captures if c == "created_type"]

        for node in nodes:
            name = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
            if pattern.search(name):
                return True
        return False
