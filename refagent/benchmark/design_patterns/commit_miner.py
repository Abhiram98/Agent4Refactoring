"""
commit_miner.py
---------------
Stage 2 – Identify candidate commits that may introduce a design pattern.

Three independently-runnable signal sources:

  2A  KeywordSignal      – grep commit messages for pattern-related keywords
  2B  RefminerSignal     – run RefactoringMiner and check for structural fingerprints
  2C  DiffHeuristicSignal – (stub) file-level AST diff checks (future work)

Each signal source is a callable that accepts a ``git.Repo`` and a
``RepoCandidate`` and yields ``CommitCandidate`` objects.  They can be
combined with ``MultiSignalMiner``.
"""

from __future__ import annotations

import logging
import re
import subprocess
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import git

import refagent.utils.refminer_utils as refminer_utils
from refagent.benchmark.design_patterns.models import (
    CommitCandidate,
    GoFPattern,
    RepoCandidate,
    SignalSource,
)

logger = logging.getLogger(__name__)

UTC = timezone.utc


# ---------------------------------------------------------------------------
# Pattern → atomic RefactoringMiner types that suggest its introduction
# ---------------------------------------------------------------------------

# A commit must contain AT LEAST ONE of these RefactoringMiner types to be
# flagged by the RefminerSignal for the corresponding pattern.
# Keys are GoFPattern enum values; values are sets of rminer type strings.
PATTERN_REFMINER_FINGERPRINTS: dict[str, set[str]] = {
    GoFPattern.BUILDER: {
        "Extract Class",
        "Extract Interface",
        "Change Method Signature",  # telescoping constructor → builder setters
        "Add Method",
    },
    GoFPattern.STRATEGY: {
        "Extract Interface",
        "Extract Class",
        "Extract Superclass",
        "Move Method",
    },
    GoFPattern.OBSERVER: {
        "Extract Interface",
        "Extract Class",
        "Add Parameter",
        "Move Method",
    },
    GoFPattern.FACTORY_METHOD: {
        "Extract Method",
        "Extract Interface",
        "Move Method",
        "Parameterize Variable",
    },
    GoFPattern.ABSTRACT_FACTORY: {
        "Extract Interface",
        "Extract Class",
        "Extract Superclass",
        "Move Method",
    },
    GoFPattern.DECORATOR: {
        "Extract Class",
        "Extract Interface",
        "Extract Superclass",
        "Move Method",
    },
    GoFPattern.COMMAND: {
        "Extract Class",
        "Extract Interface",
        "Extract Method",
        "Move Method",
    },
    GoFPattern.TEMPLATE_METHOD: {
        "Extract Superclass",
        "Pull Up Method",
        "Extract Method",
    },
    GoFPattern.ADAPTER: {
        "Extract Class",
        "Extract Interface",
        "Move Method",
    },
    GoFPattern.PROXY: {
        "Extract Class",
        "Extract Interface",
        "Move Method",
    },
    GoFPattern.FACADE: {
        "Extract Class",
        "Move Method",
    },
    GoFPattern.SINGLETON: {
        "Extract Method",
        "Add Attribute",
    },
    GoFPattern.COMPOSITE: {
        "Extract Interface",
        "Extract Superclass",
        "Extract Class",
        "Pull Up Method",
    },
    GoFPattern.VISITOR: {
        "Extract Interface",
        "Extract Class",
        "Add Parameter",
    },
    GoFPattern.STATE: {
        "Extract Interface",
        "Extract Class",
        "Move Method",
    },
    GoFPattern.PROTOTYPE: {
        "Extract Interface",
        "Extract Class",
        "Add Method",         # clone() introduction
    },
}


# ---------------------------------------------------------------------------
# Keyword lists
# ---------------------------------------------------------------------------

# Words that signal "something was refactored" (problem-side)
_REFACTORING_VERBS = re.compile(
    r"\b(introduc|refactor|extract|replac|migrat|convert|rewrit|clean\s*up|simplif)\b",
    re.IGNORECASE,
)

# Pattern names / synonyms (solution-side)
_PATTERN_NAMES = re.compile(
    r"\b(builder|factory|strategy|observer|decorator|proxy|singleton|facade|adapter"
    r"|visitor|command|template\s+method|composite|prototype|chain\s+of\s+resp"
    r"|flyweight|iterator|mediator|memento|state)\b",
    re.IGNORECASE,
)

