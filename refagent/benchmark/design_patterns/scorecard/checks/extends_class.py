import re
from typing import Literal

from pydantic import Field

from .ast_base import ASTCheckBase
from .. import ast_utils


class ExtendsClassCheck(ASTCheckBase):
    type: Literal["extends_class"]
    base_class_regex: str = Field(description="Regex matching the base class name")

    def _ast_check(self, root_node, source_bytes: bytes, target_node) -> bool:
        query_str = """
        (class_declaration
          superclass: (superclass (type_identifier) @base_class)
        )
        """
        captures = ast_utils.execute_query(target_node, query_str)
        pattern = re.compile(self.base_class_regex)

        nodes = captures.get("base_class", []) if isinstance(captures, dict) \
            else [n for n, c in captures if c == "base_class"]

        for node in nodes:
            name = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
            if pattern.search(name):
                return True
        return False
