"""
birth_finder.py  –  Phase 2
-----------------------------
For each PatternInstance, find the git commit that first introduced the
pattern file into the repository.

Uses ``git log --diff-filter=A --follow`` to trace the file through renames
and moves, so it correctly identifies the original introduction commit even
when the file was later relocated.

Key outputs:
  - BirthInfo.birth_commit_sha  → the SHA we want to study
  - BirthInfo.parent_sha        → the before-state (parent of birth commit)
  - BirthInfo.is_initial_repo_commit → True when the file was added in the
    very first commit (almost certainly greenfield; the filter will discard it)
"""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import git

from refagent.benchmark.design_patterns.pattern_first.models import (
    BirthInfo,
    PatternInstance,
)

logger = logging.getLogger(__name__)
UTC = timezone.utc


class BirthFinder:
    """
    Finds the introduction commit of a pattern file in a local git repository.

    Parameters
    ----------
    repo_path : Path
        Root of the local repository checkout.
    """

    def __init__(self, repo_path: Path) -> None:
        self.repo_path = repo_path
        self._repo     = git.Repo(repo_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find(self, instance: PatternInstance) -> Optional[BirthInfo]:
        """
        Return the BirthInfo for ``instance``, or None if the file cannot be
        traced (e.g. it no longer exists in the repo, git error, etc.).
        """
        file_path = instance.file_path

        birth_sha, birth_date, birth_message = self._git_birth(file_path)
        if birth_sha is None:
            logger.warning("[BirthFinder] Cannot find birth commit for %s", file_path)
            return None

        parent_sha, is_initial = self._get_parent(birth_sha)

        logger.info(
            "[BirthFinder] %s → birth=%s (%s)%s",
            instance.class_name,
            birth_sha[:8],
            birth_date.date() if birth_date else "?",
            "  [INITIAL COMMIT]" if is_initial else "",
        )

        return BirthInfo(
            pattern_instance=instance,
            birth_commit_sha=birth_sha,
            birth_commit_date=birth_date or datetime.now(UTC),
            birth_commit_message=birth_message,
            parent_sha=parent_sha,
            is_initial_repo_commit=is_initial,
            original_file_path=file_path,
        )

    def find_all(self, instances: list[PatternInstance]) -> list[BirthInfo]:
        """Batch version of ``find``; skips instances that cannot be resolved."""
        results: list[BirthInfo] = []
        for inst in instances:
            info = self.find(inst)
            if info is not None:
                results.append(info)
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _git_birth(
        self, file_path: str
    ) -> tuple[Optional[str], Optional[datetime], str]:
        """
        Run ``git log --diff-filter=A --follow`` to locate the commit that
        first added ``file_path`` (tracing through renames).

        Returns (sha, date, message, original_path).
        """
        cmd = [
            "git", "-C", str(self.repo_path),
            "log",
            "--diff-filter=A",   # only commits where the file was *added*
            "--follow",          # trace renames/moves backwards
            "--format=%H%x00%aI%x00%s",  # NUL-separated: hash, ISO date, subject
            "--",
            file_path,
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=True,
                cwd=str(self.repo_path),
            )
        except subprocess.CalledProcessError as exc:
            logger.debug("git log failed for %s: %s", file_path, exc.stderr)
            return None, None, "", None

        output = result.stdout.strip()
        if not output:
            return None, None, "", None

        # The output contains one or more log entries separated by blank lines.
        # We want the OLDEST entry, which is the last one in the output.
        entries = [e.strip() for e in output.split("\n\n") if e.strip()]
        if not entries:
            return None, None, "", None

        oldest_entry = entries[-1]
        lines = oldest_entry.splitlines()
        if not lines:
            return None, None, "", None

        # First line: SHA\x00ISO-date\x00subject
        parts = lines[0].split("\x00")
        if len(parts) < 3:
            # Fallback: try splitting by space
            parts = lines[0].split(" ", 2)
        sha     = parts[0].strip()
        iso_str = parts[1].strip() if len(parts) > 1 else ""
        subject = parts[2].strip() if len(parts) > 2 else ""

        # Parse date
        date: Optional[datetime] = None
        if iso_str:
            try:
                date = datetime.fromisoformat(iso_str).astimezone(UTC)
            except ValueError:
                logger.warning("[BirthFinder] Cannot parse date from %s", iso_str)

        return sha, date, subject

    def _get_parent(self, sha: str) -> tuple[Optional[str], bool]:
        """
        Return (parent_sha, is_initial_commit).
        is_initial_commit is True when the commit has no parents.
        """
        try:
            commit = self._repo.commit(sha)
            if not commit.parents:
                return None, True
            return commit.parents[0].hexsha, False
        except Exception as exc:
            logger.warning("[BirthFinder] Could not resolve parent of %s: %s", sha, exc)
            return None, False
