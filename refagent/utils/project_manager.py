import pathlib
import git
from typing import Dict
from pathlib import Path
import re
from itertools import groupby

from git import Commit
from pydantic import BaseModel, Field, root_validator
import os
import subprocess

projects_base_path = pathlib.Path(os.environ.get('PROJECTS_BASE_PATH'))


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

    def get_first_edited_line(self):
        edited_lines = self.content.split('\n')[1:]  # ignore the first line as it is the header
        new_lines = [i.startswith('+') for i in edited_lines if not i.startswith('-')]
        first_new_line = new_lines.index(True) if True in new_lines else -1
        if first_new_line >= 0:
            return self.new_start + first_new_line
        else:
            # all the lines in the hunk were delete. Return just the starting line
            return self.new_start

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
            'hunks': [h.dict() for h in self.hunks],
            'patch': self.git_diff.diff.decode('utf-8')
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

    def checkout(self, sha1, force=False):
        self.git_repo.git.checkout(sha1, force=force)

    def checkout_previous(self, sha1):
        self.git_repo.git.checkout(
            self.git_repo.commit(sha1).parents[0])

    def get_file_contents(self, rel_file_path):
        with open(self.get_project_path().joinpath(rel_file_path)) as f:
            return f.read()

    def previous_sha(self, sha1):
        return self.git_repo.commit(sha1).parents[0]

    def get_changes(self, sha1: str) -> list[MyDiff]:
        commit = self.git_repo.commit(sha1)
        parent = commit.parents[0]
        diffs = parent.diff(commit, create_patch=True)
        return [MyDiff(d) for d in diffs]

    def get_unstaged_changes(self) -> list[MyDiff]:
        diffs = self.git_repo.index.diff(None, create_patch=True)
        return [MyDiff(d) for d in diffs]

    def get_staged_changes(self) -> list[MyDiff]:
        diffs = self.git_repo.head.commit.diff(create_patch=True)
        return [MyDiff(d) for d in diffs]

    def get_changed_files(self) -> list[str]:
        result = subprocess.run(
            ['git', '-C', self.get_project_path(), 'status', '--short'], capture_output=True, text=True, check=True)
        return [i.split(' ')[-1] for i in result.stdout.strip().splitlines()]

    def get_all_uncommitted_changes(self) -> list[MyDiff]:
        diffs = self.git_repo.head.commit.diff(None, create_patch=True)
        return [MyDiff(d) for d in diffs]

    def replace_contents(self, file_path, new_content):
        try:
            with open(self.get_project_path().joinpath(file_path), "w") as f:
                f.write(new_content)
            return True  # success
        except:
            return False

    def run_ls(self, directory_path):
        return os.listdir(self.get_project_path().joinpath(directory_path))

    def commit_all(self, commit_msg):
        self.git_repo.git.add(all=True)
        return self.git_repo.index.commit(commit_msg)

    def add_files(self, files_changed):
        if len(files_changed) > 0:
            self.git_repo.git.add(files_changed)

    def safe_add(self, files_changed):
        actual_files = [file for file in files_changed if
                        os.path.exists(self.get_project_path().joinpath(file))]
        self.git_repo.git.add(actual_files)

    def get_git_diff(self, file_path: str, head_count: int=None) -> str:
        if head_count is not None:
            result = subprocess.run(
                ['git', '-C', self.get_project_path(), 'diff', f'HEAD~{head_count}', file_path], capture_output=True, text=True, check=True)
            return result.stdout
        result = subprocess.run(
            ['git', '-C', self.get_project_path(), 'diff', file_path], capture_output=True, text=True, check=True)
        if result.stdout == '':
            result = subprocess.run(
                ['git', '-C', self.get_project_path(), 'diff', '--staged', file_path], capture_output=True, text=True, check=True)
        return result.stdout

    def file_exists(self, file_path: str) -> bool:
        return os.path.exists(self.get_project_path().joinpath(file_path))

    def reset_head(self, count=0) -> str:
        # git reset --soft HEAD^
        if count==0:
            head_str = 'HEAD^'
        else:
            head_str = f'HEAD~{count}'
        result = subprocess.run(
            ['git', '-C', self.get_project_path(), 'reset', '--soft', head_str],
            capture_output=True, text=True, check=True)
        return result.stdout

    def restore_changes(self):
        result = subprocess.run(
            ['git', '-C', self.get_project_path(), 'restore', '--staged', '.'],
            capture_output=True, text=True, check=True)
        result = subprocess.run(
            ['git', '-C', self.get_project_path(), 'restore', '.'],
            capture_output=True, text=True, check=True)
        result = subprocess.run(
            ['git', '-C', self.get_project_path(), 'clean', '-fd'],
            capture_output=True, text=True, check=True)
        return result.stdout

    def squash_changes(self, commit_message: str, count: int) -> Commit:
        if count > 0:
            self.reset_head(count)
        new_hash = self.git_repo.index.commit(commit_message)
        return new_hash

    def get_file_content_by_sha(self, sha1: str, file_path: str) -> str:
        commit = self.git_repo.commit(sha1)
        file_contents = commit.tree[file_path].data_stream.read().decode('utf-8')
        return file_contents

    def get_unified_file_diff_between_commits(self, sha1: str, sha2: str, file_path: str) -> str:
        result = subprocess.run(
            ['git', '-C', self.get_project_path(), 'diff', '-U100', sha1, sha2, '--', file_path], capture_output=True, text=True, check=True)
        return result.stdout

    def pull_project(self):
        result = subprocess.run(
            ['git', '-C', self.get_project_path(), 'pull', 'origin',
             self.get_master_branch_name()], capture_output=True, text=True, check=True)
        return result.stdout

    def get_master_branch_name(self):
        # git symbolic-ref refs/remotes/origin/HEAD
        result = subprocess.run(
            ['git', '-C', self.get_project_path(), 'symbolic-ref', 'refs/remotes/origin/HEAD'], capture_output=True, text=True, check=True)
        return result.stdout.split('/')[-1].strip()

    def get_remote_url(self):
        result = subprocess.run(
            ['git', '-C', self.get_project_path(), 'remote', 'get-url', 'origin'], capture_output=True, text=True, check=True)
        return result.stdout.strip().rstrip('.git')

    def create_branch(self, branch_name):
        result = subprocess.run(
            ['git', '-C', self.get_project_path(), 'checkout', '-b',
            branch_name], capture_output=True, text=True, check=True
        )
        return result.stdout

    def push_upstream_branch(self, branch_name):
        # git push --set-upstream origin seed-1077
        result = subprocess.run(
            ['git', '-C', self.get_project_path(), 'push', '--set-upstream',
             'origin', branch_name], capture_output=True, text=True, check=True
        )
        return result.stdout
    
    def get_commit_diff(self, file_path_1: str, file_path_2: str, sha_1: str, sha_2: str, unified_context: int = 3) -> str:
        result = subprocess.run(
            [
                'git',
                '-C', str(self.get_project_path()),
                'diff',
                f'-U{unified_context}',
                sha_1,
                sha_2,
                '--',
                file_path_1,
                file_path_2
            ],
            capture_output=True, text=True, check=True
        )
        return result.stdout