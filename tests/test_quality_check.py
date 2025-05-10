import json
import os
import time
import pytest
from pathlib import Path
import refagent.utils.project_manager as pm
import refagent.utils.intellij_server as ij
import langsmith as ls
from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel
from grazie_langchain_utils.language_models.grazie import ChatGrazie
from grazie.api.client.endpoints import GrazieApiGatewayUrls
from grazie.api.client.gateway import AuthType
from pydantic.v1 import SecretStr
from refagent.agents.refactrix.quality_check import QualityCheck, IntentAlignment, OverallAssessment

from dotenv import load_dotenv
load_dotenv()


def create_model() -> BaseChatModel:
    """Create a language model for testing."""
    # Use environment variable to determine which model to use
    model_type = os.getenv("TEST_MODEL_TYPE", "grazie")
    
    if model_type == "grazie":
        return ChatGrazie(grazie_jwt_token=SecretStr(os.getenv("GRAZIE_JWT_TOKEN")),
                          client_auth_type=AuthType.APPLICATION,
                          client_url=GrazieApiGatewayUrls.STAGING,
                          profile="gpt-4o",
                          client_agent_name='quality-check-test',
                          client_agent_version='0.1',
                          temperature=0.3)
    else:
        # Fall back to OpenAI
        return ChatOpenAI(model="gpt-4o", temperature=0.3)


def get_commit_hash_from_results(results_file_path, target_id=3):
    """Extract a commit hash from the results.json file for the specified id."""
    with open(results_file_path, 'r') as file:
        results = json.load(file)
        for item in results:
            if isinstance(item, dict) and item.get('id') == target_id and item.get('response') and item['response'].get('commit_hash'):
                return item['response']['commit_hash']
    raise ValueError(f"No commit hash found for id {target_id} in results file")


def get_v1_hash_from_benchmark(benchmark_file_path, target_id=3):
    """Extract v1_hash and improve_commit_message from the benchmark file"""
    with open(benchmark_file_path, 'r') as file:
        benchmark_data = json.load(file)
        # Find the entry with the specified ID
        target_entry = next((item for item in benchmark_data if isinstance(item, dict) and item.get('id') == target_id), None)
        if not target_entry:
            raise ValueError(f"No entry found for id={target_id} in benchmark file")
        
        v1_hash = target_entry.get('v1_hash')
        improved_commit_message = target_entry.get('improved_commit_message')
        starting_file = target_entry.get('starting_file')
        
        if not v1_hash:
            raise ValueError(f"No v1_hash found for id={target_id} in benchmark file")
        
        return v1_hash, improved_commit_message, starting_file


def test_quality_check():
    """
    Test if the quality check correctly analyzes refactoring intent compliance.
    """
    with ls.trace(name="test_quality_check", tags=["test"], project_name="code-intent") as tracer:
        # Set up paths and IDs
        project_root = Path(__file__).parent.parent
        results_file_path = project_root / "data/results/baseline-2025-04-28/results.json"
        benchmark_file_path = project_root / "data/ref_miner/benchmark_lite_v0.2.json"
        
        # Use ID 3 by default or allow specifying via environment variable
        target_id = 3
        project_name = "flink"
        
        # Get both commit hashes
        results_commit_hash = get_commit_hash_from_results(results_file_path, target_id=target_id)
        v1_hash, improved_commit_message, starting_file = get_v1_hash_from_benchmark(benchmark_file_path, target_id=target_id)
        
        print(f"Results Commit Hash: {results_commit_hash}")
        print(f"V1 Hash: {v1_hash}")
        print(f"Improved Commit Message: {improved_commit_message}")
        
        # Initialize IntelliJ server and project
        intellij_server = ij.IntellijServer(server_url="http://localhost:8082")
        project = pm.EvalProject(project_name)
        
        # Get original code by checking out the v1 hash
        intellij_server.reset_project_reload_counters()
        project.checkout(v1_hash, force=True)
        intellij_server.open_project(project_path=project.get_project_path())
        intellij_server.reload_project()
        time.sleep(10)  # Wait for project to reload
        print(f"Reloaded project to original version")
        intellij_server.open_file(Path(starting_file))
        time.sleep(5)  # Wait for file to open
        source_code_before_refactoring = intellij_server.call_tool_get("get_source_code")
        
        # Get refactored code by checking out the results commit hash
        intellij_server.reset_project_reload_counters()
        project.checkout(results_commit_hash, force=True)
        intellij_server.reload_project()
        time.sleep(10)  # Wait for project to reload
        print(f"Reloaded project to refactored version")
        intellij_server.open_file(Path(starting_file))
        time.sleep(5)  # Wait for file to open
        source_code_after_refactoring = intellij_server.call_tool_get("get_source_code")
        
        # Create language model
        model = create_model()
        
        # Create quality check component with source code
        quality_checker = QualityCheck(
            model=model,
            ide_server=intellij_server,
            intent=improved_commit_message,
            _original_code=source_code_before_refactoring,
            _refactored_code=source_code_after_refactoring
        )
        
        # Run quality check
        quality_check_result = quality_checker.compile_and_run()
        print(f"Pass? {quality_check_result}")


if __name__ == "__main__":
    test_quality_check() 