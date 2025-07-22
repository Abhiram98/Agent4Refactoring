#!/usr/bin/env python3
"""
Script to create git branches from JSON benchmark data using internal_commits.
Branch pattern: benchmark-internal-{id}-{first9-of-commit}
For multiple internal commits: benchmark-internal-{id}-{index}-{first9-of-commit}

Usage:
    python create_branches_internal.py <json_file_path> [git_repo_path]

Examples:
    python create_branches_internal.py data/results/baseline-july-07-ratpack-ws/no-replication.json
    python create_branches_internal.py data/results/baseline-july-07-ratpack-ws/no-replication.json /path/to/repo

Note: This script looks for "internal_commits" field which should be a list of commit hashes.
"""

import json
import subprocess
import sys
from pathlib import Path


def run_git_command(command, repo_path=None):
    """Run a git command and return the result."""
    try:
        if repo_path:
            # Replace 'git' with 'git -C repo_path'
            if command.startswith('git '):
                command = f"git -C {repo_path} {command[4:]}"
            else:
                command = f"git -C {repo_path} {command}"
        result = subprocess.run(command, shell=True, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Git command failed: {command}")
        print(f"Error: {e.stderr}")
        return None


def create_branch_from_commit(branch_name, commit_hash, repo_path=None):
    """Create a git branch from a specific commit."""
    # Check if branch already exists
    existing_branches = run_git_command("git branch -a", repo_path)
    if existing_branches and branch_name in existing_branches:
        print(f"Branch '{branch_name}' already exists, skipping...")
        return False

    # Create branch from commit
    command = f"git checkout -b {branch_name} {commit_hash}"
    result = run_git_command(command, repo_path)

    if result is not None:
        print(f"Created branch: {branch_name}")
        # Switch back to original branch
        run_git_command("git checkout -", repo_path)
        return True
    else:
        print(f"Failed to create branch: {branch_name}")
        return False


def process_json_file(file_path, repo_path=None):
    """Process the JSON file and create branches for each data point."""
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)

        # Handle different JSON structures
        if isinstance(data, list):
            entries = data
        elif isinstance(data, dict):
            # If it's a single entry, wrap in list
            if 'id' in data and 'response' in data:
                entries = [data]
            else:
                # If it's a dict with multiple entries
                entries = list(data.values()) if data else []
        else:
            print("Unsupported JSON format")
            return

        created_count = 0
        skipped_count = 0

        for entry in entries:
            try:
                # Extract id and internal_commits
                entry_id = entry.get('id')

                # Handle nested response structure
                internal_commits = None
                if 'response' in entry and 'internal_commits' in entry['response']:
                    internal_commits = entry['response']['internal_commits']
                elif 'internal_commits' in entry:
                    internal_commits = entry['internal_commits']
                else:
                    print(f"No internal_commits found in entry {entry_id}, skipping...")
                    continue

                if entry_id is None or not internal_commits:
                    print(f"Missing id or internal_commits in entry {entry_id}, skipping...")
                    continue

                # Ensure internal_commits is a list
                if not isinstance(internal_commits, list):
                    print(f"internal_commits is not a list for entry {entry_id}, skipping...")
                    continue

                print(f"Processing entry {entry_id} with {len(internal_commits)} internal commit(s)")

                # Process each commit in internal_commits
                for i, commit_hash in enumerate(internal_commits):
                    if not commit_hash or not isinstance(commit_hash, str):
                        print(f"  Invalid commit hash at index {i}: {commit_hash}, skipping...")
                        continue

                    # Get first 9 characters of commit hash
                    short_commit = commit_hash[:9]

                    # Create branch name - include index if multiple commits
                    if len(internal_commits) == 1:
                        branch_name = f"benchmark-internal-{entry_id}-{short_commit}"
                    else:
                        branch_name = f"benchmark-internal-{entry_id}-{i + 1}-{short_commit}"

                    print(f"  Creating branch for commit {i + 1}/{len(internal_commits)}: {commit_hash}")

                    if create_branch_from_commit(branch_name, commit_hash, repo_path):
                        created_count += 1
                    else:
                        skipped_count += 1

            except Exception as e:
                print(f"Error processing entry: {e}")
                continue

        print(f"\nSummary:")
        print(f"Branches created: {created_count}")
        print(f"Branches skipped: {skipped_count}")

    except FileNotFoundError:
        print(f"File not found: {file_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON format: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


def main():
    if len(sys.argv) not in [2, 3]:
        print("Usage: python create_branches_internal.py <json_file_path> [git_repo_path]")
        print(
            "Example: python create_branches_internal.py data/results/baseline-july-07-ratpack-ws/no-replication.json")
        print(
            "Example: python create_branches_internal.py data/results/baseline-july-07-ratpack-ws/no-replication.json /path/to/repo")
        sys.exit(1)

    json_file_path = sys.argv[1]
    repo_path = sys.argv[2] if len(sys.argv) == 3 else None

    # Verify file exists
    if not Path(json_file_path).exists():
        print(f"File does not exist: {json_file_path}")
        sys.exit(1)

    # Verify repository path exists if provided
    if repo_path and not Path(repo_path).exists():
        print(f"Repository path does not exist: {repo_path}")
        sys.exit(1)

    # Check if we're in a git repository (or the specified repo is valid)
    if run_git_command("git rev-parse --git-dir", repo_path) is None:
        if repo_path:
            print(f"Error: {repo_path} is not a git repository")
        else:
            print("Error: Not in a git repository")
        sys.exit(1)

    print(f"Processing JSON file: {json_file_path}")
    if repo_path:
        print(f"Git repository: {repo_path}")
    process_json_file(json_file_path, repo_path)


if __name__ == "__main__":
    main()