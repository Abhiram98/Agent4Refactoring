"""
validator.py
------------
Stage 3 – Score and validate CommitCandidates.

Each candidate is scored across five dimensions (see ValidationEvidence in
models.py).  Candidates that don't reach the review threshold are discarded;
those above the high-confidence threshold are emitted directly; the rest go
into a manual-review queue.

The Validator is intentionally structured as a chain of individual
``_score_*`` methods so that each dimension can be extended or swapped out
independently.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

import git

from refagent.benchmark.design_patterns.models import (
    CommitCandidate,
    GoFPattern,
    PatternIntroductionInstance,
    SignalSource,
    ValidationEvidence,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

HIGH_CONFIDENCE_THRESHOLD = 5   # total score ≥ this → include automatically
REVIEW_THRESHOLD          = 3   # total score ≥ this → manual review queue
DISCARD_THRESHOLD         = 2   # total score < this → discard silently


# ---------------------------------------------------------------------------
# Structural fingerprints (pattern → after-state indicators)
# ---------------------------------------------------------------------------
# Each entry maps a GoFPattern to a set of regexes that should appear in
# the **after-state** diff (+lines) of the changed Java files.

_AFTER_PATTERNS: dict[str, list[re.Pattern]] = {
    GoFPattern.BUILDER: [
        re.compile(r"\breturn\s+this\b"),          # fluent setter
        re.compile(r"\bpublic\s+\w+\s+build\s*\("),  # build() method
    ],
    GoFPattern.STRATEGY: [
        re.compile(r"\binterface\b"),
        re.compile(r"\bvoid\s+execute\s*\(|abstract\b"),
    ],
    GoFPattern.OBSERVER: [
        re.compile(r"\bList<.*(?:Listener|Observer)\b"),
        re.compile(r"\bnotify\w*\s*\("),
        re.compile(r"\b(?:add|register)(?:Listener|Observer)\s*\("),
    ],
    GoFPattern.FACTORY_METHOD: [
        re.compile(r"\bfactory\b", re.IGNORECASE),
        re.compile(r"\breturn\s+new\b"),
    ],
    GoFPattern.DECORATOR: [
        re.compile(r"\bprivate\s+final\s+\w+\s+\w+\s*;"),  # wrapped field
        re.compile(r"delegate\.|wrapped\.|inner\."),
    ],
    GoFPattern.COMMAND: [
        re.compile(r"\bvoid\s+execute\s*\("),
        re.compile(r"\bvoid\s+undo\s*\("),
    ],
    GoFPattern.TEMPLATE_METHOD: [
        re.compile(r"\bfinal\b.*\bvoid|abstract\b.*\bvoid"),
    ],
    GoFPattern.SINGLETON: [
        re.compile(r"\bprivate\s+static\b"),
        re.compile(r"\bgetInstance\s*\("),
    ],
}

# ---------------------------------------------------------------------------
# Before-state messiness indicators
# ---------------------------------------------------------------------------
# These regexes look for code smells in the **before-state** diff (-lines).

_BEFORE_SMELL_PATTERNS = [
    re.compile(r"\bswitch\s*\("),              # switch statement over types
    re.compile(r"\bif\s*\(.*instanceof\b"),   # instanceof chain
    re.compile(r"\bnew\s+\w+\s*\(.*,.*,.*,.*,"), # constructor ≥ 4 args
    re.compile(r"\bif\s*\(\w+\s*==\s*\d+\)"),  # magic-number dispatch
]


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class Validator:
    """
    Scores a CommitCandidate and produces a PatternIntroductionInstance if
    the score is above the review threshold.

    Parameters
    ----------
    _id_counter : int
        Starting ID for output records (incremented for each accepted record).
    """

    def __init__(self, starting_id: int = 1) -> None:
        self._id_counter = starting_id

    def validate(
        self, candidate: CommitCandidate
    ) -> Optional[PatternIntroductionInstance]:
        """
        Score ``candidate`` and, if it passes the threshold, return a
        ``PatternIntroductionInstance``.  Returns None if discarded.
        """
        if not candidate.suspected_patterns:
            logger.debug("No suspected patterns; discarding %s", candidate.commit_sha[:8])
            return None

        repo_path = candidate.repo.local_path
        if repo_path is None:
            logger.warning("Repo not cloned for %s; skipping", candidate.repo.full_name)
            return None

        # Pick the most likely pattern (first in the list for now; could be refined)
        pattern = candidate.suspected_patterns[0]

        evidence = ValidationEvidence()
        diff_text = self._get_diff_text(repo_path, candidate.parent_sha, candidate.commit_sha)

        evidence = self._score_structural(evidence, pattern, diff_text)
        evidence = self._score_genuine_refactoring(evidence, repo_path, candidate)
        evidence = self._score_messiness(evidence, diff_text)
        evidence = self._score_commit_message(evidence, candidate.commit_message, pattern)
        evidence = self._score_refminer(evidence, candidate)

        logger.info(
            "Scored %s: total=%d (structural=%d, genuine=%d, mess=%d, msg=%d, rm=%d)",
            candidate.commit_sha[:8],
            evidence.total,
            evidence.structural_score,
            evidence.genuine_refactoring_score,
            evidence.messiness_score,
            evidence.commit_message_score,
            evidence.refminer_score,
        )

        if evidence.total < DISCARD_THRESHOLD:
            logger.debug("Discarding %s (score %d)", candidate.commit_sha[:8], evidence.total)
            return None

        instance = self._build_instance(candidate, pattern, evidence, diff_text)
        self._id_counter += 1
        return instance

    # ------------------------------------------------------------------
    # Scoring sub-methods (each returns an updated ValidationEvidence)
    # ------------------------------------------------------------------

    def _score_structural(
        self, ev: ValidationEvidence, pattern: str, diff_text: str
    ) -> ValidationEvidence:
        """
        Check whether the after-state diff contains structural signatures
        of the pattern.
        """
        # Extract only added lines from the diff
        added_lines = "\n".join(
            line[1:] for line in diff_text.splitlines() if line.startswith("+") and not line.startswith("+++")
        )

        fingerprints = _AFTER_PATTERNS.get(pattern, [])
        hits = sum(1 for fp in fingerprints if fp.search(added_lines))

        # TODO: replace with full AST-based check for higher precision
        if hits >= 2:
            ev = ev.model_copy(update={"structural_score": 3, "notes": ev.notes + [f"Structural: {hits}/{len(fingerprints)} fingerprints matched"]})
        elif hits == 1:
            ev = ev.model_copy(update={"structural_score": 1, "notes": ev.notes + ["Structural: 1 fingerprint matched"]})
        return ev

    def _score_genuine_refactoring(
        self, ev: ValidationEvidence, repo_path: Path, candidate: CommitCandidate
    ) -> ValidationEvidence:
        """
        Check that the commit modifies pre-existing files (not only adds new ones)
        and that call sites outside the new files are also updated.
        """
        repo = git.Repo(repo_path)
        try:
            commit = repo.commit(candidate.commit_sha)
            parent = repo.commit(candidate.parent_sha)
        except Exception as exc:
            logger.warning("Could not resolve commits: %s", exc)
            return ev

        diffs = parent.diff(commit)
        new_files      = [d for d in diffs if d.change_type == "A"]
        modified_files = [d for d in diffs if d.change_type == "M"]
        java_new       = [d for d in new_files      if (d.b_rawpath or b"").endswith(b".java")]
        java_modified  = [d for d in modified_files if (d.b_rawpath or b"").endswith(b".java")]

        notes = []
        score = 0

        if java_modified:
            score += 2
            notes.append(f"Genuine: {len(java_modified)} pre-existing Java files modified")
        if java_new:
            notes.append(f"Genuine: {len(java_new)} new Java files added")

        # Bonus: if there are modified files OTHER than the ones with pattern names,
        # it suggests call sites are being updated
        pattern_keywords = {"builder", "factory", "observer", "strategy", "decorator",
                            "proxy", "singleton", "facade", "adapter", "visitor",
                            "command", "template", "composite", "state"}
        call_site_mods = [
            d for d in java_modified
            if not any(kw in (d.b_rawpath or b"").decode("utf-8", errors="ignore").lower()
                       for kw in pattern_keywords)
        ]
        if call_site_mods:
            score = min(score + 1, 3)
            notes.append(f"Genuine: {len(call_site_mods)} call-site files also modified")

        return ev.model_copy(update={"genuine_refactoring_score": score, "notes": ev.notes + notes})

    def _score_messiness(
        self, ev: ValidationEvidence, diff_text: str
    ) -> ValidationEvidence:
        """
        Check whether the before-state (deleted lines) has code smell indicators.
        """
        removed_lines = "\n".join(
            line[1:] for line in diff_text.splitlines() if line.startswith("-") and not line.startswith("---")
        )
        hits = sum(1 for p in _BEFORE_SMELL_PATTERNS if p.search(removed_lines))

        notes = []
        score = 0
        if hits >= 2:
            score = 2
            notes.append(f"Messiness: {hits} code-smell patterns in before-state")
        elif hits == 1:
            score = 1
            notes.append("Messiness: 1 code-smell pattern in before-state")

        # TODO: add cyclomatic-complexity check via JavaParser

        return ev.model_copy(update={"messiness_score": score, "notes": ev.notes + notes})

    def _score_commit_message(
        self, ev: ValidationEvidence, message: str, pattern: str
    ) -> ValidationEvidence:
        """Check whether the commit message explicitly names the pattern."""
        lower = message.lower()
        # Map pattern enum value to searchable keywords
        keyword_map = {
            GoFPattern.BUILDER:         ["builder"],
            GoFPattern.STRATEGY:        ["strategy"],
            GoFPattern.OBSERVER:        ["observer", "listener"],
            GoFPattern.FACTORY_METHOD:  ["factory"],
            GoFPattern.ABSTRACT_FACTORY:["abstract factory"],
            GoFPattern.DECORATOR:       ["decorator"],
            GoFPattern.COMMAND:         ["command"],
            GoFPattern.TEMPLATE_METHOD: ["template method"],
            GoFPattern.SINGLETON:       ["singleton"],
            GoFPattern.ADAPTER:         ["adapter"],
            GoFPattern.PROXY:           ["proxy"],
            GoFPattern.FACADE:          ["facade"],
            GoFPattern.COMPOSITE:       ["composite"],
            GoFPattern.VISITOR:         ["visitor"],
            GoFPattern.STATE:           ["state pattern"],
            GoFPattern.PROTOTYPE:       ["prototype"],
        }
        keywords = keyword_map.get(pattern, [])
        if any(kw in lower for kw in keywords):
            return ev.model_copy(update={
                "commit_message_score": 1,
                "notes": ev.notes + ["Message: pattern name found in commit message"],
            })
        return ev

    def _score_refminer(
        self, ev: ValidationEvidence, candidate: CommitCandidate
    ) -> ValidationEvidence:
        """Give 1 point if RefactoringMiner also fired on this commit."""
        if SignalSource.REFMINER in candidate.signals and candidate.refminer_types:
            return ev.model_copy(update={
                "refminer_score": 1,
                "notes": ev.notes + [f"RefMiner: {candidate.refminer_types}"],
            })
        return ev

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_diff_text(self, repo_path: Path, parent_sha: str, commit_sha: str) -> str:
        """Return the unified diff text between parent and commit."""
        try:
            repo = git.Repo(repo_path)
            parent = repo.commit(parent_sha)
            commit = repo.commit(commit_sha)
            diffs = parent.diff(commit, create_patch=True)
            parts: list[str] = []
            for d in diffs:
                if d.diff:
                    parts.append(d.diff.decode("utf-8", errors="replace"))
            return "\n".join(parts)
        except Exception as exc:
            logger.warning("Could not get diff for %s: %s", commit_sha[:8], exc)
            return ""

    def _get_changed_java_files(
        self, repo_path: Path, parent_sha: str, commit_sha: str
    ) -> tuple[list[str], list[str]]:
        """Return (before_files, after_files) of Java file paths."""
        try:
            repo = git.Repo(repo_path)
            parent = repo.commit(parent_sha)
            commit = repo.commit(commit_sha)
            diffs = parent.diff(commit)
            before_files = [
                d.a_rawpath.decode("utf-8", errors="replace")
                for d in diffs if d.a_rawpath and d.a_rawpath.endswith(b".java")
            ]
            after_files = [
                d.b_rawpath.decode("utf-8", errors="replace")
                for d in diffs if d.b_rawpath and d.b_rawpath.endswith(b".java")
            ]
            return before_files, after_files
        except Exception as exc:
            logger.warning("Could not get changed files for %s: %s", commit_sha[:8], exc)
            return [], []

    def _build_instance(
        self,
        candidate: CommitCandidate,
        pattern: str,
        evidence: ValidationEvidence,
        diff_text: str,
    ) -> PatternIntroductionInstance:
        before_files, after_files = self._get_changed_java_files(
            candidate.repo.local_path,
            candidate.parent_sha,
            candidate.commit_sha,
        )
        return PatternIntroductionInstance(
            id=self._id_counter,
            repo_full_name=candidate.repo.full_name,
            clone_url=candidate.repo.clone_url,
            pattern=pattern,
            commit_sha=candidate.commit_sha,
            parent_sha=candidate.parent_sha,
            commit_message=candidate.commit_message,
            before_files=before_files,
            after_files=after_files,
            signals=candidate.signals,
            refminer_types=candidate.refminer_types,
            evidence=evidence,
        )
