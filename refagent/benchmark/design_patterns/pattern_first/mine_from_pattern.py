"""
mine_from_pattern.py  –  pattern-first pipeline CLI entrypoint
---------------------------------------------------------------
Runs the full pattern-first pipeline (Phases 1 → 2 → 3) on one or more
already-cloned local repositories and writes candidates to a JSON file that
shares the same schema as the commit-first ``candidates.json`` output.

Usage examples
--------------
# Heuristic scan of a local repo (Phase 1A + 1B)
python -m refagent.benchmark.design_patterns.pattern_first.mine_from_pattern \\
    --repos /path/to/my-repo \\
    --output data/design_patterns/pf_candidates.json

# Seed from dpdf_dataset (skip Phase 1, use known instances directly)
python -m refagent.benchmark.design_patterns.pattern_first.mine_from_pattern \\
    --repos /path/to/intellij-community \\
    --dpdf-dataset data/design_patterns/dpdf_dataset_filtered.json \\
    --dpdf-project intellij-community \\
    --output data/design_patterns/pf_candidates.json

# Multiple repos + filter to specific patterns
python -m refagent.benchmark.design_patterns.pattern_first.mine_from_pattern \\
    --repos /path/to/repo-a /path/to/repo-b \\
    --patterns Builder Observer \\
    --output data/design_patterns/pf_candidates.json

# Only include refactoring-likely instances (apply greenfield filter)
python -m refagent.benchmark.design_patterns.pattern_first.mine_from_pattern \\
    --repos /path/to/my-repo \\
    --filter-greenfield \\
    --output data/design_patterns/pf_candidates.json
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any, Tuple

import refagent
from refagent.benchmark.design_patterns.models import GoFPattern, PatternIntroductionInstance
from refagent.benchmark.design_patterns.pattern_first.birth_finder import BirthFinder
from refagent.benchmark.design_patterns.pattern_first.greenfield_filter import GreenfieldFilter, LLMFilter
from refagent.benchmark.design_patterns.pattern_first.models import (
    BirthInfo,
    GreenfieldVerdict,
    MiningContext,
    PatternCache,
    PatternInstance,
)

from refagent.benchmark.design_patterns.pattern_first.pattern_detector import (
    DpdfDatasetDetector,
    NameHeuristicDetector,
    detect_patterns,
)

logger = logging.getLogger(__name__)
UTC = timezone.utc


# ---------------------------------------------------------------------------
# Output serialisation
# ---------------------------------------------------------------------------

def _to_output_record(
    repo_path: Path,
    birth_info: BirthInfo,
    verdict: GreenfieldVerdict,
    instance_id: int,
) -> dict:
    """
    Serialise a (BirthInfo, GreenfieldVerdict) pair into a flat JSON record
    that can be loaded by the shared validate.py or used directly as a dataset
    entry.
    """
    inst = birth_info.pattern_instance
    return {
        "id": instance_id,
        "repo_path": str(repo_path),
        "pattern": inst.pattern.value if hasattr(inst.pattern, "value") else inst.pattern,
        "pattern_file": inst.file_path,
        "class_name": inst.class_name,
        "detection_source": inst.detection_source.value if hasattr(inst.detection_source, "value") else inst.detection_source,
        "detection_confidence": inst.confidence,
        "detection_reasoning": inst.reasoning,
        "birth_commit_sha": birth_info.birth_commit_sha,
        "parent_sha": birth_info.parent_sha,
        "birth_commit_date": birth_info.birth_commit_date.isoformat(),
        "birth_commit_message": birth_info.birth_commit_message,
        "is_initial_repo_commit": birth_info.is_initial_repo_commit,
        "original_file_path": birth_info.original_file_path,
        "greenfield": {
            "is_likely_refactoring": verdict.is_likely_refactoring,
            "signal_3a_modified_count": verdict.modified_preexisting_java_count,
            "signal_3a_modified_files": verdict.modified_preexisting_files,
            "signal_3b_package_preexisted": verdict.package_had_preexisting_files,
            "signal_3b_sibling_count": verdict.preexisting_sibling_count,
            "signal_3b_oldest_sibling_days": verdict.oldest_sibling_age_days,
            "llm_is_refactoring": verdict.llm_is_refactoring,
            "llm_reasoning": verdict.llm_reasoning,
            "is_release_commit": verdict.is_release_commit,
            "too_many_added_files": verdict.too_many_added_files,
            "evidence_notes": verdict.evidence_notes,
            "rejection_reasons": verdict.rejection_reasons,
        },
    }

def _from_output_record(record: dict) -> Tuple[Path, BirthInfo, GreenfieldVerdict]:
    repo_path = Path(record["repo_path"])
    
    inst = PatternInstance(
        file_path=record["pattern_file"],
        class_name=record["class_name"],
        pattern=GoFPattern(record["pattern"]),
        detection_source=record["detection_source"],
        confidence=record.get("detection_confidence", 1.0),
        reasoning=record.get("detection_reasoning", None)
    )
    
    birth_info = BirthInfo(
        pattern_instance=inst,
        birth_commit_sha=record["birth_commit_sha"],
        parent_sha=record["parent_sha"],
        # Allow naive string handling if fromisoformat isn't available, but standard is isoformat
        birth_commit_date=datetime.fromisoformat(record["birth_commit_date"]),
        birth_commit_message=record["birth_commit_message"],
        is_initial_repo_commit=record["is_initial_repo_commit"],
        original_file_path=record["original_file_path"],
    )
    
    gv_data = record.get("greenfield", {})
    verdict = GreenfieldVerdict(
        is_likely_refactoring=gv_data.get("is_likely_refactoring", False),
        modified_preexisting_java_count=gv_data.get("signal_3a_modified_count", 0),
        modified_preexisting_files=gv_data.get("signal_3a_modified_files", []),
        package_had_preexisting_files=gv_data.get("signal_3b_package_preexisted", False),
        preexisting_sibling_count=gv_data.get("signal_3b_sibling_count", 0),
        oldest_sibling_age_days=gv_data.get("signal_3b_oldest_sibling_days"),
        llm_is_refactoring=gv_data.get("llm_is_refactoring"),
        llm_reasoning=gv_data.get("llm_reasoning"),
        is_release_commit=gv_data.get("is_release_commit"),
        too_many_added_files=gv_data.get("too_many_added_files"),
        evidence_notes=gv_data.get("evidence_notes", []),
        rejection_reasons=gv_data.get("rejection_reasons", [])
    )
    
    return repo_path, birth_info, verdict

class PatternMiningPipeline:
    """
    Orchestrates the full pattern-first mining process:
    Phase 1 (Detection) → Phase 2 (Birth Discovery) → Phase 3 (Greenfield Filtering)
    """

    def __init__(self, repo_paths: list[Path], output_path: Path, context: MiningContext,
                 patterns: Optional[list[GoFPattern]] = None, use_heuristic: bool = True,
                 dpdf_dataset_path: Optional[Path] = None, dpdf_project_name: Optional[str] = None,
                 filter_greenfield: bool = True, use_llm_detector: bool = False, use_llm_filter: bool = False,
                 llm_filter_model: str = "gpt-5-mini", file_names: Optional[list[str]] = None) -> None:
        self.repo_paths = repo_paths
        self.output_path = output_path
        self.context = context
        self.patterns = patterns
        self.use_heuristic = use_heuristic
        self.dpdf_dataset_path = dpdf_dataset_path
        self.dpdf_project_name = dpdf_project_name
        self.filter_greenfield = filter_greenfield
        self.use_llm_detector = use_llm_detector
        self.use_llm_filter = use_llm_filter
        self.llm_filter_model = llm_filter_model
        self.file_names = file_names

        self.all_records: list[dict] = []
        self.existing_keys: set[tuple] = set()
        self.instance_id: int = 1

    def run(self) -> list[dict]:
        """Execute the pipeline across all repositories."""
        self._initialize_records()
        
        for repo_path in self.repo_paths:
            if not repo_path.exists():
                logger.error("Repo path does not exist: %s", repo_path)
                continue

            logger.info("━━━ Processing %s ━━━", repo_path.name)
            
            # Update context for the current repo
            self.context.repo_path = repo_path
            
            instances = self._phase1_detection()
            if not instances:
                logger.info("  No pattern instances found; skipping.")
                continue

            birth_infos = self._phase2_birth_discovery(instances)
            self._phase3_filtering(repo_path, birth_infos)

        self._finalize()
        return self.all_records

    def _initialize_records(self) -> None:
        """Load existing records and determine starting ID."""
        if self.output_path.exists():
            try:
                with open(self.output_path, "r") as f:
                    self.all_records = json.load(f)
                logger.info("Loaded %d existing records from %s", len(self.all_records), self.output_path)
            except Exception as e:
                logger.warning("Could not load existing output file: %s", e)

        if self.all_records:
            self.instance_id = max(r.get("id", 0) for r in self.all_records) + 1

        for r in self.all_records:
            key = (r["repo_path"], r["pattern"], r["pattern_file"], r["birth_commit_sha"])
            self.existing_keys.add(key)

    def _phase1_detection(self) -> list[PatternInstance]:
        """Phase 1: Detect pattern instances via seeds or heuristics."""
        instances: list[PatternInstance] = []

        if self.dpdf_dataset_path and self.dpdf_project_name:
            dpdf_det = DpdfDatasetDetector(
                context=self.context,
                dataset_path=self.dpdf_dataset_path,
                project_name=self.dpdf_project_name,
            )
            dpdf_instances = dpdf_det.detect()
            instances.extend(dpdf_instances)
            logger.info("  Phase 1 (dpdf seed): %d instances", len(dpdf_instances))

        if self.use_heuristic:
            # We use the convenience wrapper which now uses the context
            heuristic_instances = detect_patterns(
                context=self.context,
                llm_model=self.context.model_name if self.use_llm_detector else None,
                file_names=self.file_names,
            )
            # detect_patterns returns new instances, but we need to update our internal cache object
            # because detect_patterns creates a temporary context.
            # Ideally we'd call the detectors directly here.
            instances.extend(heuristic_instances)
            logger.info("  Phase 1 (heuristic): %d total instances found", len(heuristic_instances))

        if self.patterns:
            pattern_values = {p.value if hasattr(p, "value") else p for p in self.patterns}
            before = len(instances)
            instances = [
                i for i in instances
                if (i.pattern.value if hasattr(i.pattern, "value") else i.pattern) in pattern_values
            ]
            logger.info("  After pattern filter: %d / %d", len(instances), before)

        return instances

    def _phase2_birth_discovery(self, instances: list[PatternInstance]) -> list[BirthInfo]:
        """Phase 2: Find birth commits for detected instances."""
        logger.info("  Phase 2: Finding birth commits for %d instances …", len(instances))
        birth_finder = BirthFinder(context=self.context)
        birth_infos = birth_finder.find_all(instances)
        logger.info("  Phase 2 complete: %d birth commits resolved", len(birth_infos))
        return birth_infos

    def _phase3_filtering(self, repo_path: Path, birth_infos: list[BirthInfo]) -> None:
        """Phase 3: Apply greenfield/refactoring filters and save results."""
        logger.info("  Phase 3: Applying greenfield filter …")
        
        llm_filter = None
        if self.use_llm_filter:
            logger.info("Initializing LLM filter")
            llm_filter = LLMFilter()

        gf_filter = GreenfieldFilter(context=self.context, llm_filter=llm_filter)
        verdicts = gf_filter.evaluate_all(birth_infos)

        accepted = rejected = dups = 0
        for birth_info, verdict in verdicts:
            p_inst = birth_info.pattern_instance
            pattern_str = p_inst.pattern.value if hasattr(p_inst.pattern, "value") else str(p_inst.pattern)
            key = (str(repo_path), pattern_str, p_inst.file_path, birth_info.birth_commit_sha)

            if self.filter_greenfield and not verdict.is_likely_refactoring:
                logger.info(
                    "  ✗ Greenfield-rejected: %s (%s)  reasons=%s",
                    birth_info.pattern_instance.class_name,
                    birth_info.birth_commit_sha[:8],
                    verdict.rejection_reasons,
                )
                rejected += 1
                continue

            if key in self.existing_keys:
                dups += 1
                continue

            record = _to_output_record(repo_path, birth_info, verdict, self.instance_id)
            self.all_records.append(record)
            self.existing_keys.add(key)
            self.instance_id += 1
            accepted += 1

            status = "✓ refactoring" if verdict.is_likely_refactoring else "? greenfield"
            logger.info(
                "  [%s] %s  commit=%s  3A=%d mods  3B=%s siblings",
                status,
                birth_info.pattern_instance.class_name,
                birth_info.birth_commit_sha[:8],
                verdict.modified_preexisting_java_count,
                verdict.preexisting_sibling_count,
            )

        logger.info(
            "  Repo done: %d accepted, %d rejected (greenfield), %d skipped (duplicates)",
            accepted, rejected, dups
        )

    def _finalize(self) -> None:
        """Save results and caches."""
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, "w") as f:
            json.dump(self.all_records, f, indent=2, default=str)

        logger.info("saving cache")
        self.context.cache_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.context.save_cache()
            logger.info("Saved LLM cache with %d entries to %s", len(self.context.cache), self.context.cache_path)
        except Exception as e:
            logger.error("Could not save LLM cache: %s", e)


def run_pattern_first_mining(
    repo_paths: list[Path],
    output_path: Path,
    patterns: Optional[list[GoFPattern]],
    use_heuristic: bool,
    dpdf_dataset_path: Optional[Path],
    dpdf_project_name: Optional[str],
    filter_greenfield: bool,
    use_llm_detector: bool = False,
    llm_detector_model: str = "gpt-5-mini",
    use_llm_filter: bool = False,
    llm_filter_model: str = "gpt-5-mini",
    max_new_patterns: int = 10,
    cache_path: Path = refagent.data_folder.joinpath("design_patterns/llm_pattern_cache.json"),
    file_names: Optional[list[str]] = None,
) -> list[dict]:
    """
    Thin wrapper over PatternMiningPipeline for backward compatibility.
    """
    # Initialize cache
    cache_data = {}
    if use_llm_detector and cache_path and cache_path.exists():
        try:
            with open(cache_path, "r") as f:
                cache_data = json.load(f)
        except Exception as e:
            logger.warning("Could not load LLM cache: %s", e)
    
    context = MiningContext(
        repo_path=repo_paths[0] if repo_paths else Path("."),
        cache=PatternCache(cache_data),
        model_name=llm_detector_model,
        max_new_patterns=max_new_patterns,
        cache_path=cache_path,
    )

    pipeline = PatternMiningPipeline(repo_paths=repo_paths, output_path=output_path, context=context, patterns=patterns,
                                     use_heuristic=use_heuristic, dpdf_dataset_path=dpdf_dataset_path,
                                     dpdf_project_name=dpdf_project_name, filter_greenfield=filter_greenfield,
                                     use_llm_detector=use_llm_detector, use_llm_filter=use_llm_filter,
                                     llm_filter_model=llm_filter_model, file_names=file_names)
    return pipeline.run()


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def _print_summary(records: list[dict], output_path: Path) -> None:
    total = len(records)
    refactoring_count = sum(1 for r in records if r["greenfield"]["is_likely_refactoring"])
    pattern_counts = Counter(r["pattern"] for r in records)

    logger.info("─── Pattern-First Mining Summary ───────────────")
    logger.info("Total records written : %d  →  %s", total, output_path)
    logger.info("Likely refactoring    : %d / %d", refactoring_count, total)
    logger.info("Breakdown by pattern  :")
    for pat, count in sorted(pattern_counts.items(), key=lambda x: -x[1]):
        logger.info("  %-22s %d", pat, count)
    logger.info("────────────────────────────────────────────────")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="mine_from_pattern",
        description="Pattern-first pipeline: detect patterns → find birth commit → filter greenfield.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--repos", nargs="+", type=Path, required=True, metavar="PATH",
        help="One or more paths to locally-cloned Java git repositories.",
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path("data/design_patterns/pf_candidates.json"),
        help="Output JSON file (default: data/design_patterns/pf_candidates.json).",
    )

    # Phase 1 options
    phase1 = parser.add_argument_group("Phase 1 – Pattern Detection")
    phase1.add_argument(
        "--no-heuristic", action="store_true",
        help="Disable class-name heuristic scan (Phase 1A). Requires --dpdf-dataset.",
    )
    phase1.add_argument(
        "--use-llm-detector", action="store_true",
        help="Use LLM to validate the pattern structure in Phase 1B.",
    )
    phase1.add_argument(
        "--llm-detector-model", type=str, default="gpt-5-mini",
        help="LLM model name to use for pattern validation (Phase 1B).",
    )
    phase1.add_argument(
        "--max-new-patterns", type=int, default=10,
        help="Maximum number of new patterns to discover and validate per repository.",
    )
    phase1.add_argument(
        "--cache-path", type=Path,
        default=refagent.data_folder.joinpath("design_patterns/llm_pattern_cache.json"),
        help="Path to the JSON file for caching LLM validation results.",
    )
    phase1.add_argument(
        "--dpdf-dataset", type=Path, metavar="PATH",
        help="Path to dpdf_dataset_filtered.json to seed known pattern instances.",
    )
    phase1.add_argument(
        "--dpdf-project", type=str, metavar="PROJECT_NAME",
        help="Project name inside the dpdf dataset to filter on (e.g. 'cxf').",
    )
    phase1.add_argument(
        "--patterns", nargs="*",
        choices=[p.value for p in GoFPattern], metavar="PATTERN",
        help="Only detect/report these patterns (e.g. --patterns Builder Strategy).",
    )
    phase1.add_argument(
        "--file_names", nargs="*",
        help="Run the pipeline on these files. ",
    )

    # Phase 3 options
    phase3 = parser.add_argument_group("Phase 3 – Greenfield Filter")
    phase3.add_argument(
        "--filter-greenfield", action="store_true",
        help="Exclude instances that are likely greenfield (both 3A and 3B fail).",
    )
    phase3.add_argument(
        "--use-llm-filter", action="store_true",
        help="Use LLM (gpt-5-mini) to further filter greenfield vs refactoring commits.",
    )
    phase3.add_argument(
        "--llm-filter-model", type=str, default="gpt-5-mini",
        help="LLM model name to use for greenfield filtering (Phase 3).",
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

    if args.no_heuristic and not args.dpdf_dataset:
        raise SystemExit("--no-heuristic requires --dpdf-dataset to be specified.")

    patterns = [GoFPattern(p) for p in args.patterns] if args.patterns else None

    run_pattern_first_mining(
        repo_paths=args.repos,
        output_path=args.output,
        patterns=patterns,
        use_heuristic=not args.no_heuristic,
        dpdf_dataset_path=args.dpdf_dataset,
        dpdf_project_name=args.dpdf_project,
        filter_greenfield=args.filter_greenfield,
        use_llm_detector=args.use_llm_detector,
        llm_detector_model=args.llm_detector_model,
        use_llm_filter=args.use_llm_filter,
        llm_filter_model=args.llm_filter_model,
        max_new_patterns=args.max_new_patterns,
        cache_path=args.cache_path,
        file_names=args.file_names,
    )
