import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from datetime import datetime, timezone
from refagent.benchmark.design_patterns.pattern_first.greenfield_filter import GreenfieldFilter, LLMFilter
from refagent.benchmark.design_patterns.pattern_first.models import BirthInfo, PatternInstance, DetectionSource, GoFPattern

@pytest.fixture
def mock_repo():
    repo = MagicMock()
    return repo

@pytest.fixture
def birth_info():
    return BirthInfo(
        pattern_instance=PatternInstance(
            file_path="src/MyBuilder.java",
            class_name="MyBuilder",
            pattern=GoFPattern.BUILDER,
            detection_source=DetectionSource.STRUCTURAL,
            confidence=1.0
        ),
        birth_commit_sha="abcdef123",
        birth_commit_date=datetime(2023, 1, 1, tzinfo=timezone.utc),
        birth_commit_message="Add MyBuilder",
        parent_sha="parent123",
        is_initial_repo_commit=False,
        original_file_path="src/MyBuilder.java"
    )

@patch("git.Repo")
def test_evaluate_heuistic_fail(mock_git_repo, birth_info):
    repo_path = Path("/tmp/repo")
    gf = GreenfieldFilter(repo_path=repo_path)
    
    # Mock signals to fail
    gf._signal_3a = MagicMock(return_value=MagicMock(is_likely_refactoring=False, evidence_notes=[], rejection_reasons=["3A fail"]))
    gf._signal_3b = MagicMock(return_value=MagicMock(is_likely_refactoring=False, evidence_notes=[], rejection_reasons=["3B fail"]))
    
    verdict = gf.evaluate(birth_info)
    
    assert verdict.is_likely_refactoring is False
    assert "Skip LLM: Heuristics 3A and 3B both fail" in verdict.rejection_reasons

@patch("git.Repo")
def test_evaluate_static_fail(mock_git_repo, birth_info):
    repo_path = Path("/tmp/repo")
    gf = GreenfieldFilter(repo_path=repo_path)
    
    # Mock signals to pass
    gf._signal_3a = MagicMock(return_value=MagicMock(is_likely_refactoring=True, evidence_notes=["3A pass"], rejection_reasons=[]))
    gf._signal_3b = MagicMock(return_value=MagicMock(is_likely_refactoring=False, evidence_notes=[], rejection_reasons=["3B fail"]))
    
    # Mock static filter to fail (> 100 files)
    gf._get_added_files_count = MagicMock(return_value=150)
    
    verdict = gf.evaluate(birth_info)
    
    assert verdict.is_likely_refactoring is False
    assert verdict.too_many_added_files is True
    assert "Skip LLM: Too many files added (150 > 100)" in verdict.rejection_reasons

@patch("git.Repo")
def test_evaluate_llm_release_fail(mock_git_repo, birth_info):
    repo_path = Path("/tmp/repo")
    mock_llm = MagicMock(spec=LLMFilter)
    mock_llm.is_release_commit.return_value = True
    
    gf = GreenfieldFilter(repo_path=repo_path, llm_filter=mock_llm)
    
    # Mock signals to pass
    gf._signal_3a = MagicMock(return_value=MagicMock(is_likely_refactoring=True, evidence_notes=["3A pass"], rejection_reasons=[]))
    gf._signal_3b = MagicMock(return_value=MagicMock(is_likely_refactoring=False, evidence_notes=[], rejection_reasons=["3B fail"]))
    gf._get_added_files_count = MagicMock(return_value=10)
    
    verdict = gf.evaluate(birth_info)
    
    assert verdict.is_likely_refactoring is False
    assert verdict.is_release_commit is True
    assert "Skip LLM Diff: LLM identified this as a release/bulk commit" in verdict.rejection_reasons

@patch("git.Repo")
def test_evaluate_llm_diff_success(mock_git_repo, birth_info):
    repo_path = Path("/tmp/repo")
    mock_llm = MagicMock(spec=LLMFilter)
    mock_llm.is_release_commit.return_value = False
    mock_llm.analyze_diff.return_value = (True, "Clearly moving logic from old class to new pattern.")
    
    gf = GreenfieldFilter(repo_path=repo_path, llm_filter=mock_llm)
    
    # Mock signals to pass
    gf._signal_3a = MagicMock(return_value=MagicMock(is_likely_refactoring=True, evidence_notes=["3A pass"], rejection_reasons=[]))
    gf._signal_3b = MagicMock(return_value=MagicMock(is_likely_refactoring=False, evidence_notes=[], rejection_reasons=["3B fail"]))
    gf._get_added_files_count = MagicMock(return_value=10)
    gf._get_full_diff = MagicMock(return_value="some diff")
    
    verdict = gf.evaluate(birth_info)
    
    assert verdict.is_likely_refactoring is True
    assert verdict.llm_is_refactoring is True
    assert "LLM ✓ Refactoring confirmed" in verdict.evidence_notes[1]
