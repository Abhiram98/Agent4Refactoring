import re
import logging
from pathlib import Path
from typing import Literal

from git import Repo
from pydantic import Field

from ..schema import BaseScorecardCheck

logger = logging.getLogger(__name__)


class FilePresenceCheck(BaseScorecardCheck):
    """Check verifying the presence or absence of a specific file by filename."""
    type: Literal["file_presence"]
    file_regex: str = Field(description="A regex to match the file name.")
    expected_state: Literal["exists", "absent"] = Field(
        description="Whether the file should be present or absent at the given commit"
    )

    def _check(self, commit_hash: str, project_path: Path, rm_refactorings=None) -> bool:
        """
        Checks if a file matching self.file_regex was ADDED (if expected_state="exists")
        or DELETED (if expected_state="absent") in the given commit.
        """
        pattern = re.compile(self.file_regex)
        try:
            repo = Repo(project_path)
            commit = repo.commit(commit_hash)

            if not commit.parents:
                # Initial commit: all entries in the tree are 'added'.
                if self.expected_state == "absent":
                    return False

                for blob in commit.tree.traverse():
                    if blob.type == "blob" and pattern.search(blob.name):
                        return True
                return False

            # Not initial commit
            diff_index = commit.parents[0].diff(commit)
            change_type = 'A' if self.expected_state == "exists" else 'D'

            for diff_obj in diff_index.iter_change_type(change_type):
                # path is b_path for added, a_path for deleted
                path = diff_obj.b_path if diff_obj.b_path else diff_obj.a_path
                if path and pattern.search(path.split('/')[-1]):
                    return True

            return False
        except Exception as e:
            logger.warning(f"FilePresenceCheck: failed to check commit {commit_hash}: {e}")
            return False
