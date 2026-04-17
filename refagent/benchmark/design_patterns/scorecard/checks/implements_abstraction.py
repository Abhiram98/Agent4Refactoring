import re
from typing import Literal

from pydantic import Field

from .ast_base import ASTCheckBase
from .. import ast_utils


class ExtendsClassCheck(ASTCheckBase):
    type: Literal["extends_class"]
    base_class_regex: str = Field(description="Regex matching the base class name")

    def _ast_check(self, root_node, source_bytes: bytes, target_node) -> bool:
        has_extends = self.do_check(source_bytes, target_node)
        if not has_extends:
            check_interface = ImplementsInterfaceCheck(weight=self.weight,
                                     target_class=self.target_class,
                                     target_file=self.target_file,
                                     interface_regex=self.base_class_regex,
                                     type="implements_interface")
            return check_interface.do_check(source_bytes, target_node)
        else:
            return has_extends

    def do_check(self, source_bytes, target_node):
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


class ImplementsInterfaceCheck(ASTCheckBase):
    type: Literal["implements_interface"]
    interface_regex: str = Field(description="Regex matching the interface name")

    def _ast_check(self, root_node, source_bytes: bytes, target_node) -> bool:
        has_implements = self.do_check(source_bytes, target_node)
        if has_implements:
            return has_implements
        else:
            return ExtendsClassCheck(
                target_file=self.target_file,
                target_class=self.target_class,
                base_class_regex=self.interface_regex,
                type="extends_class"
            ).do_check(source_bytes, target_node)

    def do_check(self, source_bytes, target_node):
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
        return self.do_interface_check(source_bytes, target_node)

    def do_interface_check(self, source_bytes, target_node):
        query_str = """
        (interface_declaration
          name: (identifier) @interface.name
          )
           """
        captures = ast_utils.execute_query(target_node, query_str)
        pattern = re.compile(self.interface_regex)
        for interface in captures.get("interface.name", []):
            extends_interfaces = [i for i in interface.parent.children if i.type == "extends_interfaces"]
            if len(extends_interfaces) > 0 and pattern.search(extends_interfaces[0].text.decode("utf-8")):
                return True
        return False