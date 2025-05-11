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
import tiktoken
import langsmith as ls
from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel
from refagent.agents.refactrix.perform_refactoring import PerformRefactoring
from refagent.agents.refactrix.tools import RefactoringToolProvider
from langchain_core.messages import SystemMessage, HumanMessage
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

def get_commit_hash_from_results(results_file_path, target_id=3):
    """Extract a commit hash from the results.json file for the specified id."""
    with open(results_file_path, 'r') as file:
        results = json.load(file)
        for item in results:
            if isinstance(item, dict) and item.get('id') == target_id and item.get('response') and item['response'].get('commit_hash'):
                return item['response']['commit_hash']
    raise ValueError(f"No commit hash found for id {target_id} in results file")

def get_v1_hash_from_benchmark(benchmark_file_path, target_id=3):
    """Extract v1_hash and improve_commit_message from the benchmark_lite_v0.2.json file"""
    with open(benchmark_file_path, 'r') as file:
        benchmark_data = json.load(file)
        # Find the entry with id=3
        target_entry = next((item for item in benchmark_data if isinstance(item, dict) and item.get('id') == target_id), None)
        if not target_entry:
            raise ValueError(f"No entry found for id={target_id} in benchmark file")
        
        v1_hash = target_entry.get('v1_hash')
        improve_commit_message = target_entry.get('improve_commit_message')
        starting_file = target_entry.get('starting_file')
        
        if not v1_hash:
            raise ValueError(f"No v1_hash found for id={target_id} in benchmark file")
        
        return v1_hash, improve_commit_message, starting_file

def count_tokens(text: str) -> int:
    """Count the number of tokens in a text using tiktoken."""
    encoding = tiktoken.get_encoding("cl100k_base")  # Using OpenAI's encoding
    return len(encoding.encode(text))

def analyze_code_changes(model: BaseChatModel, before_code: str, after_code: str, intent: str) -> str:
    """Analyze how well the code changes meet the intended refactoring goals."""
    with ls.trace(name="analyze_code_changes", tags=["analysis"], project_name="code-intent") as tracer:
        # Count tokens for both versions
        before_tokens = count_tokens(before_code)
        after_tokens = count_tokens(after_code)
        print(f"\nToken counts:")
        print(f"Before refactoring: {before_tokens} tokens")
        print(f"After refactoring: {after_tokens} tokens")

        system_message = SystemMessage(
            "You are an expert code reviewer specializing in refactoring analysis. "
            "Your task is to analyze how well the code changes meet the intended refactoring goals. "
            "Please provide a detailed analysis that includes:\n"
            "1. How well the changes align with the stated intent. (Mark met, partially met, or not met)\n"
            "2. What specific improvements were made. (Mark improvements, no improvements, or negative improvements)\n"
            "3. Whether there are any aspects of the intent that were not addressed. (Mark not addressed, partially addressed, or fully addressed)\n"
            "4. Any potential issues or concerns with the refactoring. (Mark issues, no issues, or negative issues)\n"
            "Be specific and reference the actual code changes in your analysis.\n\n"
            "Please format your response as follows:\n"
            "INTENT ALIGNMENT: [met/partially met/not met]\n"
            "Explanation: [Your detailed explanation]\n\n"
            "IMPROVEMENTS: [improvements/no improvements/negative improvements]\n"
            "Explanation: [Your detailed explanation]\n\n"
            "INTENT COVERAGE: [not addressed/partially addressed/fully addressed]\n"
            "Explanation: [Your detailed explanation]\n\n"
            "ISSUES: [issues/no issues/negative issues]\n"
            "Explanation: [Your detailed explanation]\n\n"
            "OVERALL ASSESSMENT [Pass/Fail]:\n"
            "[Your final assessment of the refactoring]\n"
        )

        # Split into two separate human messages for better visibility
        human_message1 = HumanMessage(
            f"Here is the refactoring intent: {intent}\n\n"
            f"Original code:\n{before_code}"
        )

        human_message2 = HumanMessage(
            f"Refactored code:\n{after_code}\n\n"
            "Please analyze how well the refactoring meets the stated intent."
        )

        response = model.invoke([system_message, human_message1, human_message2])
        return response.content

def test_code_intent():
    with ls.trace(name="test_code_intent_data_id_hallucination_id_3", tags=["test"], project_name="code-intent") as tracer:
        project_root = Path(__file__).parent.parent
        results_file_path = project_root / "data/results/baseline-2025-04-28/results.json"
        benchmark_file_path = project_root / "data/ref_miner/benchmark_lite_v0.2.json"
        
        # Get both commit hashes
        id = 3
        results_commit_hash = get_commit_hash_from_results(results_file_path, target_id=id)
        v1_hash, improve_commit_message, starting_file = get_v1_hash_from_benchmark(benchmark_file_path, target_id=id)
        
        print(f"Results Commit Hash: {results_commit_hash}")
        print(f"V1 Hash: {v1_hash}")
        print(f"Improve Commit Message: {improve_commit_message}")
        
        intellij_server = ij.IntellijServer(server_url="http://localhost:8082")
        project = pm.EvalProject('flink')
        
        intellij_server.reset_project_reload_counters()
        project.checkout(v1_hash, force=True)
            
        intellij_server.open_project(project_path=project.get_project_path())
        intellij_server.reload_project()
        time.sleep(10)
        print(f"Reloaded project")
        intellij_server.open_file(Path(starting_file))
        time.sleep(5)

        source_code_before_refactoring = intellij_server.call_tool_get("get_source_code")

        intellij_server.reset_project_reload_counters()
        project.checkout(results_commit_hash, force=True)
        intellij_server.reload_project()
        time.sleep(10)
        print(f"Reloaded project")
        intellij_server.open_file(Path(starting_file))
        time.sleep(5)

        source_code_after_refactoring = intellij_server.call_tool_get("get_source_code")
        
        # Create the language model
        model = create_model()
        
        # Analyze the code changes against the intent
        analysis = analyze_code_changes(
            model=model,
            before_code=source_code_before_refactoring,
            after_code=source_code_after_refactoring,
            intent=improve_commit_message
        )
        
        print("\n=== Refactoring Analysis ===\n")
        print(analysis)

if __name__ == "__main__":
    test_code_intent() 