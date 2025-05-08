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
from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel
from refagent.agents.refactrix.fix_planning import FixPlanningComponent
from grazie_langchain_utils.language_models.grazie import ChatGrazie
from grazie.api.client.endpoints import GrazieApiGatewayUrls
from grazie.api.client.gateway import AuthType
from pydantic.v1 import SecretStr

from dotenv import load_dotenv
load_dotenv()

def create_model() -> BaseChatModel:
    return ChatGrazie(grazie_jwt_token=SecretStr(os.getenv("GRAZIE_JWT_TOKEN")),
                      client_auth_type=AuthType.APPLICATION,
                      client_url=GrazieApiGatewayUrls.STAGING,
                      profile="gpt-4o",
                      client_agent_name='fix-agent',
                      client_agent_version='0.1',
                      temperature=0.3)

def get_commit_hash_from_results(results_file_path):
    """Extract a commit hash from the results.json file for id 3."""
    with open(results_file_path, 'r') as file:
        results = json.load(file)
        for item in results:
            if isinstance(item, dict) and item.get('id') == 3 and item.get('response') and item['response'].get('commit_hash'):
                return item['response']['commit_hash']
    raise ValueError("No commit hash found for id 3 in results file")

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
        
        # Get all unique a_filename entries while maintaining order
        files_to_inspect = []
        seen_files = set()
        for change in target_entry['response']['changes']:
            if 'a_filename' in change and change['a_filename'] and change['a_filename'] not in seen_files:
                files_to_inspect.append(change['a_filename'])
                seen_files.add(change['a_filename'])
        
        # print(f"Files to inspect: {files_to_inspect}")
    
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
        
        # Create the language model
        model = create_model()
        
        # Process each file
        for file_path in files_to_inspect:
            print(f"\nProcessing file: {file_path}")
            intellij_server.open_file(Path(file_path))
            time.sleep(5)  # Give IDE time to open the file
            
            # Run code inspection
            response = requests.post("http://localhost:8082/run_code_inspection", json={})
            assert response.status_code == 200, f"API call failed with status code {response.status_code} for file {file_path}"
            
            try:
                issues = response.json()
                if not isinstance(issues, list):
                    issues = [issues]
                
                if not issues:
                    print(f"No issues found in {file_path}")
                    continue
                
                # Get the current source code (opened file in IDE)
                source_code = intellij_server.call_tool_get("get_source_code")
                
                # Process each issue
                for issue in issues:
                    print(f"\nFixing issue in {file_path}:")
                    print(f"Line {issue.get('lineNum')}: {issue.get('problem')}")
                    
                    # Create a detailed issue description
                    issue_description = issue.get('problem')
                    
                    # Create and run the fix planning component
                    fix_planner = FixPlanningComponent(
                        issue_description=issue_description,
                        model=model,
                        source_file_path=str(file_path),
                        source_code=source_code
                    )
                    
                    # Get the fix plan
                    fix_plan = fix_planner.run()
                    
                    # Execute each step in the fix plan
                    for step in fix_plan.steps:
                        print(f"\nExecuting fix step: {step.reason}")
                        print(f"Refactoring type: {step.refactoring_type}")
                        print(f"Execution details: {step.execution_details}")
                
            except json.JSONDecodeError:
                print(f"Failed to parse inspection results for {file_path}")
                continue
            except Exception as e:
                print(f"Error processing {file_path}: {str(e)}")
                traceback.print_exc()
                continue
            
    except Exception as e:
        print(f"Test failed with exception: {str(e)}")
        traceback.print_exc()
        raise

if __name__ == "__main__":
    test_code_inspection_with_commit() 