# Problem descriptions that precede a pattern fix
_PROBLEM_SIGNALS = re.compile(
    r"\b(telescoping\s+constructor|long\s+parameter|switch\s+statement"
    r"|massive\s+class|god\s+class|tight\s+coupling|code\s+smell)\b",
    re.IGNORECASE,
)


def _keyword_match(message: str) -> tuple[bool, list[GoFPattern]]:
    """
    Return (matched, list_of_suspected_patterns) for a commit message.
    A commit matches if it contains BOTH a refactoring verb AND a pattern name,
    OR if it contains a problem signal.
    """
    has_verb     = bool(_REFACTORING_VERBS.search(message))
    has_pattern  = bool(_PATTERN_NAMES.search(message))
    has_problem  = bool(_PROBLEM_SIGNALS.search(message))

    if not ((has_verb and has_pattern) or has_problem):
        return False, []

    # Try to infer which pattern(s) are mentioned
    suspected: list[GoFPattern] = []
    lower = message.lower()
    _name_to_pattern = {
        "builder":          GoFPattern.BUILDER,
        "factory":          GoFPattern.FACTORY_METHOD,
        "abstract factory": GoFPattern.ABSTRACT_FACTORY,
        "strategy":         GoFPattern.STRATEGY,
        "observer":         GoFPattern.OBSERVER,
        "decorator":        GoFPattern.DECORATOR,
        "proxy":            GoFPattern.PROXY,
        "singleton":        GoFPattern.SINGLETON,
        "facade":           GoFPattern.FACADE,
        "adapter":          GoFPattern.ADAPTER,
        "visitor":          GoFPattern.VISITOR,
        "command":          GoFPattern.COMMAND,
        "template method":  GoFPattern.TEMPLATE_METHOD,
        "composite":        GoFPattern.COMPOSITE,
        "prototype":        GoFPattern.PROTOTYPE,
        "state":            GoFPattern.STATE,
        "chain of resp":    GoFPattern.CHAIN_OF_RESP,
    }
    for keyword, pattern in _name_to_pattern.items():
        if keyword in lower:
            suspected.append(pattern)

    return True, suspected


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class SignalBase(ABC):
    """Base class for a single signal source in Stage 2."""

    @abstractmethod
    def scan_repo(
        self,
        repo: git.Repo,
        candidate: RepoCandidate,
        since: datetime,
        max_commits: int,
    ) -> Iterator[CommitCandidate]:
        """Yield CommitCandidate objects for commits that fire this signal."""
        ...


# ---------------------------------------------------------------------------
# 2A – Keyword signal
# ---------------------------------------------------------------------------

class KeywordSignal(SignalBase):
    """
    Greps commit messages for pattern-name + refactoring-verb combinations.
    Cheap to run; produces many false positives that later stages filter out.
    """

    def scan_repo(
        self,
        repo: git.Repo,
        candidate: RepoCandidate,
        since: datetime,
        max_commits: int,
    ) -> Iterator[CommitCandidate]:
        count = 0
        for commit in repo.iter_commits(since=since):
            if count >= max_commits:
                break
            matched, patterns = _keyword_match(commit.message)
            if not matched:
                continue
            if not commit.parents:
                continue  # skip root commit

            parent_sha = commit.parents[0].hexsha
            logger.info(
                "[KeywordSignal] Match: %s  %s", commit.hexsha[:8], commit.message[:60]
            )
            yield CommitCandidate(
                repo=candidate,
                commit_sha=commit.hexsha,
                parent_sha=parent_sha,
                commit_message=commit.message,
                signals=[SignalSource.KEYWORD],
                suspected_patterns=patterns,
            )
            count += 1


# ---------------------------------------------------------------------------
# 2B – RefactoringMiner signal
# ---------------------------------------------------------------------------

