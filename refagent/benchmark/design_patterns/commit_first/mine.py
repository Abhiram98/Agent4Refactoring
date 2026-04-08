"""
mine.py  –  Stage 2 entrypoint
--------------------------------
Run commit mining on one or more already-cloned local repositories and write
the candidate commits to a JSON file for Stage 3 to consume.

Usage examples
--------------
# Single repo, both signals
python -m refagent.benchmark.design_patterns.mine \\
    --repos /path/to/my-repo \\
    --output /tmp/candidates.json

# Several repos, keyword signal only (faster)
python -m refagent.benchmark.design_patterns.mine \\
    --repos /path/to/repo-a /path/to/repo-b \\
    --output /tmp/candidates.json \\
    --no-refminer \\
    --since 2024-01-01

# Specific patterns only
python -m refagent.benchmark.design_patterns.mine \\
    --repos /path/to/my-repo \\
    --patterns Builder Strategy Observer \\
    --output /tmp/candidates.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import git

from refagent.benchmark.design_patterns.commit_first.commit_miner import (
    KeywordSignal,
    MultiSignalMiner,
    RefminerSignal,
)
from refagent.benchmark.design_patterns.models import GoFPattern, RepoCandidate

logger = logging.getLogger(__name__)
UTC = timezone.utc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _repo_candidate_from_local_path(path: Path) -> RepoCandidate:
    """
    Build a minimal RepoCandidate from a local git checkout.
    Attempts to read the remote URL; falls back to the directory name.
    """
    try:
        repo = git.Repo(path)
        remote_url = repo.remotes.origin.url
    except Exception:
        remote_url = f"file://{path}"

    # Derive owner/name from URL or directory
    parts = remote_url.rstrip("/").rstrip(".git").rsplit("/", 2)
    if len(parts) >= 2:
        owner, name = parts[-2].split(":")[-1], parts[-1]   # handle git@ URLs
    else:
        owner, name = "local", path.name

    return RepoCandidate(
        owner=owner,
        name=name,
        stars=0,
        pushed_at="unknown",
        clone_url=remote_url,
        local_path=path,
    )


def _filter_by_patterns(
    candidates: list,
    patterns: list[GoFPattern] | None,
) -> list:
    """If a pattern filter is active, drop candidates with no overlap."""
    if not patterns:
        return candidates
    pattern_set = set(patterns)
    return [
        c for c in candidates
        if not c.suspected_patterns or set(c.suspected_patterns) & pattern_set
    ]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_mining(
    repo_paths: list[Path],
    output_path: Path,
    since: datetime,
    max_commits: int,
    enable_keyword: bool,
    enable_refminer: bool,
    patterns: list[GoFPattern] | None,
) -> list[dict]:
    """
    Core logic – separated from argument parsing so it can be imported and
    called programmatically.

    Returns the list of serialised CommitCandidate dicts that were written.
    """
    signals = []
    if enable_keyword:
        signals.append(KeywordSignal())
    if enable_refminer:
        signals.append(RefminerSignal())

    if not signals:
        logger.error("At least one signal must be enabled.")
        sys.exit(1)

    miner = MultiSignalMiner(
        signals=signals,
        since=since,
        max_commits_per_signal=max_commits,
    )

    all_candidates: list[dict] = []

    for repo_path in repo_paths:
        if not repo_path.exists():
            logger.error("Path does not exist: %s", repo_path)
            continue

        logger.info("─── Mining %s ───", repo_path)
        try:
            repo_candidate = _repo_candidate_from_local_path(repo_path)
        except Exception as exc:
            logger.error("Not a git repo (%s): %s", repo_path, exc)
            continue

        try:
            candidates = miner.mine(repo_candidate)
        except Exception as exc:
            logger.error("Mining failed for %s: %s", repo_path, exc)
            continue

        candidates = _filter_by_patterns(candidates, patterns)
        logger.info("  → %d candidates (after pattern filter)", len(candidates))

        # Serialise – store local_path so Stage 3 can find the repo
        for c in candidates:
            d = c.model_dump(mode="json")
            d["repo"]["local_path"] = str(repo_path)   # ensure path is preserved
            all_candidates.append(d)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(all_candidates, f, indent=2, default=str)

    logger.info(
        "Wrote %d total candidates to %s", len(all_candidates), output_path
    )
    return all_candidates


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="mine",
        description="Stage 2 – Mine local repos for design-pattern introduction candidates.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--repos", nargs="+", type=Path, required=True,
        metavar="PATH",
        help="One or more paths to locally-cloned git repositories.",
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path("data/design_patterns/candidates.json"),
        help="Output JSON file for Stage 3 (default: data/design_patterns/candidates.json).",
    )
    parser.add_argument(
        "--since", type=str, default="2026-01-01",
        metavar="YYYY-MM-DD",
        help="Only examine commits after this date.",
    )
    parser.add_argument(
        "--max-commits", type=int, default=500,
        help="Maximum commits to feed to each signal per repo (default: 500).",
    )
    parser.add_argument(
        "--no-keyword", action="store_true",
        help="Disable the commit-message keyword signal.",
    )
    parser.add_argument(
        "--no-refminer", action="store_true",
        help="Disable RefactoringMiner (much faster, lower recall).",
    )
    parser.add_argument(
        "--patterns", nargs="*",
        choices=[p.value for p in GoFPattern],
        metavar="PATTERN",
        help=(
            "Only keep candidates suspected of introducing these patterns. "
            "Omit to keep all. e.g. --patterns Builder Strategy"
        ),
    )
    parser.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)-8s %(name)s – %(message)s",
        datefmt="%H:%M:%S",
    )

    since_dt = datetime.fromisoformat(args.since).replace(tzinfo=UTC)
    patterns = [GoFPattern(p) for p in args.patterns] if args.patterns else None

    run_mining(
        repo_paths=args.repos,
        output_path=args.output,
        since=since_dt,
        max_commits=args.max_commits,
        enable_keyword=not args.no_keyword,
        enable_refminer=not args.no_refminer,
        patterns=patterns,
    )
