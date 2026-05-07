"""
run.py
------
CLI entrypoint for the undo-pattern pipeline.

Usage
-----
# Dry run — inspect tasks without launching OpenHands
python -m refagent.benchmark.design_patterns.undo_pattern.run \\
    --ids ef050c5292da0baa 3f1a2b9c \\
    --dry-run

# Live run — dispatches OpenHands for each (candidate × variant) pair
python -m refagent.benchmark.design_patterns.undo_pattern.run \\
    --ids ef050c5292da0baa 3f1a2b9c \\
    --num-variants 2 \\
    --output data/design_patterns/undo_results.jsonl

# Override paths
python -m refagent.benchmark.design_patterns.undo_pattern.run \\
    --ids ef050c5292da0baa \\
    --candidates /path/to/aggregated_candidates.json \\
    --output /path/to/undo_results.jsonl \\
    --patches-dir /path/to/patches/ \\
    --md-dir /path/to/undo_pattern/
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import refagent
from refagent.benchmark.design_patterns.undo_pattern.pipeline import UndoPatternPipeline
from refagent.benchmark.design_patterns.undo_pattern.variants import VARIANT_REGISTRY

logger = logging.getLogger(__name__)

_DEFAULT_CANDIDATES = refagent.data_folder / "design_patterns" / "aggregated_candidates.json"
_DEFAULT_OUTPUT     = refagent.data_folder / "design_patterns" / "undo_results.jsonl"
_DEFAULT_PATCHES    = refagent.data_folder / "design_patterns" / "undo_patches"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="undo_pattern",
        description=(
            "Generate 'smelly' code snapshots by asking OpenHands to undo design patterns.\n"
            "\n"
            "For each supplied candidate ID the pipeline selects the top-N realism-ranked\n"
            "undo variants (parsed from the Markdown files in benchmark/design_patterns/\n"
            "undo_pattern/), constructs a task prompt, and dispatches OpenHands in headless\n"
            "mode using the project's existing Docker image as the sandbox.\n"
            "\n"
            "The agent's changes are captured as a .patch file for reproducibility."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Required
    parser.add_argument(
        "--ids",
        nargs="+",
        required=True,
        metavar="ID",
        help=(
            "One or more candidate IDs from aggregated_candidates.json to process. "
            "Example: --ids ef050c5292da0baa 3f1a2b9c"
        ),
    )

    # Dataset / output paths
    parser.add_argument(
        "--candidates",
        type=Path,
        default=_DEFAULT_CANDIDATES,
        metavar="PATH",
        help=f"Path to aggregated_candidates.json (default: {_DEFAULT_CANDIDATES})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_DEFAULT_OUTPUT,
        metavar="PATH",
        help=f"Appendable JSONL file for the task manifest (default: {_DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--patches-dir",
        type=Path,
        default=_DEFAULT_PATCHES,
        metavar="DIR",
        help=f"Directory where .patch / .diff files are saved (default: {_DEFAULT_PATCHES})",
    )

    # Variant selection
    parser.add_argument(
        "--num-variants",
        type=int,
        default=2,
        metavar="N",
        help="Number of top-realism variants to run per candidate (default: 2)",
    )
    parser.add_argument(
        "--md-dir",
        type=Path,
        default=None,
        metavar="DIR",
        help="Override the directory containing the undo_pattern/*.md files (default: auto-detected)",
    )

    # Execution flags
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print tasks and config without launching OpenHands",
    )

    # Logging
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )

    return parser.parse_args()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_registry_summary() -> None:
    """Log a summary of the loaded variant registry for quick sanity-check."""
    if not VARIANT_REGISTRY:
        logger.warning("VARIANT_REGISTRY is empty — did the Markdown files load correctly?")
        return
    logger.info("Loaded variant registry:")
    for pattern, variants in sorted(VARIANT_REGISTRY.items()):
        ids = ", ".join(v.id for v in variants)
        logger.info("  %-16s %d variant(s): %s", pattern, len(variants), ids)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    args = _parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)-8s %(name)s – %(message)s",
        datefmt="%H:%M:%S",
    )

    _print_registry_summary()

    pipeline = UndoPatternPipeline(
        candidate_ids=args.ids,
        candidates_path=args.candidates,
        output_path=args.output,
        patches_dir=args.patches_dir,
        num_variants=args.num_variants,
        dry_run=args.dry_run,
        md_dir=args.md_dir,
    )
    tasks = pipeline.run()

    if not args.dry_run:
        done    = sum(1 for t in tasks if t.status == "done")
        failed  = sum(1 for t in tasks if t.status == "failed")
        skipped = sum(1 for t in tasks if t.status == "pending")
        logger.info("─" * 50)
        logger.info("Tasks total  : %d", len(tasks))
        logger.info("  done       : %d", done)
        logger.info("  failed     : %d", failed)
        logger.info("  skipped    : %d", skipped)
        logger.info("Manifest     : %s", args.output)
        logger.info("Patches dir  : %s", args.patches_dir)


if __name__ == "__main__":
    main()
