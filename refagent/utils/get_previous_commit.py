import os
import sys
from dotenv import load_dotenv

load_dotenv()

from project_manager import EvalProject


def get_project_root():
    current_file = os.path.abspath(__file__)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
    return project_root


def get_previous_commit_hash(project_name, commit_hash):
    """
    Get the previous commit hash from a given commit hash.

    Args:
        project_name (str): Name of the project
        commit_hash (str): The commit hash to get the previous commit for

    Returns:
        str: The previous commit hash, or None if not found
    """
    try:
        project = EvalProject(project_name)
        # Get the parent commit hash (previous commit)
        previous_commit = project.previous_sha(commit_hash)
        return previous_commit.hexsha
    except Exception as e:
        print(f"Error getting previous commit hash: {e}")
        return None


def main():
    if len(sys.argv) != 3:
        print("Usage: python get_previous_commit.py <project_name> <commit_hash>")
        print("Example: python get_previous_commit.py vespa abc123def456")
        return

    project_name = sys.argv[1]
    commit_hash = sys.argv[2]

    previous_hash = get_previous_commit_hash(project_name, commit_hash)

    if previous_hash:
        print(previous_hash)
    else:
        print("Could not retrieve previous commit hash")
        sys.exit(1)


if __name__ == "__main__":
    main()
