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
        Traverses the git commit tree at commit_hash (no checkout) and returns
        True when the file's actual state matches expected_state.
        """
        pattern = re.compile(self.file_regex)
        file_exists = False
        try:
            repo = Repo(project_path)
            for blob in repo.commit(commit_hash).tree.traverse():
                if blob.type == "blob" and pattern.search(blob.name):
                    file_exists = True
                    break
        except Exception as e:
            logger.warning(f"FilePresenceCheck: failed to traverse commit tree {commit_hash}: {e}")

        return file_exists if self.expected_state == "exists" else not file_exists
