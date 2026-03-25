import os
import csv
import json
import urllib.request
import time

SPLIT_FILES_DIR = "split_files"
REPO_STATE_FILE = "repository_state.csv"
OUTPUT_FILE = "project_metadata.csv"

def get_project_names():
    projects = []
    for f in os.listdir(SPLIT_FILES_DIR):
        if f.endswith(".json"):
            projects.append(f[:-5])
    return projects

def get_urls(projects):
    project_urls = {}
    with open(REPO_STATE_FILE, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter='\t')
        for row in reader:
            if not row:
                continue
            url = row[0]
            # url is like git://github.com/owner/repo.git
            repo_name = url.split('/')[-1]
            if repo_name.endswith('.git'):
                repo_name = repo_name[:-4]
            # we need to do case insensitive match just in case
            for p in projects:
                if p.lower() == repo_name.lower():
                    project_urls[p] = url
    return project_urls

def get_stars(url):
    # url is git://github.com/owner/repo.git
    parts = url.replace('git://github.com/', '').replace('.git', '').split('/')
    if len(parts) != 2:
        return 0
    owner, repo = parts
    api_url = f"https://api.github.com/repos/{owner}/{repo}"
    
    req = urllib.request.Request(api_url)
    
    # Check if GH_TOKEN from .env or environment is available
    token = os.environ.get("GH_TOKEN")
    if not token:
        env_path = "/Users/abhiram/Documents/TBE/RefactoringAgentProject/Agent4Refactoring/.env"
        if os.path.exists(env_path):
            with open(env_path, 'r') as env_f:
                for line in env_f:
                    if line.startswith("GH_TOKEN="):
                        token = line.split('=', 1)[1].strip().strip("'").strip('"')
                        break
    if token:
        # print first few chars for debugging to ensure clean parse
        # print("Using token: " + token[:10] + "...")
        req.add_header("Authorization", f"Bearer {token}")
        
    try:
        response = urllib.request.urlopen(req)
        data = json.loads(response.read().decode('utf-8'))
        return data.get('stargazers_count', 0)
    except Exception as e:
        print(f"Error fetching {api_url}: {e}")
        return 0

def main():
    projects = get_project_names()
    project_urls = get_urls(projects)
    
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Project Name", "URL", "Stars"])
        
        for project in projects:
            url = project_urls.get(project)
            stars = 0
            if url:
                stars = get_stars(url)
                print(f"Fetched {project}: {stars} stars")
                time.sleep(0.5) # simple rate limit avoidance if unauthenticated
            else:
                print(f"URL not found for {project}")
            writer.writerow([project, url, stars])

if __name__ == "__main__":
    main()
