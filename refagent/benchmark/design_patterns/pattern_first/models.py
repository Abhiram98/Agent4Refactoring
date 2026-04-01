"""
models.py  –  pattern_first-local data models
-----------------------------------------------
These types flow through the three phases of the pattern-first pipeline:

  PatternInstance  (Phase 1 output)
       ↓
  BirthInfo        (Phase 2 output)
       ↓
  GreenfieldVerdict (Phase 3 output)
       ↓
  PatternIntroductionInstance  (shared, final dataset record)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from refagent.benchmark.design_patterns.models import GoFPattern


# ---------------------------------------------------------------------------
# Phase 1 output
# ---------------------------------------------------------------------------

class DetectionSource(str, Enum):
    NAME_HEURISTIC  = "name_heuristic"   # class/file name matched a keyword
    STRUCTURAL      = "structural"        # regex-based structural check passed
    DPDF_SEED       = "dpdf_seed"         # came directly from dpdf_dataset.json


class PatternInstance(BaseModel):
    """A pattern class detected in the current HEAD of a repository."""
    file_path: str          = Field(..., description="Relative path from repo root (e.g. src/main/.../MyBuilder.java)")
    class_name: str         = Field(..., description="Simple class name")
    pattern: GoFPattern     = Field(..., description="Suspected GoF pattern")
    detection_source: DetectionSource
    confidence: float       = Field(1.0, ge=0.0, le=1.0, description="Detection confidence (1.0 for dpdf_seed)")

    class Config:
        use_enum_values = True


# ---------------------------------------------------------------------------
# Phase 2 output
# ---------------------------------------------------------------------------

class BirthInfo(BaseModel):
    """Introduction commit data for a single PatternInstance."""
    pattern_instance: PatternInstance

    # The commit that first added the pattern file
    birth_commit_sha: str     = Field(..., description="SHA of the commit that first added the pattern file")
    birth_commit_date: datetime
    birth_commit_message: str

    # Parent of the birth commit (= the before-state we want to study)
    parent_sha: Optional[str] = Field(None, description="None only if birth commit is the repo's initial commit")

    # Metadata for the greenfield filter
    is_initial_repo_commit: bool = Field(
        False,
        description="True if the file was added in the very first commit of the repo",
    )
    original_file_path: str  = Field(
        "",
        description="File path at the time of birth (may differ from current path if the file was renamed/moved)",
    )


# ---------------------------------------------------------------------------
# Phase 3 output
# ---------------------------------------------------------------------------

class GreenfieldVerdict(BaseModel):
    """Result of the greenfield filter for a single BirthInfo."""

    # 3A – call-site modification
    modified_preexisting_java_count: int = Field(
        0,
        description="Number of pre-existing .java files MODIFIED (not added) in the birth commit",
    )
    modified_preexisting_files: list[str] = Field(
        default_factory=list,
        description="Paths of those modified pre-existing files",
    )

    # 3B – temporal age
    package_had_preexisting_files: bool = Field(
        False,
        description="True if the same directory already contained .java files before the birth commit",
    )
    preexisting_sibling_count: int = Field(
        0,
        description="Number of .java files in the same directory that existed before the birth commit",
    )
    oldest_sibling_age_days: Optional[int] = Field(
        None,
        description="Age in days of the oldest sibling file relative to the birth commit",
    )

    # Final verdict
    is_likely_refactoring: bool = False
    rejection_reasons: list[str] = Field(default_factory=list)
    evidence_notes: list[str]    = Field(default_factory=list)
