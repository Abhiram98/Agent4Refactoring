import json
import json
import os
import argparse
from analyze_repo import analyze_repo_from_beginning, analyze_repo_from_checkpoint
from dotenv import load_dotenv

load_dotenv()
# Default date filter - set to 2024-01-01 by default to exclude older data
DEFAULT_SINCE_DATE = "2024-01-01"

def get_since_date():
    """
    Get the date filter to use. Can be overridden by environment variable or config.
    Returns the date string in YYYY-MM-DD format.
    """
    # Allow override via environment variable
    env_date = os.environ.get('REFACTORING_SINCE_DATE')
    if env_date:
        print(f"Using date filter from environment variable: {env_date}")
        return env_date
    return DEFAULT_SINCE_DATE


def check_dir_exist(dir):
    """Check if a directory exists"""
    if not os.path.exists(dir):
        return False
    return True

def find_project_and_developer_info(raw_json_data, project_name):
    for item in raw_json_data:
        if item['project'] == project_name:
            return item

    return None

def load_already_analyzed_repos(analyzed_repo_file='analyzed_repo.json'):
    """Load the list of already analyzed repositories from the JSON file"""
    analyzed_repos = set()

    if os.path.exists(analyzed_repo_file):
        try:
            with open(analyzed_repo_file, 'r', encoding='utf-8') as file:
                data = json.load(file)
                for entry in data:
                    if 'project' in entry:
                        analyzed_repos.add(entry['project'])
            print(f"Found {len(analyzed_repos)} already analyzed repositories in {analyzed_repo_file}")
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not read {analyzed_repo_file}: {e}")
    else:
        print(f"No existing {analyzed_repo_file} found - will process all repositories")

    return data, analyzed_repos

def main():
    parser = argparse.ArgumentParser(description="Analyze repositories from JSONL files by cutoff date")
    parser.add_argument("jsonl_files", nargs='+', help="Path(s) to JSONL files to process")
    parser.add_argument("analyzed_repo_file", nargs='?', help="Path to analyzed repo JSON file")

    args = parser.parse_args()

    if args.analyzed_repo_file:
        analyzed_repos_json_data, analyzed_repos_set = load_already_analyzed_repos(args.analyzed_repo_file)
    else:
        analyzed_repos_json_data, analyzed_repos_set = load_already_analyzed_repos()

    for jsonl_file in args.jsonl_files:
        print(f"Processing JSONL file: {jsonl_file}")
        json_data_of_a_repo = []
        with open(jsonl_file, 'r', encoding='utf-8') as file:
            for line in file:
                if line.strip():  # skip empty lines
                    try:
                        loaded_json = json.loads(line)
                        json_data_of_a_repo.append(loaded_json)
                    except Exception as e:
                        print(e)
        project_name = json_data_of_a_repo[0]['project']

        projects_base_path = os.getenv('PROJECTS_BASE_PATH')
        if projects_base_path:
            local_repo_path = os.path.join(projects_base_path, project_name)
        else:
            local_repo_path = loaded_json.get("repo_path", "")

        # 1-> if project is in analyzed json and batch result exist : just get the recent commit and process those batch
        # 2-> if project is in (not in) analyzed json and/or batch result doesn't exist : start from beginning
        # 3-> else: start from beginning

        output_dir_base = f"analysis_result"
        analyzed_repo_info = find_project_and_developer_info(analyzed_repos_json_data, project_name)
        if check_dir_exist(f"output_dir_base/{project_name}") and project_name in analyzed_repos_set:
            analyze_repo_from_checkpoint(analyzed_repo_info, json_data_of_a_repo, local_repo_path, get_since_date(), f"{output_dir_base}/{project_name}")
        else:
            analyze_repo_from_beginning(analyzed_repo_info, json_data_of_a_repo, local_repo_path, get_since_date(), f"{output_dir_base}/{project_name}")

if __name__ == "__main__":
    main()