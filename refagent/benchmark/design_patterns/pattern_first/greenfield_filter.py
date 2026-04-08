"""
greenfield_filter.py  –  Phase 3
-----------------------------------
Determines whether a pattern's introduction commit represents a genuine
refactoring of pre-existing code, or a greenfield introduction (pattern
classes written from scratch for brand-new functionality).

Two signals are implemented:

  3A  Call-site modification
      In the birth commit, were pre-existing .java files MODIFIED (as opposed
      to only new files being added)?  If yes, it means something that already
      existed was updated to use the pattern = strong refactoring signal.

  3B  Temporal age (package presence)
      Did the same directory already contain .java files BEFORE the birth
      commit?  If the package was brand-new in the birth commit, every file
      in it—including the pattern file—was likely written from scratch.

Verdict logic
-------------
  is_likely_refactoring = True
      iff (3A: ≥1 call-site modified)   OR
          (3B: package had ≥1 pre-existing sibling)

  Discarded (is_initial_repo_commit = True)
      The file was added in the very first commit; no before-state exists.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Optional

import git
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from refagent.benchmark.design_patterns.pattern_first.models import (
    BirthInfo,
    GreenfieldVerdict, MiningContext,
)

logger = logging.getLogger(__name__)
UTC = timezone.utc


class LLMFilter:
    """
    Uses an LLM to evaluate whether a commit is a release or a refactoring.
    """

    def __init__(self, model_name: str = "gpt-5-mini") -> None:
        self.model = ChatOpenAI(model=model_name, temperature=1)

    def is_release_commit(self, commit_message: str) -> bool:
        """
        Returns True if the LLM thinks the commit message refers to a release or version bump.
        """
        system_prompt = (
            "You are an expert software engineer. Your task is to determine if a git commit message "
            "indicates a 'release' commit, a 'version bump', or a 'distribution update'. "
            "Such commits often bundle many unrelated changes or just update version strings. "
            "Respond with only 'YES' or 'NO'."
        )
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Commit message: {commit_message}"),
        ]
        response = self.model.invoke(messages)
        return "YES" in response.content.upper()

    def analyze_diff(self, diff_text: str) -> tuple[bool, str]:
        """
        Analyzes a git diff and determines if it's a 'greenfield' pattern addition
        (writing new code from scratch) or a 'refactoring' (migrating existing logic).
        Returns (is_refactoring, reasoning).
        """
        system_prompt = (
            "You are an expert in design patterns and refactoring. Analyze the provided git diff. "
            "Determine if the commit represents a 'greenfield' introduction of a design pattern "
            "(i.e., new classes and logic added from scratch -- the design pattern was created directly) "
            "or a 'refactoring' (i.e., existing "
            "functionality being restructured into a design pattern). "
            "Focus on whether existing methods/logic were moved/changed into the new pattern structure. "
            "Provide your answer in the following format:\n"
            "Verdict: [REFACTORING/GREENFIELD]\n"
            "Reasoning: [Short explanation]"
        )
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Git Diff:\n{diff_text}"),
        ]
        response = self.model.invoke(messages)
        content = response.content
        is_ref = "REFACTORING" in content.upper() and "GREENFIELD" not in content.upper().split("VERDICT:")[1].split("\n")[0]
        # Safety check for parsing
        verdict_line = [line for line in content.splitlines() if "VERDICT:" in line.upper()]
        if verdict_line:
            is_ref = "REFACTORING" in verdict_line[0].upper()
        
        reasoning = content
        if "Reasoning:" in content:
            reasoning = content.split("Reasoning:")[1].strip()
            
        return is_ref, reasoning


class GreenfieldFilter:
    """
    Evaluates each BirthInfo and returns a GreenfieldVerdict.

    Parameters
    ----------
    context : MiningContext
        Pipeline context.
    min_call_site_modifications : int
        Minimum number of pre-existing modified .java files required for
        signal 3A to fire (default: 1).
    min_preexisting_siblings : int
        Minimum number of pre-existing sibling .java files required for
        signal 3B to fire (default: 1).
    """

    def __init__(
        self,
        context: MiningContext,
        min_call_site_modifications: int = 1,
        min_preexisting_siblings: int = 1,
        max_added_files: int = 100,
        llm_filter: Optional[LLMFilter] = None,
    ) -> None:
        self.context                     = context
        self.repo_path                   = context.repo_path
        self.min_call_site_modifications = min_call_site_modifications
        self.min_preexisting_siblings    = min_preexisting_siblings
        self.max_added_files            = max_added_files
        self.llm_filter                  = llm_filter
        self._repo                       = git.Repo(context.repo_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(self, birth_info: BirthInfo) -> GreenfieldVerdict:
        """
        Run tiered signals and return a GreenfieldVerdict.
        """
        # Fast-path: initial commit always means greenfield
        if birth_info.is_initial_repo_commit or birth_info.parent_sha is None:
            return GreenfieldVerdict(
                is_likely_refactoring=False,
                rejection_reasons=["File was added in the repository's initial commit — no before-state exists"],
            )

        # 1. Base heuristics (3A + 3B)
        verdict_3a = self._signal_3a(birth_info)
        verdict_3b = self._signal_3b(birth_info)

        notes  = verdict_3a.evidence_notes + verdict_3b.evidence_notes
        rejections = verdict_3a.rejection_reasons + verdict_3b.rejection_reasons

        is_heuristic_refactoring = (
            verdict_3a.is_likely_refactoring or verdict_3b.is_likely_refactoring
        )

        verdict = GreenfieldVerdict(
            # 3A fields
            modified_preexisting_java_count=verdict_3a.modified_preexisting_java_count,
            modified_preexisting_files=verdict_3a.modified_preexisting_files,
            # 3B fields
            package_had_preexisting_files=verdict_3b.package_had_preexisting_files,
            preexisting_sibling_count=verdict_3b.preexisting_sibling_count,
            oldest_sibling_age_days=verdict_3b.oldest_sibling_age_days,
            # Initial Combined verdict
            is_likely_refactoring=is_heuristic_refactoring,
            rejection_reasons=rejections,
            evidence_notes=notes,
        )

        if not is_heuristic_refactoring:
            verdict.rejection_reasons.append("Skip LLM: Heuristics 3A and 3B both fail")
            return verdict

        # 2. Static filter (> 100 added files)
        added_files = self._get_added_files_count(birth_info)
        if added_files > self.max_added_files:
            verdict.too_many_added_files = True
            verdict.is_likely_refactoring = False
            verdict.rejection_reasons.append(
                f"Skip LLM: Too many files added ({added_files} > {self.max_added_files})"
            )
            return verdict

        # 3. LLM Commit Message Check (Release)
        if self.llm_filter:
            is_release = self.llm_filter.is_release_commit(birth_info.birth_commit_message)
            verdict.is_release_commit = is_release
            if is_release:
                verdict.is_likely_refactoring = False
                verdict.rejection_reasons.append("Skip LLM Diff: LLM identified this as a release/bulk commit")
                return verdict

            # 4. LLM Diff Check
            diff_text = self._get_full_diff(birth_info)
            llm_is_ref, reasoning = self.llm_filter.analyze_diff(diff_text)
            verdict.llm_is_refactoring = llm_is_ref
            verdict.llm_reasoning = reasoning
            verdict.is_likely_refactoring = llm_is_ref
            
            if llm_is_ref:
                verdict.evidence_notes.append(f"LLM ✓ Refactoring confirmed: {reasoning[:200]}")
            else:
                verdict.rejection_reasons.append(f"LLM ✗ Greenfield according to LLM: {reasoning[:200]}")

        return verdict

    def evaluate_all(self, birth_infos: list[BirthInfo]) -> list[tuple[BirthInfo, GreenfieldVerdict]]:
        """Batch version. Returns (birth_info, verdict) pairs for all inputs."""
        return [(bi, self.evaluate(bi)) for bi in birth_infos]

    # ------------------------------------------------------------------
    # Signal 3A – call-site modification
    # ------------------------------------------------------------------

    def _signal_3a(self, birth_info: BirthInfo) -> GreenfieldVerdict:
        """
        Check whether any pre-existing .java files were MODIFIED (not added)
        in the birth commit, excluding the pattern file itself.
        """
        try:
            birth_commit  = self._repo.commit(birth_info.birth_commit_sha)
            parent_commit = self._repo.commit(birth_info.parent_sha)
        except Exception as exc:
            logger.warning("[3A] Cannot resolve commits: %s", exc)
            return GreenfieldVerdict(
                rejection_reasons=["3A: could not resolve commits"],
            )

        diffs = parent_commit.diff(birth_commit)

        pattern_file = birth_info.pattern_instance.file_path
        modified_preexisting: list[str] = []

        for diff in diffs:
            if diff.change_type != "M":
                continue  # only interested in Modified files
            b_path = (diff.b_rawpath or b"").decode("utf-8", errors="replace")
            if not b_path.endswith(".java"):
                continue
            if b_path == pattern_file:
                continue  # ignore the pattern file itself
            modified_preexisting.append(b_path)

        count    = len(modified_preexisting)
        fires    = count >= self.min_call_site_modifications
        notes    = []
        rejections = []

        if fires:
            notes.append(
                f"3A ✓ {count} pre-existing Java file(s) modified in birth commit "
                f"(call-site update): {modified_preexisting[:5]}"
                + (" …" if count > 5 else "")
            )
        else:
            rejections.append(
                f"3A ✗ No pre-existing Java files modified in birth commit "
                f"(only {count} found, need {self.min_call_site_modifications})"
            )

        return GreenfieldVerdict(
            modified_preexisting_java_count=count,
            modified_preexisting_files=modified_preexisting,
            is_likely_refactoring=fires,
            evidence_notes=notes,
            rejection_reasons=rejections,
        )

    # ------------------------------------------------------------------
    # Signal 3B – temporal age of the package
    # ------------------------------------------------------------------

    def _signal_3b(self, birth_info: BirthInfo) -> GreenfieldVerdict:
        """
        Check whether the directory that contains the pattern file already
        had other .java files BEFORE the birth commit.

        We look at the parent commit's tree to enumerate .java files in the
        same directory.  If any exist there, the package is pre-existing.
        """
        try:
            parent_commit = self._repo.commit(birth_info.parent_sha)
        except Exception as exc:
            logger.warning("[3B] Cannot resolve parent commit: %s", exc)
            return GreenfieldVerdict(rejection_reasons=["3B: could not resolve parent commit"])

        # Determine the directory of the pattern file in the parent tree
        pattern_file = birth_info.original_file_path or birth_info.pattern_instance.file_path
        package_dir  = str(PurePosixPath(pattern_file).parent)

        siblings: list[str] = self._java_files_in_dir_at_commit(parent_commit, package_dir)
        count = len(siblings)
        fires = count >= self.min_preexisting_siblings

        # Determine the age of the oldest sibling relative to the birth commit
        oldest_age_days: Optional[int] = None
        if siblings:
            oldest_age_days = self._oldest_file_age_days(siblings, birth_info.birth_commit_date)

        notes      = []
        rejections = []

        if fires:
            age_str = f", oldest sibling {oldest_age_days}d old" if oldest_age_days is not None else ""
            notes.append(
                f"3B ✓ Package '{package_dir}' had {count} pre-existing .java file(s)"
                f" before the birth commit{age_str}"
            )
        else:
            rejections.append(
                f"3B ✗ Package '{package_dir}' had no pre-existing .java files "
                f"before the birth commit (count={count})"
            )

        return GreenfieldVerdict(
            package_had_preexisting_files=fires,
            preexisting_sibling_count=count,
            oldest_sibling_age_days=oldest_age_days,
            is_likely_refactoring=fires,
            evidence_notes=notes,
            rejection_reasons=rejections,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _java_files_in_dir_at_commit(
        self, commit: git.Commit, directory: str
    ) -> list[str]:
        """
        Return relative paths of .java files inside ``directory`` as seen in
        ``commit``'s tree.  Uses gitpython's tree traversal (no checkout needed).
        """
        java_files: list[str] = []
        try:
            # Navigate to the subtree for the given directory
            subtree = commit.tree
            for part in directory.split("/"):
                if not part or part == ".":
                    continue
                try:
                    subtree = subtree[part]
                except KeyError:
                    return []  # directory didn't exist in parent → definitely new

            for blob in subtree.blobs:
                if blob.name.endswith(".java"):
                    java_files.append(blob.path)
        except Exception as exc:
            logger.debug("[3B] Tree traversal error for dir '%s': %s", directory, exc)

        return java_files

    def _oldest_file_age_days(
        self, file_paths: list[str], reference_date: datetime
    ) -> Optional[int]:
        """
        For each file in ``file_paths``, find its own birth commit and compute
        how many days before ``reference_date`` it was introduced.
        Returns the maximum age (oldest sibling).
        """
        max_age: Optional[int] = None
        for fp in file_paths[:10]:  # cap at 10 to avoid expensive git calls
            try:
                log = self._repo.git.log(
                    "--diff-filter=A", "--follow",
                    "--format=%aI", "--", fp,
                )
                if not log:
                    continue
                # The last line is the oldest entry
                oldest_line = log.strip().splitlines()[-1].strip()
                file_birth  = datetime.fromisoformat(oldest_line).astimezone(UTC)
                age_days    = (reference_date - file_birth).days
                if age_days > 0:
                    max_age = max(max_age or 0, age_days)
            except Exception:
                continue
        return max_age

    def _get_added_files_count(self, birth_info: BirthInfo) -> int:
        """
        Return the number of files added in the birth commit.
        """
        try:
            birth_commit = self._repo.commit(birth_info.birth_commit_sha)
            if not birth_info.parent_sha:
                return len(birth_commit.tree.traverse())
            
            parent_commit = self._repo.commit(birth_info.parent_sha)
            diffs = parent_commit.diff(birth_commit)
            return sum(1 for d in diffs if d.change_type == "A")
        except Exception as exc:
            logger.warning("Could not count added files: %s", exc)
            return 0

    def _get_full_diff(self, birth_info: BirthInfo) -> str:
        """
        Return the full diff of the birth commit against its parent.
        """
        try:
            if not birth_info.parent_sha:
                return self._repo.git.show(birth_info.birth_commit_sha)
            
            return self._repo.git.diff(birth_info.parent_sha, birth_info.birth_commit_sha)
        except Exception as exc:
            logger.warning("Could not get full diff: %s", exc)
            return ""
