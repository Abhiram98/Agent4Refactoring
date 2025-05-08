import json
import os
import time
import pytest
import requests
from pathlib import Path
import git
import refagent.utils.project_manager as pm
import refagent.utils.intellij_server as ij
import refagent.benchmark.load as bm_load
import refagent
import traceback

def get_commit_hash_from_results(results_file_path):
    """Extract a commit hash from the results.json file for id 3."""
    with open(results_file_path, 'r') as file:
        results = json.load(file)
        # Handle the case when results is a list
        if isinstance(results, list):
            for item in results:
                if isinstance(item, dict) and item.get('id') == 3 and item.get('response') and item['response'].get('commit_hash'):
                    return item['response']['commit_hash']
        # Handle the case when results is a dictionary
        elif isinstance(results, dict):
            if results.get('id') == 3 and results.get('response') and results['response'].get('commit_hash'):
                return results['response']['commit_hash']
    raise ValueError("No commit hash found for id 3 in results file")

def wait_for_checkout(project, expected_commit, timeout=300, check_interval=5):
    start_time = time.time()
    while time.time() - start_time < timeout:
        current_commit = project.git_repo.head.commit.hexsha
        if current_commit.startswith(expected_commit):
            return True
        time.sleep(check_interval)
    raise TimeoutError(f"Checkout did not complete within {timeout} seconds")

def test_code_inspection_with_commit():
    # Get the results file and commit hash
    # Get the project root directory (one level up from tests)
    project_root = Path(__file__).parent.parent
    results_file_path = project_root / "data/results/baseline-2025-04-28/results.json"
    commit_hash = get_commit_hash_from_results(results_file_path)
    print(f"Commit hash: {commit_hash}")
    
    # Load the results to get the list of files
    with open(results_file_path, 'r') as file:
        results = json.load(file)
        # Find the entry with id 3
        target_entry = next((item for item in results if item.get('id') == 3), None)
        if not target_entry or 'response' not in target_entry or 'changes' not in target_entry['response']:
            raise ValueError("Could not find changes for id 3 in results file")
        
        # Get all unique a_filename entries
        files_to_inspect = set()
        for change in target_entry['response']['changes']:
            if 'a_filename' in change and change['a_filename']:
                files_to_inspect.add(change['a_filename'])
    
    intellij_server = ij.IntellijServer(server_url="http://localhost:8082")
    project = pm.EvalProject('flink')
    
    try:
        intellij_server.reset_project_reload_counters()
        project.checkout(commit_hash, force=True)
        print(f"Checked out commit: {commit_hash}")
        
        intellij_server.open_project(project_path=project.get_project_path())
        intellij_server.reload_project()
        time.sleep(20)
        print(f"Reloaded project")
        
        # Run code inspection on each file
        for file_path in files_to_inspect:
            print(f"\nRunning code inspection on: {file_path}")
            intellij_server.open_file(Path(file_path))
            time.sleep(5)  # Give IDE time to open the file
            
            response = requests.post("http://localhost:8082/run_code_inspection", json={})
            assert response.status_code == 200, f"API call failed with status code {response.status_code} for file {file_path}"
            
            try:
                inspection_results = response.json()
                print(f"Parsed inspection results for {file_path}:")
                print(f"Type: {type(inspection_results)}")
                print(f"Results: {json.dumps(inspection_results, indent=2)}")
                assert isinstance(inspection_results, (dict, list))
            except json.JSONDecodeError:
                assert response.text
                print(f"Code inspection raw response for {file_path}: {response.text}")
            
    except Exception as e:
        print(f"Test failed with exception: {str(e)}")
        traceback.print_exc()
        raise

if __name__ == "__main__":
    test_code_inspection_with_commit() 