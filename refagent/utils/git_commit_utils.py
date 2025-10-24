#!/usr/bin/env python3
"""
Simple Git commit utility to get previous SHA from a given commit.
Uses EvalProject class from project_manager.py.
"""

import sys
from typing import Optional

# Import EvalProject for git operations
from project_manager import EvalProject


def get_previous_sha(
    commit_sha: str, project_name: str = None, repo_path: str = "."
) -> Optional[str]:
    """
    Get the previous (parent) SHA from a given commit.

    Args:
        commit_sha (str): The commit SHA to get the parent of
        project_name (str): Name of the project (uses EvalProject)
        repo_path (str): Path to git repository (fallback if no project_name)

    Returns:
        Optional[str]: The parent commit SHA, or None if no parent exists or on error
    """
    try:
        if project_name:
            # Use EvalProject directly for known projects
            eval_project = EvalProject(project_name)
        else:
            # For local repositories, create EvalProject with custom path
            import pathlib
            import git

            eval_project = EvalProject.__new__(EvalProject)
            eval_project.project_name = "temp"
            eval_project.git_repo = git.Repo(repo_path)
            eval_project.get_project_path = lambda: pathlib.Path(repo_path)

        # Use EvalProject's previous_sha method
        parent_commit = eval_project.previous_sha(commit_sha)
        return parent_commit.hexsha if parent_commit else None

    except Exception as e:
        print(f"Error getting previous SHA: {e}")
        return None


def main():
    """
    Command-line interface for getting previous commit SHA.
    """
    if len(sys.argv) < 2:
        print(
            "Usage: python git_commit_utils.py <commit_sha> [--project <project_name>] [repo_path]"
        )
        print("Examples:")
        print("  python git_commit_utils.py HEAD")
        print("  python git_commit_utils.py HEAD --project flink")
        print("  python git_commit_utils.py abc123def /path/to/repo")
        sys.exit(1)

    commit_sha = sys.argv[1]
    project_name = None
    repo_path = "."

    # Parse arguments
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == "--project" and i + 1 < len(sys.argv):
            project_name = sys.argv[i + 1]
            i += 2
        else:
            repo_path = sys.argv[i]
            i += 1

    # Get previous SHA
    previous_sha = get_previous_sha(commit_sha, project_name, repo_path)

    if previous_sha:
        print(previous_sha)
    else:
        print("No previous SHA found", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
