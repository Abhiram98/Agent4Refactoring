import os
import json
from pathlib import Path
import pytest
from langchain_openai import ChatOpenAI

import refagent
from benchmark.design_patterns.pattern_first.mine_from_pattern import _from_output_record
from refagent.benchmark.design_patterns.scorecard.synthesis.create_lenient_scorecard import LenientScoreCardCreator

@pytest.fixture
def projects_base_path():
    """Returns the base path for cloned repositories."""
    base = os.getenv("PROJECTS_BASE_PATH")
    if not base:
        raise RuntimeError("PROJECTS_BASE_PATH environment variable not set")
    return Path(base)

def test_synthesize_lenient_scorecard(projects_base_path):
    """
    Test synthesizing the resilient/goal-oriented scorecard for Candidate dc6ddb40847ae26f (HBase TableBuilder).
    """
    project_name = "hbase"
    candidate_id = "dc6ddb40847ae26f"
    repo_path = projects_base_path / project_name
    
    if not repo_path.exists():
        pytest.skip(f"Repo not found at {repo_path}")

    # Load dataset to get birth_info and greenfield verdict for the candidate
    dataset_path = refagent.data_folder / "design_patterns/aggregated_candidates.json"
    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)
        
    candidate_data = next((c for c in dataset if c["id"] == candidate_id), None)
    assert candidate_data is not None, f"Candidate {candidate_id} not found in dataset."
    
    # Reconstruct BirthInfo mapping (Assuming GreenfieldVerdict is properly serialized in 'greenfield' key)
    # The dictionary structure might need explicit reconstruction depending on the Pydantic model
    path, birth_info, verdict = _from_output_record(candidate_data)

    # Initialize Creator
    llm = ChatOpenAI(model="gpt-5-mini", temperature=1)
    creator = LenientScoreCardCreator(repo_path=repo_path, llm=llm)
    
    # Synthesize Scorecard
    scorecard = creator.create_scorecard(
        candidate_id=candidate_id,
        birth_info=birth_info,
        verdict=verdict
    )
    
    # Verify Checks were generated
    assert len(scorecard.checks) > 0, "No checks were generated for the lenient scorecard."
    
    print("\n--- Synthesized Lenient Scorecard ---")
    for check in scorecard.checks:
        print(f"[{check.type}] Weight: {check.weight} Expected: {check.expected}")
        if hasattr(check, "has_methods"):
            print(f"  Methods: {check.has_methods}")
        if hasattr(check, "forbidden_methods"):
            print(f"  Forbidden Methods: {check.forbidden_methods}")
        if hasattr(check, "invoked_method_regex"):
            print(f"  Invoked Method: {check.invoked_method_regex}")
            
    # Serialize to ensure it can be dumped to JSON
    json_output = scorecard.model_dump_json(indent=2)
    assert len(json_output) > 0
