import os
import csv
import json
import urllib.request
import urllib.error
import time
from datetime import datetime, timezone

INPUT_FILE = "/Users/abhiram/Documents/TBE/RefactoringAgentProject/Agent4Refactoring/data/design_patterns/project_metadata.csv"
OUTPUT_FILE = "/Users/abhiram/Documents/TBE/RefactoringAgentProject/Agent4Refactoring/data/design_patterns/project_metadata_updated.csv"

def get_token():
    token = os.environ.get("GH_TOKEN")
    if not token:
        env_path = "/Users/abhiram/Documents/TBE/RefactoringAgentProject/Agent4Refactoring/.env"
        if os.path.exists(env_path):
            with open(env_path, 'r') as env_f:
                for line in env_f:
                    if line.startswith("GH_TOKEN="):
                        token = line.split('=', 1)[1].strip().strip("'").strip('"')
                        break
    return token

def fetch_json(url, token):
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        response = urllib.request.urlopen(req)
        return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code} for {url}")
        return None
    except Exception as e:
        print(f"Error for {url}: {e}")
        return None

def main():
    token = get_token()
    
    rows = []
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            rows.append(row)
            
    new_fields = ["Last Push", "Archived", "Has POM", "Has Gradle", "Has Build XML", "Recent Commits", "likely_buildable"]
    for field in new_fields:
        if field not in fieldnames:
            fieldnames.append(field)
            
    current_time = datetime(2026, 3, 25, tzinfo=timezone.utc)
    
    # Write header first to output file
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
    
    for i, row in enumerate(rows):
        url = row.get("URL", "")
        if not url or url.strip() == "":
            print(f"Skipping empty URL for {row.get('Project Name')}")
            for field in new_fields:
                row[field] = ""
            row["likely_buildable"] = "False"
            
            with open(OUTPUT_FILE, 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writerow(row)
            continue
            
        parts = url.replace('git://github.com/', '').replace('.git', '').split('/')
        if len(parts) != 2:
            print(f"Invalid URL format: {url}")
            continue
            
        owner, repo = parts
        api_url = f"https://api.github.com/repos/{owner}/{repo}"
        
        print(f"[{i+1}/{len(rows)}] Fetching {owner}/{repo}...")
        repo_data = fetch_json(api_url, token)
        
        has_pom = False
        has_gradle = False
        has_build_xml = False
        last_push = ""
        archived = False
        recent_commits = False
        likely_buildable = False
        
        if repo_data:
            last_push = repo_data.get('pushed_at', '')
            archived = repo_data.get('archived', False)
            default_branch = repo_data.get('default_branch', 'master')
            
            if last_push:
                push_dt = datetime.strptime(last_push, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                days_since_push = (current_time - push_dt).days
                recent_commits = days_since_push <= 365
                
            tree_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}"
            tree_data = fetch_json(tree_url, token)
            if tree_data and 'tree' in tree_data:
                files = [item['path'] for item in tree_data['tree'] if item['type'] == 'blob']
                has_pom = 'pom.xml' in files
                has_gradle = 'build.gradle' in files or 'build.gradle.kts' in files
                has_build_xml = 'build.xml' in files
        else:
            print(f"Repo data not found for {owner}/{repo}")

        row["Last Push"] = last_push
        row["Archived"] = str(archived)
        row["Has POM"] = str(has_pom)
        row["Has Gradle"] = str(has_gradle)
        row["Has Build XML"] = str(has_build_xml)
        row["Recent Commits"] = str(recent_commits)
        
        is_buildable = not archived and recent_commits and (has_pom or has_gradle or has_build_xml)
        row["likely_buildable"] = str(is_buildable)
        
        with open(OUTPUT_FILE, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writerow(row)
            
        time.sleep(0.5)

    print("Overwriting original file...")
    os.rename(OUTPUT_FILE, INPUT_FILE)
    print("Done!")

if __name__ == "__main__":
    main()
