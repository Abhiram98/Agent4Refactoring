import argparse
import json
import os
from datetime import datetime
from typing import Optional, Type, List, Dict

import refagent.refactoring_types.refactorings as ref
import refagent.utils.project_manager as pm
import refagent.utils.refminer_utils as rminer_utils
from refagent.refactoring_types.refactorings import RefminerOut

CACHE_FILE = "data/ide_refactorings/mining_cache.json"
RESULTS_DIR = "data/ide_refactorings/mining_results"

def load_cache() -> Dict:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"Error decoding cache file {CACHE_FILE}. Starting with empty cache.")
    return {}

def save_cache(cache: Dict):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=4)

def get_refactoring_class(type_name: str) -> Optional[Type[RefminerOut]]:
    # First check the registry
    if type_name in RefminerOut.subclass_registry:
        return RefminerOut.subclass_registry[type_name]
    
    # Fallback to case-insensitive match or direct class name if possible
    for key, cls in RefminerOut.subclass_registry.items():
        if key.lower() == type_name.lower():
            return cls
            
    return None

def run_on_project(project_name: str,
                   refactoring_type_name: str,
                   limit_commits: int):
    project = pm.EvalProject(project_name)
    ref_class = get_refactoring_class(refactoring_type_name)
    
    if not ref_class:
        available_types = list(RefminerOut.subclass_registry.keys())
        print(f"Unknown refactoring type: '{refactoring_type_name}'.")
        print(f"Available types: {available_types}")
        return

    cache = load_cache()
    if project_name not in cache:
        cache[project_name] = {}
    
    project_type_cache = cache[project_name].get(refactoring_type_name, [])
    processed_commits = set(project_type_cache)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    safe_type_name = refactoring_type_name.replace(" ", "_").lower()
    results_file = os.path.join(RESULTS_DIR, f"{project_name}_{safe_type_name}.jsonl")

    # Mining since 2020-01-01
    since_date = "2020-01-01"
    print(f"Starting mining for {project_name} - {refactoring_type_name} since {since_date}...")
    
    try:
        commits = project.git_repo.iter_commits(since=since_date)
    except Exception as e:
        print(f"Error accessing commits for project {project_name}: {e}")
        return

    commits_inspected = 0
    new_commits_processed = 0
    
    # We use a context manager to ensure the file is closed properly
    with open(results_file, "a") as f:
        for commit in commits:
            commits_inspected += 1
            commit_hash = commit.hexsha
            
            if commit_hash in processed_commits:
                continue

            print(f"[{commits_inspected}] Processing commit {commit_hash} ({commit.committed_datetime.strftime('%Y-%m-%d')})")
            
            try:
                refactorings = rminer_utils.default_runner.run(
                    project_path=project.get_project_path(),
                    commit_hash=commit_hash,
                )
                
                filtered = [r for r in refactorings if isinstance(r, ref_class)]
                
                if filtered:
                    print(f"  --> Found {len(filtered)} refactorings")
                    for r in filtered:
                        result_item = {
                            "project": project_name,
                            "commit": commit_hash,
                            "date": commit.committed_datetime.isoformat(),
                            "type": refactoring_type_name,
                            "refactoring": r.dict()
                        }
                        f.write(json.dumps(result_item) + "\n")
                
                processed_commits.add(commit_hash)
                
                # Update cache after each commit (as requested: "do both")
                cache[project_name][refactoring_type_name] = list(processed_commits)
                save_cache(cache)
                
                new_commits_processed += 1
                if new_commits_processed >= limit_commits:
                    print(f"Reached limit of {limit_commits} new commits.")
                    break
                    
            except Exception as e:
                print(f"  !! Error processing commit {commit_hash}: {e}")

    # Final save of the cache (as requested: "do both")
    save_cache(cache)
    print(f"Finished mining run.")
    print(f"Total commits inspected: {commits_inspected}")
    print(f"New commits processed: {new_commits_processed}")
    print(f"Results stored in: {results_file}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Mine a project for specific refactoring types since 2020.")
    parser.add_argument("--project", required=True, help="Name of the project directory.")
    parser.add_argument("--type", required=True, help="Refactoring type (e.g., 'Extract Method', 'Rename Class').")
    parser.add_argument("--limit", type=int, default=500, help="Maximum number of new commits to process in this run.")
    
    args = parser.parse_args()
    run_on_project(args.project, args.type, args.limit)
