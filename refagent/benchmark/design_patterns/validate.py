"""
validate.py  –  Stage 3 entrypoint
------------------------------------
Validate and score CommitCandidate records produced by mine.py (Stage 2).
Writes two output files:
  • <output>               – high-confidence records (score ≥ 5)
  • <output>.review.json   – records that need manual review (score 3-4)

Usage examples
--------------
# Basic – read from Stage 2 output
python -m refagent.benchmark.design_patterns.validate \\
    --candidates /tmp/candidates.json \\
    --output     data/design_patterns/dp_introductions.json

# Only keep candidates for specific patterns
python -m refagent.benchmark.design_patterns.validate \\
    --candidates /tmp/candidates.json \\
    --output     data/design_patterns/dp_introductions.json \\
    --patterns Builder Observer

# Lower the confidence threshold to see more results during exploration
python -m refagent.benchmark.design_patterns.validate \\
    --candidates /tmp/candidates.json \\
    --output     /tmp/results.json \\
    --min-score 3
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Optional

from refagent.benchmark.design_patterns.models import (
    CommitCandidate,
    GoFPattern,
    PatternIntroductionInstance,
    RepoCandidate,
)
from refagent.benchmark.design_patterns.validator import Validator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Deserialization helpers
# ---------------------------------------------------------------------------

def _load_candidates(candidates_path: Path) -> list[CommitCandidate]:
    """Load CommitCandidate objects from the JSON file written by mine.py."""
    with open(candidates_path) as f:
        raw_list = json.load(f)

    candidates: list[CommitCandidate] = []
    for raw in raw_list:
        try:
            # Pydantic will coerce enum strings automatically
            candidates.append(CommitCandidate.model_validate(raw))
        except Exception as exc:
            logger.warning("Skipping malformed candidate record: %s", exc)

    logger.info("Loaded %d candidates from %s", len(candidates), candidates_path)
    return candidates


def _filter_by_patterns(
    candidates: list[CommitCandidate],
    patterns: list[GoFPattern] | None,
) -> list[CommitCandidate]:
    if not patterns:
        return candidates
    pattern_set = set(p.value for p in patterns)
    return [
        c for c in candidates
        if set(c.suspected_patterns) & pattern_set
    ]


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

def run_validation(
    candidates_path: Path,
    output_path: Path,
    min_score: int,
    patterns: list[GoFPattern] | None,
    starting_id: int,
) -> tuple[list[PatternIntroductionInstance], list[PatternIntroductionInstance]]:
    """
    Core validation logic — separated from argument-parsing so it can be
    imported and called directly.

    Returns
    -------
    (high_confidence, manual_review) lists of PatternIntroductionInstance.
    """
    candidates = _load_candidates(candidates_path)
    candidates = _filter_by_patterns(candidates, patterns)
    logger.info("%d candidates after pattern filter", len(candidates))

    validator = Validator(starting_id=starting_id)

    high_confidence: list[PatternIntroductionInstance] = []
    manual_review:   list[PatternIntroductionInstance] = []
    discarded = 0

    for i, candidate in enumerate(candidates, 1):
        logger.info(
            "[%d/%d] Validating %s in %s/%s",
            i, len(candidates),
            candidate.commit_sha[:8],
            candidate.repo.owner,
            candidate.repo.name,
        )
        instance = validator.validate(candidate)

        if instance is None:
            discarded += 1
            continue

        score = instance.evidence.total

        if score < min_score:
            discarded += 1
            logger.debug("  ↳ Discarded (score %d < min %d)", score, min_score)
        elif instance.evidence.is_high_confidence:
            high_confidence.append(instance)
            logger.info(
                "  ✓ High-confidence: pattern=%s score=%d", instance.pattern, score
            )
        elif instance.evidence.needs_manual_review:
            manual_review.append(instance)
            logger.info(
                "  ? Needs review:    pattern=%s score=%d", instance.pattern, score
            )
        else:
            # min_score <= score < review threshold
            manual_review.append(instance)
            logger.info(
                "  ? Low-score kept:  pattern=%s score=%d", instance.pattern, score
            )

    logger.info(
        "Validation done – high-confidence: %d, review: %d, discarded: %d",
        len(high_confidence), len(manual_review), discarded,
    )

    _write_outputs(output_path, high_confidence, manual_review)
    return high_confidence, manual_review


def _write_outputs(
    output_path: Path,
    high_confidence: list[PatternIntroductionInstance],
    manual_review: list[PatternIntroductionInstance],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    review_path = output_path.with_suffix("").with_name(
        output_path.stem + ".review"
    ).with_suffix(".json")

    with open(output_path, "w") as f:
        json.dump([i.to_json() for i in high_confidence], f, indent=2, default=str)
    logger.info("Wrote %d high-confidence records → %s", len(high_confidence), output_path)

    with open(review_path, "w") as f:
        json.dump([i.to_json() for i in manual_review], f, indent=2, default=str)
    logger.info("Wrote %d review records → %s", len(manual_review), review_path)

    # Human-readable summary
    _print_summary(high_confidence + manual_review, output_path)


def _print_summary(
    instances: list[PatternIntroductionInstance],
    output_path: Path,
) -> None:
    if not instances:
        logger.info("No instances to summarise.")
        return

    from collections import Counter
    pattern_counts = Counter(i.pattern for i in instances)

    logger.info("─── Summary ───────────────────────────────")
    logger.info("Total validated instances : %d", len(instances))
    logger.info("Breakdown by pattern:")
    for pattern, count in sorted(pattern_counts.items(), key=lambda x: -x[1]):
        logger.info("  %-20s %d", pattern, count)
    logger.info("Output: %s", output_path)
    logger.info("───────────────────────────────────────────")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="validate",
        description="Stage 3 – Validate and score design-pattern introduction candidates.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--candidates", type=Path, required=True,
        metavar="PATH",
        help="JSON file produced by mine.py (Stage 2).",
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path("data/design_patterns/dp_introductions.json"),
        help=(
            "Output JSON for high-confidence records. "
            "A parallel *.review.json file is always written alongside it."
        ),
    )
    parser.add_argument(
        "--patterns", nargs="*",
        choices=[p.value for p in GoFPattern],
        metavar="PATTERN",
        help=(
            "Only validate candidates suspected of these patterns. "
            "Omit to validate all. e.g. --patterns Builder Strategy"
        ),
    )
    parser.add_argument(
        "--min-score", type=int, default=3,
        metavar="N",
        help=(
            "Minimum total score (0–10) to keep a record. "
            "Records below this are silently discarded. "
            "High-confidence threshold is always 5. (default: 3)"
        ),
    )
    parser.add_argument(
        "--starting-id", type=int, default=1,
        help="Starting numeric ID for output records (default: 1).",
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

    patterns = [GoFPattern(p) for p in args.patterns] if args.patterns else None

    run_validation(
        candidates_path=args.candidates,
        output_path=args.output,
        min_score=args.min_score,
        patterns=patterns,
        starting_id=args.starting_id,
    )
