import json
import os
import sys
import argparse
from dotenv import load_dotenv
from git_utils import get_repo_url, get_commit_author_info, git_pull
from datetime import datetime, timedelta
from analyze_repo import analyze_repo_with_new_commits, analyze_repo_from_beginning
import re
from collect_commits import get_commits_since_date, get_commit_date

load_dotenv()


RENAME_TYPES = {
    'Rename Class',
    'Rename Method',
    'Rename Variable',
    'Rename Parameter',
    'Rename Attribute',
    'Rename Package'
}

def get_rename_instance_count(refactoring_changes):
    count = 0
    for refactoring_change in refactoring_changes:
        if refactoring_change['type'] in RENAME_TYPES:
            count += 1
    return count

def check_entry_from_jsonl(filepath_to_jsonl, filepath_to_analyzed_repo, skip_old_commits=False):
    with open(filepath_to_jsonl, 'r', encoding='utf-8') as file:
        run_git_pull = True
        for line in file:
            if line.strip():  # skip empty lines
                loaded_json = json.loads(line)
                print(f"Checking id: {loaded_json['id']} commit: {loaded_json['v2_hash']}")

                # Get repository path
                projects_base_path = os.getenv('PROJECTS_BASE_PATH')
                if projects_base_path and loaded_json.get("project"):
                    local_repo_path = os.path.join(projects_base_path, loaded_json["project"])
                else:
                    local_repo_path = loaded_json.get("repo_path", "")

                # Pull latest changes
                if run_git_pull:
                    git_pull(local_repo_path)
                    run_git_pull = False

                # Skip commits older than one day if skip_old_commits is True
                if skip_old_commits:
                    print(f"skipping commit enabled")
                    commit_date = get_commit_date(local_repo_path, loaded_json['v2_hash'])
                    if commit_date:
                        # Convert both dates to date-only objects for comparison
                        commit_date_only = commit_date.date()
                        two_days_ago = (datetime.now() - timedelta(days=2)).date()  # Changed from one day to two days
                        print(f"commit date: {commit_date_only} and checking against: {two_days_ago}")
                        if commit_date_only >= two_days_ago:  # Changed to > two_days_ago
                            print(f"Processing: Commit {loaded_json['v2_hash']} is within last day (committed on {commit_date_only})")
                        else:
                            print(f"Skipped: Commit {loaded_json['v2_hash']} is older than two (committed on {commit_date_only})")
                            continue
                    else:
                        print(f"Warning: Could not get commit date for {loaded_json['v2_hash']}, processing anyway")

                rename_count = get_rename_instance_count(loaded_json['refactoring_changes'])
                if rename_count <= 2:
                    print(f"Skipped: {loaded_json['project']} has {rename_count} renames (less than or equal to 2)")
                    continue
                res = check_analyzed_entry(loaded_json, filepath_to_analyzed_repo, rename_count)
                if res is not None:
                    if isinstance(res, dict) and "status" in res:
                        if res["status"] == "already_exists":
                            print(f"Skipped: {res['message']}")
                        elif res["status"] == "repo_not_found":
                            print(f"Error: {res['message']}")
                    else:
                        renamed_attributes = get_renamed_attributes(loaded_json)
                        if res["project_already_analyzed"]:
                            analyze_repo_with_new_commits(res, filepath_to_analyzed_repo, renamed_attributes)
                        else:
                            analyze_repo_from_beginning(res, filepath_to_analyzed_repo, renamed_attributes)


def check_analyzed_entry(json_data, filepath_to_analyzed_repo, rename_count):
    
    analyzed_data = None
    new_commits = []

    projects_base_path = os.getenv('PROJECTS_BASE_PATH')
    if projects_base_path and json_data.get("project"):
        local_repo_path = os.path.join(projects_base_path, json_data["project"])
    else:
        local_repo_path = json_data.get("repo_path", "")
    
    remote_repo_url = get_repo_url(local_repo_path)


    project_already_analyzed = False # if the project is already analyzed, we need to append the developer info to the existing entry and send mail to the developer
    target_entry = None
    with open(filepath_to_analyzed_repo, 'r', encoding='utf-8') as file:
        analyzed_data = json.load(file)
        for entry in analyzed_data:
            if entry["project"] == json_data["project"]:
                project_already_analyzed = True
                target_entry = entry
                git_pull(local_repo_path)
                new_commits = get_commits_since_date(local_repo_path, since_date=target_entry["last_analyzed_time"].split(' ')[0])
                break

    # for developer in target_entry["mail_sent_to_developer"]:
    #     if (rename_count <= developer["total_renames_count"]) and (developer["v2_hash"] == json_data["v2_hash"] or developer["developer_email"] == get_commit_author_info(json_data["v2_hash"], local_repo_path)[1]):
    #         return {"status": "already_exists", "message": "Developer already processed and has less or equal renames"}

    
    projects_base_path = os.getenv('PROJECTS_BASE_PATH')
    if projects_base_path and json_data.get("project"):
        local_repo_path = os.path.join(projects_base_path, json_data["project"])
    else:
        local_repo_path = json_data.get("repo_path", "")
    
    remote_repo_url = get_repo_url(local_repo_path)
    
    if remote_repo_url is None:
        existing_projects = set()
        txt_file_path = "project_not_in_local.txt"
        
        try:
            with open(txt_file_path, "r", encoding='utf-8') as txt_file:
                existing_projects = set(line.strip() for line in txt_file if line.strip())
        except FileNotFoundError:
            pass
        
        existing_projects.add(json_data["project"])
        
        with open(txt_file_path, "w", encoding='utf-8') as txt_file:
            for project in sorted(existing_projects):  # Sort for better readability
                txt_file.write(project + "\n")
        
        return {"status": "repo_not_found", "message": f"Repository not found locally: {json_data['project']}"}

    developer_name, developer_email = get_commit_author_info(json_data["v2_hash"], local_repo_path)

    return_data = {
        "json_data_from_jsonl": json_data,
        "local_repo_path": local_repo_path,
        "remote_repo_url": remote_repo_url,
        "developer_name": developer_name,
        "developer_email": developer_email,
        "last_analyzed_time": target_entry["last_analyzed_time"] if target_entry else datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "batch_anlayzed": target_entry["batch_anlayzed"] if target_entry else 0
    }

    developer_info = {
        "developer_name": developer_name,
        "developer_email": developer_email,
        "mail_sent_time": "x",
        "v2_hash": json_data["v2_hash"],
        "total_renames_count": get_rename_instance_count(json_data['refactoring_changes'])
    }
    
    if project_already_analyzed:
        target_entry["mail_sent_to_developer"].append(developer_info)
        return_data["project_already_analyzed"] = True
        return_data["processed_project_info"] = target_entry
        return_data["new_commits"] = new_commits
    else:       
        analyzed_data.append({
            "project": json_data["project"],
            "repo_url": remote_repo_url,
            "last_analyzed_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "batch_anlayzed": 0,
            "total_commits_found": 0,
            "mail_sent_to_developer": [developer_info]
        })
        return_data["project_already_analyzed"] = False
        return_data["processed_project_info"] = analyzed_data[-1]
    
    # Write the updated data back to the file (overwrite, not append)
    with open(filepath_to_analyzed_repo, 'w', encoding='utf-8') as file:
        json.dump(analyzed_data, file, indent=4, ensure_ascii=False)
    return return_data

