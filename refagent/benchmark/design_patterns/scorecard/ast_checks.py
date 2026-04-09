import re
from pathlib import Path
from .ast_interface import ASTCheckEvaluator
from . import ast_utils

class BaseParameterizedASTCheck(ASTCheckEvaluator):
    def __init__(self, check_schema):
        self.check_schema = check_schema

    def _resolve_target_file(self, repo_path: Path) -> Path:
        """Finds the absolute path of the target_file in the repo."""
        matches = list(repo_path.rglob(self.check_schema.target_file))
        if not matches:
            raise FileNotFoundError(f"Target file {self.check_schema.target_file} not found in {repo_path}")
        return matches[0]

    def _evaluate(self, root_node, source_bytes: bytes, target_node) -> bool:
        """Override this to implement the specific structural check logic."""
        raise NotImplementedError()

    def evaluate(self, repo_path: Path, target_file: str, target_class: str) -> bool:
        try:
            filepath = self._resolve_target_file(repo_path)
            tree, source_bytes = ast_utils.parse_java_file(filepath)
            if not tree:
                return not self.check_schema.expected

            target_node = ast_utils.find_class_declaration(tree.root_node, source_bytes, target_class)
            if not target_node:
                return not self.check_schema.expected

            result = self._evaluate(tree.root_node, source_bytes, target_node)
            return result == self.check_schema.expected
        except Exception:
            return not self.check_schema.expected


class ImplementsInterfaceCheckEvaluator(BaseParameterizedASTCheck):
    def _evaluate(self, root_node, source_bytes: bytes, target_node) -> bool:
        query_str = """
        (class_declaration
          interfaces: (super_interfaces
            (type_list (type_identifier) @interface)
          )
        )
        """
        captures = ast_utils.execute_query(target_node, query_str)
        pattern = re.compile(self.check_schema.interface_regex)
        
        # Determine capture format (dict vs list of tuples based on tree-sitter version)
        if isinstance(captures, dict):
            nodes = captures.get("interface", [])
        else:
            nodes = [node for node, capture_name in captures if capture_name == "interface"]
            
        for node in nodes:
            name = source_bytes[node.start_byte:node.end_byte].decode('utf-8')
            if pattern.search(name):
                return True
        return False


class HasMethodCheckEvaluator(BaseParameterizedASTCheck):
    def _evaluate(self, root_node, source_bytes: bytes, target_node) -> bool:
        query_str = """
        (method_declaration
            name: (identifier) @method_name
            type: (_) @return_type
        ) @method_decl
        """
        captures = ast_utils.execute_query(target_node, query_str)
        name_pattern = re.compile(self.check_schema.method_name_regex)
        
        if self.check_schema.return_type_regex:
            return_pattern = re.compile(self.check_schema.return_type_regex)
        else:
            return_pattern = None

        method_decls = set()
        
        # Normalization for captures structure
        if isinstance(captures, dict):
            method_nodes = captures.get("method_decl", [])
        else:
            method_nodes = [n for n, c in captures if c == "method_decl"]

        for method_node in method_nodes:
            # Re-query this specific method to find its name and return type precisely
            sub_captures = ast_utils.execute_query(method_node, query_str)
            if isinstance(sub_captures, dict):
                names = sub_captures.get("method_name", [])
                types = sub_captures.get("return_type", [])
            else:
                names = [n for n, c in sub_captures if c == "method_name"]
                types = [n for n, c in sub_captures if c == "return_type"]
                
            if names:
                m_name = source_bytes[names[0].start_byte:names[0].end_byte].decode('utf-8')
                if name_pattern.search(m_name):
                    # We matched the name! Now check return type if provided
                    if return_pattern and types:
                        m_type = source_bytes[types[0].start_byte:types[0].end_byte].decode('utf-8')
                        if return_pattern.search(m_type):
                            return True
                    elif not return_pattern:
                        return True
        return False
