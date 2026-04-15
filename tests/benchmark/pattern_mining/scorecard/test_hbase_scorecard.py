"""
Integration tests: every check in the HBase scorecard must pass on the golden commit.

Commit: 07e0a30efa332ab451e5f5729dd8257eced82c4d
Message: HBASE-17491 Remove all setters from HTable interface and
         introduce a TableBuilder to build Table instance

Prerequisites
-------------
* ``PROJECTS_BASE_PATH`` env var must point to the directory that contains
  a checkout of the hbase repository (e.g. /home/user/projects, with
  hbase/ inside it).
* RefactoringMiner must be on PATH (used by refactoring_miner checks).
"""

import os
import re
from pathlib import Path
from typing import List, Tuple

import pytest

from refagent.benchmark.design_patterns.scorecard.schema import (
    BaseScorecardCheck,
    CandidateScorecard,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COMMIT_HASH = "07e0a30efa332ab451e5f5729dd8257eced82c4d"
SCORECARD_RESOURCE = Path(__file__).parent / "resources" / "hbase_scorecard.json"


# ---------------------------------------------------------------------------
# ID generation — called at collection time to name each parametrized case
# ---------------------------------------------------------------------------

def _sanitize(s: str, max_len: int = 28) -> str:
    """Replace non-alphanumeric chars and truncate for readable pytest IDs."""
    return re.sub(r"[^a-zA-Z0-9]", "_", s).strip("_")[:max_len]


def _make_check_id(check: BaseScorecardCheck, index: int) -> str:
    parts = [f"{index:02d}", check.type]

    if hasattr(check, "target_class"):
        parts.append(_sanitize(check.target_class))

    if check.type == "file_presence":
        parts.append(_sanitize(check.file_regex))
        parts.append(check.expected_state)
    elif check.type == "refactoring_miner":
        parts.append(_sanitize(check.operation_type))
    elif check.type == "implements_interface":
        parts.append(_sanitize(check.interface_regex))
    elif check.type == "has_constructor_visibility":
        parts.append(check.visibility.replace("-", "_"))
    elif check.type == "has_field":
        parts.append(_sanitize(check.field_name_regex))
    elif check.type == "has_method":
        parts.append(_sanitize(check.method_name_regex))
    elif check.type == "instantiates_class":
        parts.append(_sanitize(check.instantiated_class_regex))

    if not check.expected:
        parts.append("NOT")

    return "__".join(parts)


def _build_params() -> List[Tuple[BaseScorecardCheck, str]]:
    scorecard = CandidateScorecard.from_json_string(SCORECARD_RESOURCE.read_text())
    return [
        (check, _make_check_id(check, i))
        for i, check in enumerate(scorecard.checks)
    ]


_PARAMS = _build_params()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def hbase_repo_path() -> Path:
    base = os.environ.get("PROJECTS_BASE_PATH")
    if not base:
        pytest.skip("PROJECTS_BASE_PATH environment variable is not set.")
        
    path = Path(base) / "hbase"
    if not path.is_dir():
        pytest.skip(f"HBase repository not found at: {path}")
        
    return path


@pytest.fixture(scope="module")
def rm_refactorings(hbase_repo_path: Path) -> list:
    """
    Runs RefactoringMiner once for the whole module.  All refactoring_miner
    checks share this result — avoids spawning a separate RM process per check.
    Non-RM checks receive it too but simply ignore it.
    """
    from refagent.utils.refminer_utils import default_runner

    if not default_runner.refminer_path or not os.path.exists(default_runner.refminer_path):
        # We don't skip the whole suite because other checks (AST, File) can still run
        return []

    return default_runner.run(
        project_path=str(hbase_repo_path),
        commit_hash=COMMIT_HASH,
    )


# ---------------------------------------------------------------------------
# Parametrized test — one case per check (60 total)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "check,check_id",
    _PARAMS,
    ids=[check_id for _, check_id in _PARAMS],
)
def test_check_passes(
    check: BaseScorecardCheck,
    check_id: str,
    hbase_repo_path: Path,
    rm_refactorings: list,
) -> None:
    """
    Asserts that check.check() returns True on the golden HBase commit.

    For checks with ``expected=False`` (e.g. asserting a public constructor was
    REMOVED), the base-class ``check()`` already applies the inversion, so the
    assertion is always ``result is True``.
    """
    from refagent.benchmark.design_patterns.scorecard.ast_utils import HAS_TREE_SITTER
    from refagent.benchmark.design_patterns.scorecard.checks.ast_base import ASTCheckBase
    
    if isinstance(check, ASTCheckBase) and not HAS_TREE_SITTER:
        pytest.fail("tree-sitter or tree-sitter-java not installed.")
        
    if check.type == "refactoring_miner" and not rm_refactorings:
        pytest.fail("RefactoringMiner results not available (check REFMINER_PATH).")

    result = check.check(COMMIT_HASH, hbase_repo_path, rm_refactorings)

    assert result is True, (
        f"\nCheck FAILED: {check_id}"
        f"\n  type     : {check.type}"
        f"\n  expected : {check.expected}"
        f"\n  details  : {check.model_dump_json(indent=2)}"
    )
