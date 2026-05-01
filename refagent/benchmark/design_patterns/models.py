"""
models.py
---------
Shared data models for the design-pattern introduction pipeline.
All pipeline stages read/write instances of these models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Design-pattern taxonomy
# ---------------------------------------------------------------------------

class GoFPattern(str, Enum):
    """GoF patterns we want to find introduction commits for."""
    ABSTRACT_FACTORY = "AbstractFactory"
    ADAPTER         = "Adapter"
    BUILDER         = "Builder"
    CHAIN_OF_RESP   = "ChainOfResponsibility"
    COMMAND         = "Command"
    COMPOSITE       = "Composite"
    DECORATOR       = "Decorator"
    FACADE          = "Facade"
    FACTORY_METHOD  = "FactoryMethod"
    FLYWEIGHT       = "Flyweight"
    ITERATOR        = "Iterator"
    MEDIATOR        = "Mediator"
    MEMENTO         = "Memento"
    OBSERVER        = "Observer"
    PROTOTYPE       = "Prototype"
    PROXY           = "Proxy"
    SINGLETON       = "Singleton"
    STATE           = "State"
    STRATEGY        = "Strategy"
    TEMPLATE_METHOD = "TemplateMethod"
    VISITOR         = "Visitor"


# ---------------------------------------------------------------------------
# Repo discovery
# ---------------------------------------------------------------------------

class RepoCandidate(BaseModel):
    """A Java repository that is a candidate for mining."""
    owner: str       = Field(..., description="GitHub owner / org")
    name: str        = Field(..., description="Repository name")
    stars: int       = Field(..., description="Star count at discovery time")
    pushed_at: str   = Field(..., description="ISO timestamp of most-recent push")
    clone_url: str   = Field(..., description="HTTPS clone URL")
    local_path: Optional[Path] = Field(None, description="Local checkout path after cloning")

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


# ---------------------------------------------------------------------------
# Stage 2 – candidate commits
# ---------------------------------------------------------------------------

class SignalSource(str, Enum):
    """Which signal identified this as a candidate."""
    KEYWORD     = "keyword"       # Stage 2A – commit-message grep
    REFMINER    = "refminer"      # Stage 2B – RefactoringMiner atomic ops
    DIFF_HEURISTIC = "diff"       # Stage 2C – file-level diff heuristics (future)


class CommitCandidate(BaseModel):
    """A commit that is a candidate for containing a pattern introduction."""
    repo: RepoCandidate
    commit_sha: str           = Field(..., description="SHA of the candidate commit")
    parent_sha: str           = Field(..., description="SHA of the parent (before-state)")
    commit_message: str       = Field(..., description="Raw commit message")
    signals: list[SignalSource] = Field(default_factory=list, description="Signals that flagged this commit")

    # RefactoringMiner output (populated during Stage 2B)
    refminer_types: list[str] = Field(
        default_factory=list,
        description="RefactoringMiner refactoring type strings found in this commit",
    )

    # Hypothesised pattern(s) at this stage (may be multiple, refined later)
    suspected_patterns: list[GoFPattern] = Field(default_factory=list)

    class Config:
        use_enum_values = True


# ---------------------------------------------------------------------------
# Stage 3 – validated instances
# ---------------------------------------------------------------------------

class ValidationEvidence(BaseModel):
    """Structured evidence supporting (or refuting) a pattern introduction claim."""
    structural_score: int  = Field(0, ge=0, le=3, description="Pattern structure found in after-state")
    genuine_refactoring_score: int = Field(0, ge=0, le=3, description="Pre-existing code was modified, not only new files added")
    messiness_score: int   = Field(0, ge=0, le=2, description="Before-state complexity / code smell indicators")
    commit_message_score: int = Field(0, ge=0, le=1, description="Commit message explicitly describes the pattern")
    refminer_score: int    = Field(0, ge=0, le=1, description="RefactoringMiner corroborates the introduction")

    notes: list[str] = Field(default_factory=list, description="Human-readable evidence notes")

    @property
    def total(self) -> int:
        return (
            self.structural_score
            + self.genuine_refactoring_score
            + self.messiness_score
            + self.commit_message_score
            + self.refminer_score
        )

    @property
    def is_high_confidence(self) -> bool:
        return self.total >= 5

    @property
    def needs_manual_review(self) -> bool:
        return 3 <= self.total < 5


class PatternIntroductionInstance(BaseModel):
    """A validated design-pattern introduction event – the final dataset record."""
    id: Optional[int]           = Field(None, description="Unique dataset ID")
    repo_full_name: str         = Field(..., description="owner/repo")
    clone_url: str              = Field(..., description="Clone URL used")
    pattern: GoFPattern         = Field(..., description="GoF pattern that was introduced")
    commit_sha: str             = Field(..., description="SHA of the introduction commit (after-state)")
    parent_sha: str             = Field(..., description="SHA of the parent commit (before-state)")
    commit_message: str         = Field(..., description="Original commit message")

    # Key files involved (relative paths inside the repo)
    before_files: list[str]     = Field(default_factory=list, description="Files changed in the before-state")
    after_files: list[str]      = Field(default_factory=list, description="Files added/changed in the after-state")

    signals: list[SignalSource] = Field(default_factory=list, description="Detection signals")
    refminer_types: list[str]   = Field(default_factory=list, description="RefactoringMiner types found")
    evidence: ValidationEvidence = Field(default_factory=ValidationEvidence)

    human_validation: bool = Field(False, description="Flag indicating if this instance has been manually verified")

    class Config:
        use_enum_values = True

    def to_json(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
