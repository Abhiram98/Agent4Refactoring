import logging
import re
from pathlib import Path
from typing import List, Optional

from git import Repo
from pydantic import Field

from ..schema import BaseScorecardCheck
from .. import ast_utils

logger = logging.getLogger(__name__)


class RegexASTCheckBase(BaseScorecardCheck):
    """
    Shared base for AST checks that search for files and classes by regex.
    """
    target_file_regex: str = Field(
        description="A regex pattern to match the file basename (e.g. '.*Builder.*\\.java')"
    )
    target_class_regex: str = Field(
        description="A regex pattern to match the class or interface name (e.g. '.*Builder.*')"
    )

    def _get_matching_blobs_from_commit(self, commit_hash: str, project_path: Path):
        """
        Walks the git commit tree and yields (filename, bytes) for all matching blobs.
        """
        pattern = re.compile(self.target_file_regex)
        try:
            repo = Repo(project_path)
            for blob in repo.commit(commit_hash).tree.traverse():
                if blob.type == "blob" and pattern.match(blob.name):
                    yield blob.name, blob.data_stream.read()
        except Exception as e:
            logger.warning(
                f"RegexASTCheckBase: could not traverse tree at commit {commit_hash}: {e}"
            )

    def _find_matching_class_declarations(self, root_node, source_bytes: bytes):
        """
        Finds all class or interface declarations matching target_class_regex.
        """
        pattern = re.compile(self.target_class_regex)
        
        query_str = """
        [
          (class_declaration name: (identifier) @name)
          (interface_declaration name: (identifier) @name)
        ] @decl
        """
        captures = ast_utils.execute_query(root_node, query_str)
        
        if isinstance(captures, dict):
            decl_nodes = captures.get("decl", [])
            name_nodes = captures.get("name", [])
        else:
            decl_nodes = [n for n, c in captures if c == "decl"]
            name_nodes = [n for n, c in captures if c == "name"]

        decl_to_name = {}
        for d_node in decl_nodes:
            for n_node in name_nodes:
                if n_node.parent == d_node:
                    decl_to_name[d_node] = source_bytes[n_node.start_byte:n_node.end_byte].decode('utf-8')
                    break

        matching_nodes = []
        for d_node, name in decl_to_name.items():
            if pattern.match(name):
                matching_nodes.append(d_node)
                
        return matching_nodes

    def _ast_check(self, root_node, source_bytes: bytes, target_node) -> bool:
        raise NotImplementedError()

    def _check(self, commit_hash: str, project_path: Path, rm_refactorings=None) -> bool:
        """
        Checks if ANY matching class in ANY matching file satisfies _ast_check.
        """
        for filename, source_bytes in self._get_matching_blobs_from_commit(commit_hash, project_path):
            tree, source_bytes = ast_utils.parse_java_bytes(source_bytes)
            if tree is None:
                continue

            target_nodes = self._find_matching_class_declarations(tree.root_node, source_bytes)
            for node in target_nodes:
                if self._ast_check(tree.root_node, source_bytes, node):
                    return True # Passed on at least one class!
                    
        return False


class ClassMatchingRegexCheck(RegexASTCheckBase):
    """
    Checks if there exists a class matching regexes that contains the required methods.
    """
    type: str = Field(default="class_matching_regex", Literal=True)
    has_methods: List[str] = Field(
        default_factory=list,
        description="A list of regex patterns for method names the class must contain"
    )

    def _ast_check(self, root_node, source_bytes: bytes, target_node) -> bool:
        """
        Checks if target_node has all methods specified by has_methods.
        """
        if not self.has_methods:
            return True

        query_str = """
        (method_declaration
            name: (identifier) @method_name
        )
        """
        captures = ast_utils.execute_query(target_node, query_str)
        if isinstance(captures, dict):
            method_nodes = captures.get("method_name", [])
        else:
            method_nodes = [n for n, c in captures if c == "method_name"]

        found_methods = set()
        for m_node in method_nodes:
            method_name = source_bytes[m_node.start_byte:m_node.end_byte].decode('utf-8')
            for method_regex in self.has_methods:
                if re.match(method_regex, method_name):
                    found_methods.add(method_regex)
                    break
        
        # We need to find at least one match for every required method pattern
        return len(found_methods) == len(self.has_methods)


from .ast_base import ASTCheckBase

class AntiPatternRemovalCheck(ASTCheckBase):
    """
    Evaluates whether a target file no longer contains certain anti-pattern methods.
    (e.g., removing legacy setters, or making sure constructors aren't too large).
    """
    type: str = Field(default="anti_pattern_removal", Literal=True)
    forbidden_methods: List[str] = Field(
        default_factory=list,
        description="A list of method regexes that should NOT be present."
    )
    forbidden_constructor_params_threshold: Optional[int] = Field(
        default=None,
        description="If set to N, any constructor with >N parameters causes a failure."
    )
    
    def _ast_check(self, root_node, source_bytes: bytes, target_node) -> bool:
        # Check forbidden methods
        if self.forbidden_methods:
            query_str = """
            (method_declaration
                name: (identifier) @method_name
            )
            """
            captures = ast_utils.execute_query(target_node, query_str)
            if isinstance(captures, dict):
                method_nodes = captures.get("method_name", [])
            else:
                method_nodes = [n for n, c in captures if c == "method_name"]

            for m_node in method_nodes:
                method_name = source_bytes[m_node.start_byte:m_node.end_byte].decode('utf-8')
                for method_regex in self.forbidden_methods:
                    if re.match(method_regex, method_name):
                        logger.debug(f"AntiPatternRemovalCheck failed: found forbidden method {method_name}")
                        return False

        # Check constructors
        if self.forbidden_constructor_params_threshold is not None:
            query_str = """
            (constructor_declaration
                parameters: (formal_parameters) @params
            )
            """
            captures = ast_utils.execute_query(target_node, query_str)
            if isinstance(captures, dict):
                param_nodes = captures.get("params", [])
            else:
                param_nodes = [n for n, c in captures if c == "params"]

            for p_node in param_nodes:
                # Count commas in formal_parameters to get param count, or count child nodes
                # Easier: just count the formal_parameter children
                param_count = sum(1 for child in p_node.children if child.type == "formal_parameter")
                if param_count > self.forbidden_constructor_params_threshold:
                    logger.debug(f"AntiPatternRemovalCheck failed: constructor has {param_count} params")
                    return False

        return True