class RefminerSignal(SignalBase):
    """
    Runs RefactoringMiner on every commit (up to ``max_commits``) and checks
    whether the detected atomic refactorings match the structural fingerprint
    of any GoF pattern.

    Reuses ``refagent.utils.refminer_utils.default_runner``.
    """

    # Minimum number of fingerprint-matching rminer operations required
    # before we treat a commit as a candidate.
    MIN_MATCHING_OPS: int = 2

    def scan_repo(
        self,
        repo: git.Repo,
        candidate: RepoCandidate,
        since: datetime,
        max_commits: int,
    ) -> Iterator[CommitCandidate]:
        count = 0
        for commit in repo.iter_commits(since=since):
            if count >= max_commits:
                break
            if not commit.parents:
                continue  # skip root commit

            sha  = commit.hexsha
            parent_sha = commit.parents[0].hexsha

            try:
                refactorings = refminer_utils.default_runner.run(
                    project_path=str(candidate.local_path),
                    commit_hash=sha,
                )
            except refminer_utils.RminerError as exc:
                logger.warning("[RefminerSignal] rminer failed on %s: %s", sha[:8], exc)
                continue
            except Exception as exc:
                logger.warning("[RefminerSignal] Unexpected error on %s: %s", sha[:8], exc)
                continue

            if not refactorings:
                continue

            rminer_type_strings = [r.type for r in refactorings]
            matched_patterns = self._match_patterns(set(rminer_type_strings))

            if not matched_patterns:
                continue

            logger.info(
                "[RefminerSignal] Match: %s  patterns=%s  ops=%s",
                sha[:8],
                matched_patterns,
                rminer_type_strings,
            )
            yield CommitCandidate(
                repo=candidate,
                commit_sha=sha,
                parent_sha=parent_sha,
                commit_message=commit.message,
                signals=[SignalSource.REFMINER],
                refminer_types=rminer_type_strings,
                suspected_patterns=matched_patterns,
            )
            count += 1

    def _match_patterns(self, rminer_types: set[str]) -> list[GoFPattern]:
        """Return which GoF patterns have enough matching RefactoringMiner ops."""
        matches: list[GoFPattern] = []
        for pattern, fingerprint in PATTERN_REFMINER_FINGERPRINTS.items():
            overlap = rminer_types & fingerprint
            if len(overlap) >= self.MIN_MATCHING_OPS:
                matches.append(pattern)
        return matches


# ---------------------------------------------------------------------------
# 2C – Diff heuristic signal (stub for future implementation)
# ---------------------------------------------------------------------------

class DiffHeuristicSignal(SignalBase):
    """
    (Stub) Analyse the raw file diff for structural before/after signatures
    that indicate a specific pattern was introduced.

    Examples:
      - Builder: constructor with N params disappeared; new class with build()
        and chained setters appeared.
      - Strategy: switch/if-else block deleted; interface + impls added.

    TODO: implement per-pattern AST checks using tree-sitter or JavaParser.
    """

    def scan_repo(
        self,
        repo: git.Repo,
        candidate: RepoCandidate,
        since: datetime,
        max_commits: int,
    ) -> Iterator[CommitCandidate]:
        # TODO: implement
        logger.debug("[DiffHeuristicSignal] Not yet implemented, yielding nothing.")
        return
        yield  # make this a generator


# ---------------------------------------------------------------------------
# Multi-signal miner (combines the above)
# ---------------------------------------------------------------------------

class MultiSignalMiner:
    """
    Runs multiple signal sources against a repo and merges their results,
    deduplicating by commit SHA and combining signals from different sources.

    Parameters
    ----------
    signals : list[SignalBase]
        Signal sources to run (order doesn't matter).
    since : datetime
        Only examine commits authored after this date.
    max_commits_per_signal : int
        Max commits fed to each signal per repo.
    """

    def __init__(
        self,
        signals: list[SignalBase],
        since: datetime,
        max_commits_per_signal: int = 500,
    ) -> None:
        self.signals = signals
        self.since   = since
        self.max_commits_per_signal = max_commits_per_signal

    def mine(self, candidate: RepoCandidate) -> list[CommitCandidate]:
        """
        Run all signals against ``candidate`` and return merged candidates.
        """
        if candidate.local_path is None:
            raise ValueError(f"Repo not cloned yet: {candidate.full_name}")

        repo = git.Repo(candidate.local_path)

        # sha → CommitCandidate (merge by SHA)
        merged: dict[str, CommitCandidate] = {}

        for signal in self.signals:
            for cc in signal.scan_repo(
                repo=repo,
                candidate=candidate,
                since=self.since,
                max_commits=self.max_commits_per_signal,
            ):
                sha = cc.commit_sha
                if sha in merged:
                    # Merge signals and suspected patterns
                    existing = merged[sha]
                    new_signals = list(set(existing.signals + cc.signals))
                    new_patterns = list(set(existing.suspected_patterns + cc.suspected_patterns))
                    new_types = list(set(existing.refminer_types + cc.refminer_types))
                    merged[sha] = existing.model_copy(update={
                        "signals": new_signals,
                        "suspected_patterns": new_patterns,
                        "refminer_types": new_types,
                    })
                else:
                    merged[sha] = cc

        results = list(merged.values())
        logger.info(
            "[MultiSignalMiner] %s: %d candidate commits found",
            candidate.full_name,
            len(results),
        )
        return results
