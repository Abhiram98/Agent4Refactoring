"""
Aggregate report-*.json files produced by evaluate_agent.py into a single
benchmark-wide precision / recall / F1 score, computed from raw TP/FP/FN totals.

Usage:
    python aggregate_reports.py <results_dir>

The script scans <results_dir> for files matching report-*.json, tallies the
raw counts from each file's "summary" block, and prints the final numbers.
"""

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aggregate per-file report JSONs into benchmark-wide metrics."
    )
    parser.add_argument(
        "results_dir",
        type=str,
        help="Directory containing report-*.json files",
    )
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    report_files = sorted(results_dir.glob("report-*.json"))

    if not report_files:
        print(f"No report-*.json files found in {results_dir}", file=sys.stderr)
        sys.exit(1)

    total_tp = 0
    total_fp = 0
    total_fn = 0
    loaded = []

    for path in report_files:
        with open(path) as f:
            data = json.load(f)

        # Support both the new {summary, results} format and the old bare-list format
        if isinstance(data, dict) and "summary" in data:
            summary = data["summary"]
            tp = summary["total_tp"]
            fp = summary["total_fp"]
            fn = summary["total_fn"]
        elif isinstance(data, list):
            # Fall back to summing raw counts from each result entry
            tp = sum(r.get("tp_count", 0) for r in data)
            fp = sum(r.get("fp_count", 0) for r in data)
            fn = sum(
                r.get("oracle_count", 0) - r.get("tp_count", 0) for r in data
            )
        else:
            print(f"Skipping {path.name}: unrecognised format", file=sys.stderr)
            continue

        loaded.append((path.name, tp, fp, fn))
        total_tp += tp
        total_fp += fp
        total_fn += fn

    # Per-file breakdown
    print(f"{'File':<45} {'TP':>6} {'FP':>6} {'FN':>6}")
    print("-" * 67)
    for name, tp, fp, fn in loaded:
        print(f"{name:<45} {tp:>6} {fp:>6} {fn:>6}")
    print("-" * 67)

    # Benchmark-wide aggregates
    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    recall    = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    f1        = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    print()
    print("=" * 45)
    print("BENCHMARK-WIDE AGGREGATE (raw counts)")
    print("=" * 45)
    print(f"  Total TP        : {total_tp}")
    print(f"  Total FP        : {total_fp}")
    print(f"  Total FN        : {total_fn}")
    print(f"  Total Precision : {precision:.4f}")
    print(f"  Total Recall    : {recall:.4f}")
    print(f"  Total F1 Score  : {f1:.4f}")
    print("=" * 45)


if __name__ == "__main__":
    main()
