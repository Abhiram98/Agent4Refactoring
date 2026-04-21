import re
from typing import Literal, Optional

from pydantic import Field

from .ast_base import ASTCheckBase
from .. import ast_utils

class MethodInvocationCheck(ASTCheckBase):
    type: Literal["method_invocation"]
    invoked_method_regex: str = Field(
        description="Regex matching the name of the method being called (e.g. 'build' or 'getTableBuilder')"
    )
    calling_object_regex: Optional[str] = Field(
        default=None,
        description="Regex matching the object the method is called on (e.g. 'Connection' or '.*Builder')"
    )

    def _ast_check(self, root_node, source_bytes: bytes, target_node) -> bool:
        # We query for method invocations
        # A method_invocation looks like:
        # (method_invocation
        #   object: (identifier)? @obj
        #   name: (identifier) @meth_name
        # )
        query_str = """
        (method_invocation
          object: (_) @obj
          name: (identifier) @meth_name
        )
        """
        captures = ast_utils.execute_query(target_node, query_str)
        method_pattern = re.compile(self.invoked_method_regex)
        object_pattern = re.compile(self.calling_object_regex) if self.calling_object_regex else None

        if isinstance(captures, dict):
            obj_nodes_all = captures.get("obj", [])
            meth_nodes = captures.get("meth_name", [])
        else:
            obj_nodes_all = [n for n, c in captures if c == "obj"]
            meth_nodes = [n for n, c in captures if c == "meth_name"]

        # Tree-sitter captures might mismatch if we just iterate parallel lists when not every invocation has an object.
        # But 'object: (_)' forces it to have one in the query. For static methods or implicit 'this', 
        # tree-sitter might have a different structure. Let's query both forms.
        
        query_str_no_obj = """
        (method_invocation
          name: (identifier) @meth_name
        )
        """
        captures_all = ast_utils.execute_query(target_node, query_str_no_obj)
        if isinstance(captures_all, dict):
            meth_nodes_all = captures_all.get("meth_name", [])
        else:
            meth_nodes_all = [n for n, c in captures_all if c == "meth_name"]

        for meth_node in meth_nodes_all:
            method_name = source_bytes[meth_node.start_byte:meth_node.end_byte].decode("utf-8")
            if not method_pattern.match(method_name):
                continue
                
            if object_pattern is None:
                return True
                
            # If we need to match the object, let's find the parent method_invocation and its object child
            parent = meth_node.parent
            if parent and parent.type == "method_invocation":
                obj_child = parent.child_by_field_name("object")
                if obj_child:
                    obj_name = source_bytes[obj_child.start_byte:obj_child.end_byte].decode("utf-8")
                    if object_pattern.match(obj_name):
                        return True

        return False
