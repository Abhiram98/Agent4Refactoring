import re
from typing import Literal

from pydantic import Field

from .ast_base import ASTCheckBase
from .. import ast_utils


class ImplementsInterfaceCheck(ASTCheckBase):
    type: Literal["implements_interface"]
    interface_regex: str = Field(description="Regex matching the interface name")

    def _ast_check(self, root_node, source_bytes: bytes, target_node) -> bool:
        query_str = """
        (class_declaration
          interfaces: (super_interfaces
            (type_list (type_identifier) @interface)
          )
        )
        """
        captures = ast_utils.execute_query(target_node, query_str)
        pattern = re.compile(self.interface_regex)

        nodes = captures.get("interface", []) if isinstance(captures, dict) \
            else [n for n, c in captures if c == "interface"]

        for node in nodes:
            name = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
            if pattern.search(name):
                return True
        return False
