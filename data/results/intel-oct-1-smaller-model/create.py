#!/usr/bin/env python3

import json
import os
import subprocess
import sys

# Configuration
PROJECT_NAME = "intellij-community"  # Change this to your project name
PROJECTS_BASE_PATH = os.getenv('PROJECTS_BASE_PATH', '/Users/moul7361/Desktop/AI-Agents/evaluation-projects')


def main():
    if len(sys.argv) != 2:
        print("Usage: python create_branches_from_commits.py <json_file>")
        sys.exit(1)

    json_file = sys.argv[1]
    project_path = os.path.join(PROJECTS_BASE_PATH, PROJECT_NAME)

    # Load JSON data
    with open(json_file, 'r') as f:
        data = json.load(f)

    # Extract commit hashes
    commit_hashes = []
    for item in data:
        # Try different possible fields for commit hashes
        # if 'v1_hash' in item:
        #     commit_hashes.append(item['v1_hash'])
        # if 'v2_hash' in item:
        #     commit_hashes.append(item['v2_hash'])
        # if 'commit_hash' in item:
        #     commit_hashes.append(item['commit_hash'])
        if 'response' in item and 'commit_hash' in item['response']:
            commit_hashes.append(item['response']['commit_hash'])
        if 'response' in item and 'internal_commits' in item['response']:
            for internal_commit in item['response']['internal_commits']:
                print(f"Got internal commit {internal_commit}")
                commit_hashes.append(internal_commit)


    # Remove duplicates
    commit_hashes = list(set(commit_hashes))

    print(f"Found {len(commit_hashes)} commit hashes")
    print(f"Working in project: {project_path}")

    # Create branches
    for i, commit_hash in enumerate(commit_hashes):
        branch_name = f"commit-{commit_hash[:8]}"
        print(f"[{i + 1}/{len(commit_hashes)}] Creating branch {branch_name} from {commit_hash}")

        # Run git command to create branch
        cmd = ['git', 'branch', branch_name, commit_hash]
        result = subprocess.run(cmd, cwd=project_path, capture_output=True, text=True)

        if result.returncode == 0:
            print(f"  ✅ Success")
        else:
            print(f"  ❌ Failed: {result.stderr.strip()}")


if __name__ == '__main__':
    main()