import os
import json
import logging
from pathlib import Path
import pytest

from refagent.benchmark.design_patterns.pattern_first.mine_from_pattern import run_pattern_first_mining
import refagent

logger = logging.getLogger(__name__)

@pytest.fixture
def projects_base_path():
    """Returns the base path for cloned repositories."""
    base = os.getenv("PROJECTS_BASE_PATH")
    if not base:
        raise RuntimeError("PROJECTS_BASE_PATH environment variable not set")
    return Path(base)



def _run_validation_test(project_name: str, file_path: str, projects_base_path: Path):
    """
    Helper to run the pipeline on a single validated instance and assert success.
    """
    repo_path = projects_base_path / project_name
    
    if not repo_path.exists():
        pytest.skip(f"Repo not found at {repo_path}")

    print(f"\n--- Testing Validated Instance: {project_name} -> {file_path} ---")
    
    # Run the full pipeline restricted to this specific file
    results = run_pattern_first_mining(
        repo_paths=[repo_path],
        output_path=refagent.data_folder.joinpath(f"design_patterns/miner/test_validation_{project_name}.json"),
        patterns=None,
        use_heuristic=True,
        filter_greenfield=True,
        use_llm_filter=True,
        file_names=[file_path],
        # Use gpt-5-mini for evaluation as configured in the pipeline
        llm_detector_model="gpt-5-mini",
        llm_filter_model="gpt-5-mini",
        dpdf_dataset_path=None,
        dpdf_project_name=None,
    )
    
    # 1. Verify that the file was actually processed
    assert len(results) > 0, f"Pipeline failed to return any results for {file_path} in {project_name}"
    
    # 2. Verify there is a record for the target file
    record = next((r for r in results if r["pattern_file"] == file_path), None)
    assert record is not None, f"Could not find output record for file: {file_path}"
    
    # 3. Verify the core assertion: it should be recognized as a refactoring
    is_refactoring = record["greenfield"]["is_likely_refactoring"]
    reasons = record["greenfield"].get("rejection_reasons", [])
    
    assert is_refactoring, (
        f"Validated pattern in {file_path} was incorrectly rejected as greenfield.\n"
        f"Rejection Reasons: {reasons}\n"
        f"Evidence Notes: {record['greenfield'].get('evidence_notes', [])}"
    )
    
    print(f"✓ Success: {file_path} correctly identified as refactoring.")


def test_hbase_table_builder(projects_base_path):
    """Test the HBase TableBuilder pattern (HBASE-17491)."""
    _run_validation_test(
        project_name="hbase",
        file_path="hbase-client/src/main/java/org/apache/hadoop/hbase/client/TableBuilder.java",
        projects_base_path=projects_base_path
    )


def test_ant_resource_decorator(projects_base_path):
    """Test the Ant ResourceDecorator pattern."""
    _run_validation_test(
        project_name="ant",
        file_path="src/main/org/apache/tools/ant/types/resources/ResourceDecorator.java",
        projects_base_path=projects_base_path
    )
