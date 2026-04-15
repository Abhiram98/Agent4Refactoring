import logging
from pathlib import Path
from typing import Optional

from git import Repo
from pydantic import Field

from ..schema import BaseScorecardCheck
from .. import ast_utils

logger = logging.getLogger(__name__)


class ASTCheckBase(BaseScorecardCheck):
    """
    Shared base for all structural AST checks.

    Reads the target file's bytes directly from the git commit object store
    (no working-tree checkout), parses it with tree-sitter, locates the
    target class node, then delegates to _ast_check().
    """
    target_file: str = Field(
        description="The exact file basename to parse, WITHOUT its path (e.g. 'StreamSpliterator.java')"
    )
    target_class: str = Field(
        description="The name of the class (or interface) within the file to check"
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_file_bytes_from_commit(self, commit_hash: str, project_path: Path) -> Optional[bytes]:
        """
        Walks the git commit tree to locate target_file by basename and returns
        its raw bytes.  Returns None when the file is absent at that commit.
        """
        try:
            repo = Repo(project_path)
            for blob in repo.commit(commit_hash).tree.traverse():
                if blob.type == "blob" and blob.name == self.target_file:
                    return blob.data_stream.read()
        except Exception as e:
            logger.warning(
                f"ASTCheckBase: could not read '{self.target_file}' "
                f"from commit {commit_hash}: {e}"
            )
        return None

    # ------------------------------------------------------------------
    # Template method
    # ------------------------------------------------------------------

    def _ast_check(self, root_node, source_bytes: bytes, target_node) -> bool:
        """
        Override in subclasses to implement the specific structural constraint.
        target_node is the tree-sitter class_declaration (or interface_declaration)
        node for self.target_class.
        """
        raise NotImplementedError(f"_ast_check() not implemented for {type(self).__name__}")

    def _check(self, commit_hash: str, project_path: Path, rm_refactorings=None) -> bool:
        """
        Reads the file from the commit tree, parses it, finds the target class,
        and invokes _ast_check().  Returns False at any failure point.
        """
        source_bytes = self._get_file_bytes_from_commit(commit_hash, project_path)
        if source_bytes is None:
            return False

        tree, source_bytes = ast_utils.parse_java_bytes(source_bytes)
        if tree is None:
            return False

        target_node = ast_utils.find_class_declaration(tree.root_node, source_bytes, self.target_class)
        if target_node is None:
            return False

        return self._ast_check(tree.root_node, source_bytes, target_node)