def get_renamed_attributes(json_data):
    codeElements = set()
    for refactoring_change in json_data['refactoring_changes']:
            codeElementType = refactoring_change['leftSideLocations'][0]['codeElementType']
            old_name = ''
            new_name = ''

            if refactoring_change['type'] == 'Rename Class':
                match = re.search(r"Rename Class .*\.([A-Za-z0-9_]+) renamed to .*\.([A-Za-z0-9_]+)", refactoring_change['description'])
                if match:
                    old_name = match.group(1)
                    new_name = match.group(2)
                
            elif refactoring_change['type'] == 'Rename Method':
                match = re.search(r"Rename Method .*? ([A-Za-z0-9_]+)\(.*?\)\s*:\s*.*? renamed to .*? ([A-Za-z0-9_]+)\(", refactoring_change['description'])
                if match:
                    old_name = match.group(1)
                    new_name = match.group(2)
                
            elif refactoring_change['type'] == 'Rename Variable':
                match = re.search(r"Rename Variable ([A-Za-z0-9_]+) ?: .*? to ([A-Za-z0-9_]+) ?: .*?", refactoring_change['description'])
                if match:
                    old_name = match.group(1)
                    new_name = match.group(2)
            elif refactoring_change['type'] == 'Rename Attribute':
                match = re.search(r"Rename Attribute ([A-Za-z0-9_]+) ?: .*? to ([A-Za-z0-9_]+) ?: .*? in class", refactoring_change['description'])
                if match:
                    old_name = match.group(1)
                    new_name = match.group(2)
            elif refactoring_change['type'] == 'Rename Parameter':    
                match = re.search(r"Rename Parameter ([A-Za-z0-9_]+) ?: .*? to ([A-Za-z0-9_]+) ?: .*? in method", refactoring_change['description'])
                if match:
                    old_name = match.group(1)
                    new_name = match.group(2)
            
            if old_name and new_name:
                codeElements.add((codeElementType.lower().replace('_', ' ').title(), f'{old_name} -> {new_name}'))
    return codeElements

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check entries from JSONL file and analyze repositories")
    parser.add_argument("jsonl_file", help="Path to the JSONL file to process")
    parser.add_argument("analyzed_repo_file", help="Path to the analyzed repository JSON file")
    parser.add_argument("--skip-old-commits", action="store_true", help="Skip commits older than one day")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.jsonl_file):
        print(f"Error: JSONL file '{args.jsonl_file}' not found.")
        sys.exit(1)
    
    if not os.path.exists(args.analyzed_repo_file):
        print(f"Error: Analyzed repo file '{args.analyzed_repo_file}' not found.")
        sys.exit(1)
    
    check_entry_from_jsonl(args.jsonl_file, args.analyzed_repo_file, args.skip_old_commits)

    # Example commands:
    # python check_entry_from_jsonl.py temp_mekhq.jsonl analyzed_repo.json
    # python check_entry_from_jsonl.py temp_mekhq.jsonl analyzed_repo.json --skip-old-commits
    # python check_entry_from_jsonl.py temp_quarkus.jsonl analyzed_repo.json
    # python check_entry_from_jsonl.py temp_flink.jsonl analyzed_repo.json
    # python check_entry_from_jsonl.py temp_graal.jsonl analyzed_repo.json
    # python check_entry_from_jsonl.py temp_spring-boot.jsonl analyzed_repo.json
    # python check_entry_from_jsonl.py temp_spring-framework.jsonl analyzed_repo.json
    # python check_entry_from_jsonl.py temp_camunda.jsonl analyzed_repo.json
    # python check_entry_from_jsonl.py temp_jans.jsonl analyzed_repo.json