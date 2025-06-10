import json
import os
import sys
import argparse
from dotenv import load_dotenv
from git_utils import get_repo_url, get_commit_author_info
from datetime import datetime
from analyze_repo import analyze_repo_with_new_commits, analyze_repo_from_beginning

load_dotenv()

def check_entry_from_jsonl(filepath_to_jsonl, filepath_to_analyzed_repo):
    with open(filepath_to_jsonl, 'r', encoding='utf-8') as file:
        # index = 0
        for line in file:
            # if index >= 2:
                # break
            if line.strip():  # skip empty lines
                loaded_json = json.loads(line)
                if len(loaded_json['refactoring_changes']) <= 1:
                    continue
                res = check_analyzed_entry(loaded_json, filepath_to_analyzed_repo)
                if res is not None:
                    if isinstance(res, dict) and "status" in res:
                        if res["status"] == "already_exists":
                            print(f"Skipped: {res['message']}")
                        elif res["status"] == "repo_not_found":
                            print(f"Error: {res['message']}")
                    else:
                        if res["project_already_analyzed"]:
                            analyze_repo_with_new_commits(res, filepath_to_analyzed_repo)
                        else:
                            analyze_repo_from_beginning(res, filepath_to_analyzed_repo)
            # index += 1


def check_analyzed_entry(json_data, filepath_to_analyzed_repo):
    analyzed_data = None

    projects_base_path = os.getenv('PROJECTS_BASE_PATH')
    if projects_base_path and json_data.get("project"):
        local_repo_path = os.path.join(projects_base_path, json_data["project"])
    else:
        local_repo_path = json_data.get("repo_path", "")
    
    remote_repo_url = get_repo_url(local_repo_path)

    with open(filepath_to_analyzed_repo, 'r', encoding='utf-8') as file:
        analyzed_data = json.load(file)
        for entry in analyzed_data:
            for developer in entry["mail_sent_to_developer"]:
                if developer["v2_hash"] == json_data["v2_hash"] or developer["developer_email"] == get_commit_author_info(json_data["v2_hash"], local_repo_path)[1]:
                    return {"status": "already_exists", "message": "Developer already processed"}

    project_already_analyzed = False # if the project is already analyzed, we need to append the developer info to the existing entry and send mail to the developer
    target_entry = None
    for entry in analyzed_data:
        if entry["project"] == json_data["project"]:
            project_already_analyzed = True
            target_entry = entry
            break
    
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
        "developer_email": developer_email
    }

    developer_info = {
        "developer_name": developer_name,
        "developer_email": developer_email,
        "mail_sent_time": "x",
        "v2_hash": json_data["v2_hash"]
    }
    
    if project_already_analyzed:
        target_entry["mail_sent_to_developer"].append(developer_info)
        return_data["project_already_analyzed"] = True
        return_data["processed_project_info"] = target_entry
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check entries from JSONL file and analyze repositories")
    parser.add_argument("jsonl_file", help="Path to the JSONL file to process")
    parser.add_argument("analyzed_repo_file", help="Path to the analyzed repository JSON file")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.jsonl_file):
        print(f"Error: JSONL file '{args.jsonl_file}' not found.")
        sys.exit(1)
    
    if not os.path.exists(args.analyzed_repo_file):
        print(f"Error: Analyzed repo file '{args.analyzed_repo_file}' not found.")
        sys.exit(1)
    
    check_entry_from_jsonl(args.jsonl_file, args.analyzed_repo_file)

    # python check_entry_from_jsonl.py temp_mekhq.jsonl analyzed_repo.json
    # python check_entry_from_jsonl.py temp_quarkus.jsonl analyzed_repo.json
    # python check_entry_from_jsonl.py temp_flink.jsonl analyzed_repo.json
    # python check_entry_from_jsonl.py temp_graal.jsonl analyzed_repo.json
    # python check_entry_from_jsonl.py temp_spring-boot.jsonl analyzed_repo.json
    # python check_entry_from_jsonl.py temp_spring-framework.jsonl analyzed_repo.json
    # python check_entry_from_jsonl.py temp_camunda.jsonl analyzed_repo.json
    # python check_entry_from_jsonl.py temp_jans.jsonl analyzed_repo.json