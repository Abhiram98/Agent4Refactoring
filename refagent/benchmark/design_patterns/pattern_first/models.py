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

import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Any

from pydantic import BaseModel, Field

from refagent.benchmark.design_patterns.models import GoFPattern


# ---------------------------------------------------------------------------
# Infrastructure / Context
# ---------------------------------------------------------------------------

class PatternCache:
    """
    Encapsulates the LLM validation cache to centralize cache key generation
    and lookup logic.
    """
    def __init__(self, data: Optional[dict[str, Any]] = None) -> None:
        self._data = data if data is not None else {}

    def get_key(self, model_name: str, pattern: GoFPattern | str, file_path: str) -> str:
        """Centralized cache key format: model:pattern:file_path"""
        if isinstance(pattern, GoFPattern):
            return f"{model_name}:{pattern.value}:{file_path}"
        elif isinstance(pattern, str):
            return f"{model_name}:{pattern}:{file_path}"
        else:
            raise ValueError(f"Invalid pattern type: {type(pattern)}")

    def get_release_key(self, model_name: str, commit_sha: str) -> str:
        """Cache key format for greenfield release checks: model:release:commit_sha"""
        return f"{model_name}:release:{commit_sha}"

    def get_diff_key(self, model_name: str, pattern: GoFPattern | str, commit_sha: str, file_path: str) -> str:
        """Cache key format for greenfield diff checks: model:diff:pattern:commit_sha:file_path"""
        pattern_str = pattern.value if isinstance(pattern, GoFPattern) else str(pattern)
        return f"{model_name}:diff:{pattern_str}:{commit_sha}:{file_path}"

    def get(self, key: str) -> Optional[dict[str, Any]]:
        return self._data.get(key)

    def set(self, key: str, value: dict[str, Any]) -> None:
        self._data[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def to_dict(self) -> dict[str, Any]:
        return self._data

    def __len__(self) -> int:
        return len(self._data)


class MiningContext(BaseModel):
    """
    Shared configuration and state for the pattern-first mining pipeline.
    Passed as a field to detectors, finders, and filters.
    """
    repo_path: Path
    cache: PatternCache
    cache_path: Path
    model_name: str = "gpt-5-mini"
    max_new_patterns: int = 10

    class Config:
        arbitrary_types_allowed = True
        use_enum_values = True

    def save_cache(self) -> None:
        with open(self.cache_path, "w") as f:
            json.dump(self.cache.to_dict(), f, indent=2)


# ---------------------------------------------------------------------------
# Phase 1 output
# ---------------------------------------------------------------------------

class DetectionSource(str, Enum):
    NAME_HEURISTIC  = "name_heuristic"   # class/file name matched a keyword
    LLM_VALIDATION  = "llm_validation"   # LLM confirmed the pattern
    DPDF_SEED       = "dpdf_seed"         # came directly from dpdf_dataset.json


class PatternInstance(BaseModel):
    """A pattern class detected in the current HEAD of a repository."""
    file_path: str          = Field(..., description="Relative path from repo root (e.g. src/main/.../MyBuilder.java)")
    class_name: str         = Field(..., description="Simple class name")
    pattern: GoFPattern     = Field(..., description="Suspected GoF pattern")
    detection_source: DetectionSource
    confidence: float       = Field(1.0, ge=0.0, le=1.0, description="Detection confidence (1.0 for dpdf_seed)")
    reasoning: Optional[str] = Field(None, description="LLM's reasoning for detection")

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

    # LLM Filtering
    llm_is_refactoring: Optional[bool] = Field(
        None,
        description="Result of the LLM diff analysis",
    )
    llm_reasoning: Optional[str] = Field(
        None,
        description="LLM's explanation for its decision",
    )
    is_release_commit: Optional[bool] = Field(
        None,
        description="True if the LLM identified this as a release/version-bump commit",
    )
    too_many_added_files: Optional[bool] = Field(
        None,
        description="True if the commit exceeded the added-files threshold (e.g. 100)",
    )

    # Final verdict
    is_likely_refactoring: bool = False
    rejection_reasons: list[str] = Field(default_factory=list)
    evidence_notes: list[str]    = Field(default_factory=list)
