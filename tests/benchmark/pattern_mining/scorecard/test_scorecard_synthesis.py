import os
import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock
from langchain_openai import ChatOpenAI

from refagent.benchmark.design_patterns.scorecard.synthesis.create_scorecard import (
    ScoreCardCreator,
    FileCheckList,
    RMCheckList,
    ASTCheckList
)
from refagent.benchmark.design_patterns.scorecard.schema import (
    CandidateScorecard,
    FilePresenceCheck,
    RefactoringMinerCheck,
    HasMethodCheck,
    ImplementsInterfaceCheck
)
from refagent.benchmark.design_patterns.pattern_first.models import BirthInfo, GreenfieldVerdict, PatternInstance, DetectionSource
from refagent.benchmark.design_patterns.models import GoFPattern
from datetime import datetime

@pytest.fixture
def projects_base_path():
    """Returns the base path for cloned repositories."""
    base = os.getenv("PROJECTS_BASE_PATH")
    if not base:
        raise Exception("PROJECTS_BASE_PATH environment variable not set")
    return Path(base)


def test_scorecard_synthesis_hbase(projects_base_path):
    """
    Exercises the scorecard creation logic for the HBase TableBuilder (validated pattern).
    """
    repo_path = projects_base_path / "hbase"
    if not repo_path.exists():
        pytest.fail(f"HBase repo not found at {repo_path}")

    creator = ScoreCardCreator(repo_path, ChatOpenAI(model="gpt-5-mini", temperature=1))
    
    # Data from benchmark_to_pattern.json for entry 1001
    candidate_id = "1001"
    pattern_type = "Builder"
    detection_reasoning = ("The commit introduces a Builder pattern (TableBuilder / TableBuilderBase) but moves existing"
                           " construction and configuration logic into it rather than creating entirely new functionality."
                           " getTable now delegates to getTableBuilder, ConnectionImplementation constructs a TableBuilder "
                           "that builds an HTable, and HTable's previous constructor/configuration fields and setters were"
                           " refactored to read from the builder (with deprecated setters left for backwards compatibility). "
                           "ConnectionConfiguration was extended to expose an rpcTimeout used by the builder. "
                           "These changes reorganize and relocate existing logic into the new pattern — a refactor.")
    commit_hash = "07e0a30efa332ab451e5f5729dd8257eced82c4d"
    parent_hash = "7754a96" # Short SHA from benchmark JSON
    
    inst = PatternInstance(
        file_path="hbase-client/src/main/java/org/apache/hadoop/hbase/client/TableBuilder.java",
        class_name="TableBuilder",
        pattern=GoFPattern("Builder"),
        detection_source=DetectionSource.NAME_HEURISTIC,
        confidence=1.0,
        reasoning=detection_reasoning
    )
    birth_info = BirthInfo(
        pattern_instance=inst,
        birth_commit_sha=commit_hash,
        parent_sha=parent_hash,
        birth_commit_date=datetime.now(),
        birth_commit_message="HBASE-17491 Remove all setters from HTable interface and introduce a TableBuilder to build Table instance",
        is_initial_repo_commit=False,
        original_file_path="hbase-client/src/main/java/org/apache/hadoop/hbase/client/TableBuilder.java"
    )
    verdict = GreenfieldVerdict(
        is_likely_refactoring=True,
        modified_preexisting_java_count=1,
        modified_preexisting_files=[
        "hbase-client/src/main/java/org/apache/hadoop/hbase/client/Connection.java",
        "hbase-client/src/main/java/org/apache/hadoop/hbase/client/ConnectionConfiguration.java",
        "hbase-client/src/main/java/org/apache/hadoop/hbase/client/ConnectionImplementation.java",
        "hbase-client/src/main/java/org/apache/hadoop/hbase/client/HTable.java",
        "hbase-client/src/main/java/org/apache/hadoop/hbase/client/Table.java"
      ],
        package_had_preexisting_files=True,
        preexisting_sibling_count=1,
        llm_is_refactoring=True,
        llm_reasoning="The commit introduces a Builder pattern (TableBuilder / TableBuilderBase) but moves existing construction and configuration logic into it rather than creating entirely new functionality. getTable now delegates to getTableBuilder, ConnectionImplementation constructs a TableBuilder that builds an HTable, and HTable's previous constructor/configuration fields and setters were refactored to read from the builder (with deprecated setters left for backwards compatibility). ConnectionConfiguration was extended to expose an rpcTimeout used by the builder. These changes reorganize and relocate existing logic into the new pattern \u2014 a refactor.",
        is_release_commit=False,
        oldest_sibling_age_days=3531,
        too_many_added_files=None
    )

    print(f"\n--- Synthesizing Scorecard for {pattern_type} in HBase ---")
    scorecard = creator.create_scorecard(
        candidate_id=candidate_id,
        birth_info=birth_info,
        verdict=verdict,
    )

    # Verify the results
    assert isinstance(scorecard, CandidateScorecard)
    assert scorecard.candidate_id == candidate_id
    assert len(scorecard.checks) > 0
    
    # Check for specific types of generated checks
    check_types = [c.type for c in scorecard.checks]
    assert "file_presence" in check_types
    assert "refactoring_miner" in check_types
    assert "has_method" in check_types
    
    print(f"✓ Created scorecard with {len(scorecard.checks)} checks.")

def test_scorecard_synthesis_ant(projects_base_path):
    """
    Exercises the scorecard creation logic for the Ant ResourceDecorator (validated pattern).
    """
    repo_path = projects_base_path / "ant"
    if not repo_path.exists():
        pytest.skip(f"Ant repo not found at {repo_path}")

    creator = ScoreCardCreator(repo_path, ChatOpenAI(model="gpt-5-mini", temperature=1))
    
    # Data from benchmark_to_pattern.json
    candidate_id = "ant-decorator-1"
    pattern_type = "Decorator"
    detection_reasoning = "Extract a common base class for resource decorators"
    commit_hash = "99deca2a7689ef13a6dfa6ad2c30db68e6f3d3e9"
    parent_hash = "b10fa11"

    inst = PatternInstance(
        file_path="dummy/ResourceDecorator.java",
        class_name="ResourceDecorator",
        pattern=GoFPattern("Decorator"),
        detection_source=DetectionSource.NAME_HEURISTIC,
        confidence=1.0,
        reasoning=detection_reasoning
    )
    birth_info = BirthInfo(
        pattern_instance=inst,
        birth_commit_sha=commit_hash,
        parent_sha=parent_hash,
        birth_commit_date=datetime.now(),
        birth_commit_message="dummy message",
        is_initial_repo_commit=False,
        original_file_path="dummy/ResourceDecorator.java"
    )
    verdict = GreenfieldVerdict(
        is_likely_refactoring=True,
        modified_preexisting_java_count=1,
        modified_preexisting_files=["dummy/CallSite.java"],
        package_had_preexisting_files=True,
        preexisting_sibling_count=1,
        llm_is_refactoring=True,
        llm_reasoning="dummy"
    )

    print(f"\n--- Synthesizing Scorecard for {pattern_type} in Ant ---")
    scorecard = creator.create_scorecard(
        candidate_id=candidate_id,
        birth_info=birth_info,
        verdict=verdict,
    )

    assert isinstance(scorecard, CandidateScorecard)
    assert len(scorecard.checks) > 0
    
    print(f"✓ Created scorecard with {len(scorecard.checks)} checks.")
