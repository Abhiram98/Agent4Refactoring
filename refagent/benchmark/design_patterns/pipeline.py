"""
pipeline.py
-----------
Top-level orchestrator that wires Stage 1 → Stage 2 → Stage 3 together
and writes intermediate + final output.

Usage (CLI):
    python -m refagent.benchmark.design_patterns.pipeline \\
        --output  data/design_patterns/dp_introductions.json \\
        --since   2023-01-01 \\
        --max-repos 50 \\
        --max-commits 300

Or import and drive programmatically:
    from refagent.benchmark.design_patterns.pipeline import Pipeline
    results = Pipeline(...).run()
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from refagent.benchmark.design_patterns.commit_miner import (
    DiffHeuristicSignal,
    KeywordSignal,
    MultiSignalMiner,
    RefminerSignal,
)
from refagent.benchmark.design_patterns.models import PatternIntroductionInstance
from refagent.benchmark.design_patterns.repo_harvester import RepoCloner, RepoHarvester
from refagent.benchmark.design_patterns.validator import (
    HIGH_CONFIDENCE_THRESHOLD,
    REVIEW_THRESHOLD,
    Validator,
)

logger = logging.getLogger(__name__)

UTC = timezone.utc


class Pipeline:
    """
    End-to-end pipeline for finding design-pattern introduction commits.

    Parameters
    ----------
    output_path : Path
        Where to write the final JSON dataset.
    clone_base_dir : Path
        Directory for cloning repos (defaults to ``data/dp_repos/`` in repo root).
    since : datetime
        Only examine commits after this date.
    max_repos : int
        Cap on repos to discover.
    max_commits_per_signal : int
        Max commits fed to each signal per repo.
    min_stars, max_stars : int
        Star-count window for repo discovery.
    enable_refminer : bool
        Whether to run the RefactoringMiner signal (slow but high-precision).
    enable_keyword : bool
        Whether to run the keyword signal.
    starting_id : int
        Starting numeric ID for output records.
    """

    def __init__(
        self,
        output_path: Path,
        clone_base_dir: Path,
        since: datetime,
        max_repos: int = 50,
        max_commits_per_signal: int = 300,
        min_stars: int = 500,
        max_stars: int = 5000,
        enable_refminer: bool = True,
        enable_keyword: bool = True,
        starting_id: int = 1,
    ) -> None:
        self.output_path            = output_path
        self.clone_base_dir         = clone_base_dir
        self.since                  = since
        self.max_repos              = max_repos
        self.max_commits_per_signal = max_commits_per_signal
        self.min_stars              = min_stars
        self.max_stars              = max_stars
        self.enable_refminer        = enable_refminer
        self.enable_keyword         = enable_keyword
        self.starting_id            = starting_id

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> list[PatternIntroductionInstance]:
        """Execute all stages and return validated instances."""

        # ── Stage 1: Repo Discovery ──────────────────────────────────
        logger.info("=== Stage 1: Repo Discovery ===")
        repos = self._stage1_discover()
        logger.info("Discovered %d candidate repos", len(repos))

        cloner = RepoCloner(base_dir=self.clone_base_dir)

        all_instances: list[PatternIntroductionInstance] = []
        manual_review: list[PatternIntroductionInstance] = []

        validator = Validator(starting_id=self.starting_id)

        for repo in repos:
            # ── Clone ────────────────────────────────────────────────
            try:
                repo = cloner.clone_or_update(repo)
            except Exception as exc:
                logger.error("Failed to clone %s: %s", repo.full_name, exc)
                continue

            # ── Stage 2: Commit Mining ───────────────────────────────
            logger.info("=== Stage 2: Mining %s ===", repo.full_name)
            candidates = self._stage2_mine(repo)
            logger.info("Found %d candidates in %s", len(candidates), repo.full_name)

            # ── Stage 3: Validation ──────────────────────────────────
            logger.info("=== Stage 3: Validating %s candidates ===", len(candidates))
            for candidate in candidates:
                instance = validator.validate(candidate)
                if instance is None:
                    continue
                if instance.evidence.is_high_confidence:
                    all_instances.append(instance)
                    logger.info(
                        "✓ High-confidence: %s  pattern=%s  score=%d",
                        instance.commit_sha[:8],
                        instance.pattern,
                        instance.evidence.total,
                    )
                elif instance.evidence.needs_manual_review:
                    manual_review.append(instance)
                    logger.info(
                        "? Needs review: %s  pattern=%s  score=%d",
                        instance.commit_sha[:8],
                        instance.pattern,
                        instance.evidence.total,
                    )

            # Write partial results after each repo so nothing is lost on crash
            self._write_output(all_instances, manual_review)

        logger.info(
            "Pipeline complete: %d high-confidence, %d manual-review",
            len(all_instances),
            len(manual_review),
        )
        return all_instances

    # ------------------------------------------------------------------
    # Stage implementations
    # ------------------------------------------------------------------

    def _stage1_discover(self):
        harvester = RepoHarvester(
            min_stars=self.min_stars,
            max_stars=self.max_stars,
            pushed_after=self.since.strftime("%Y-%m-%d"),
            max_repos=self.max_repos,
        )
        return harvester.discover()

    def _stage2_mine(self, repo):
        signals = []
        if self.enable_keyword:
            signals.append(KeywordSignal())
        if self.enable_refminer:
            signals.append(RefminerSignal())
        # DiffHeuristicSignal is a stub – omit until implemented
        # signals.append(DiffHeuristicSignal())

        miner = MultiSignalMiner(
            signals=signals,
            since=self.since,
            max_commits_per_signal=self.max_commits_per_signal,
        )
        return miner.mine(repo)

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    def _write_output(
        self,
        high_confidence: list[PatternIntroductionInstance],
        manual_review: list[PatternIntroductionInstance],
    ) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "high_confidence": [i.to_json() for i in high_confidence],
            "manual_review":   [i.to_json() for i in manual_review],
        }
        with open(self.output_path, "w") as f:
            json.dump(payload, f, indent=2, default=str)
        logger.info("Wrote %d records to %s", len(high_confidence) + len(manual_review), self.output_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mine Java repos for design-pattern introduction commits."
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path("data/design_patterns/dp_introductions.json"),
        help="Output JSON file",
    )
    parser.add_argument(
        "--clone-dir", type=Path,
        default=Path("data/dp_repos"),
        help="Directory to clone repos into",
    )
    parser.add_argument(
        "--since", type=str, default="2023-01-01",
        help="Only look at commits after this date (YYYY-MM-DD)",
    )
    parser.add_argument("--max-repos",    type=int, default=50)
    parser.add_argument("--max-commits",  type=int, default=300,
                        help="Max commits per signal per repo")
    parser.add_argument("--min-stars",    type=int, default=500)
    parser.add_argument("--max-stars",    type=int, default=5000)
    parser.add_argument("--no-refminer",  action="store_true",
                        help="Disable the RefactoringMiner signal (faster)")
    parser.add_argument("--no-keyword",   action="store_true",
                        help="Disable the keyword signal")
    parser.add_argument("--starting-id",  type=int, default=1)
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s – %(message)s",
        datefmt="%H:%M:%S",
    )

    args = _parse_args()
    since_dt = datetime.fromisoformat(args.since).replace(tzinfo=UTC)

    Pipeline(
        output_path=args.output,
        clone_base_dir=args.clone_dir,
        since=since_dt,
        max_repos=args.max_repos,
        max_commits_per_signal=args.max_commits,
        min_stars=args.min_stars,
        max_stars=args.max_stars,
        enable_refminer=not args.no_refminer,
        enable_keyword=not args.no_keyword,
        starting_id=args.starting_id,
    ).run()
