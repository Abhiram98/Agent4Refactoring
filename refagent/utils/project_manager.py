import pathlib
import git
from typing import Dict
from pathlib import Path
import re
from itertools import groupby
from pydantic import BaseModel, Field, root_validator

projects_base_path = pathlib.Path("/Users/abhiram/Documents/TBE/evaluation_projects")


class Hunk(BaseModel):
    """
    Represents a single hunk in a Git diff.
    """
    old_start: int = Field(..., description="Starting line number in the old file")
    old_lines: int = Field(..., description="Number of lines in the old file")
    new_start: int = Field(..., description="Starting line number in the new file")
    new_lines: int = Field(..., description="Number of lines in the new file")
    content: str = Field(..., description="The full hunk content as a string")

    @classmethod
    def from_header_and_content(cls, header: str, content_lines: list[str]) -> "Hunk":
        """
        Create a Hunk instance from a header line and content lines.

        Args:
            header (str): The hunk header line (e.g., @@ -1,2 +1,2 @@).
            content_lines (list[str]): The lines of the hunk content.

        Returns:
            Hunk: An instance of the Hunk class.
        """
        match = re.match(r"@@ -(\d+),?(\d+)? \+(\d+),?(\d+)? @@", header)
        if not match:
            raise ValueError(f"Invalid hunk header format: {header}")

        old_start = int(match.group(1))
        old_lines = int(match.group(2) or 1)
        new_start = int(match.group(3))
        new_lines = int(match.group(4) or 1)
        content = "\n".join([header] + content_lines)

        return cls(
            old_start=old_start,
            old_lines=old_lines,
            new_start=new_start,
            new_lines=new_lines,
            content=content,
        )

class MyDiff:
    def __init__(self, git_diff: git.Diff):
        self.git_diff = git_diff
        self.hunks = self.compute_hunks()

    def to_json(self):
        return {
            'a_filename': self.git_diff.a_rawpath.decode('utf-8') if self.git_diff.a_rawpath else None,
            'b_filename': self.git_diff.b_rawpath.decode('utf-8') if self.git_diff.b_rawpath else None,
            'renamed': self.git_diff.renamed,
            'copied': self.git_diff.copied_file,
            'deleted': self.git_diff.deleted_file,
            'change_type': self.git_diff.change_type,
            'hunks': [h.dict() for h in self.hunks]
        }


    @staticmethod
    def parse_hunk_metadata(header):
        """
        Parse the hunk metadata from the `@@` line.

        Args:
            header (str): The hunk header line (e.g., @@ -1,2 +1,2 @@).

        Returns:
            dict: Metadata with old_start, old_lines, new_start, and new_lines.
        """
        match = re.match(r"@@ -(\d+),?(\d+)? \+(\d+),?(\d+)? @@", header)
        if match:
            return {
                "old_start": int(match.group(1)),
                "old_lines": int(match.group(2) or 1),
                "new_start": int(match.group(3)),
                "new_lines": int(match.group(4) or 1),
            }
        return {}

    def compute_hunks(self) -> list[Hunk]:
        lines = self.git_diff.diff.decode('utf-8').splitlines()
        hunks = []
        header = None
        content_lines = []
        is_hunk_header = lambda x: x.startswith('@@')

        for is_header, group in groupby(lines, is_hunk_header):
            if is_header:
                # Process previous hunk
                if header:
                    hunks.append(Hunk.from_header_and_content(header, content_lines))
                # Start a new hunk
                header = next(group)
                content_lines = []
            else:
                content_lines.extend(group)

        # Process the final hunk
        if header:
            hunks.append(Hunk.from_header_and_content(header, content_lines))
        return hunks



class EvalProject:
    def __init__(self, project_name):
        self.project_name = project_name
        self.git_repo = git.Repo(self.get_project_path())

    def get_project_path(self):
        project_path = projects_base_path.joinpath(self.project_name)
        return project_path

    def checkout(self, sha1):
        self.git_repo.git.checkout(sha1)

    def checkout_previous(self, sha1):
        self.git_repo.git.checkout(
            self.git_repo.commit(sha1).parents[0])

    def get_file_contents(self, rel_file_path):
        with open(self.get_project_path().joinpath(rel_file_path)) as f:
            return f.read()

    def previous_sha(self, sha1):
        return self.git_repo.commit(sha1).parents[0]

    def get_changes(self, sha1) -> list[MyDiff]:
        commit = self.git_repo.commit(sha1)
        parent = commit.parents[0]
        diffs = commit.diff(parent, create_patch=True)
        return [MyDiff(d) for d in diffs]
