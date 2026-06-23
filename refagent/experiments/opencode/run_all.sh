#!/usr/bin/env bash
# Run opencode_runner.py on every benchmark file in data/uncontaminated/.
#
# Usage:
#   ./run_all.sh [run_identifier]
#
# Examples:
#   ./run_all.sh                          # uses default identifier below
#   ./run_all.sh opencode_o4-mini-jun-21

set -euo pipefail

# ---------------------------------------------------------------------------
# Config — edit these as needed
# ---------------------------------------------------------------------------
RUN_IDENTIFIER="${1:-opencode_o4-mini-jun-21}"

REPO=/Users/abhiram/Documents/TBE/RefactoringAgentProject/Agent4Refactoring
PYTHON=$REPO/.venv/bin/python
SCRIPT=$REPO/refagent/experiments/opencode/opencode_runner.py
BENCHMARK_DIR=$REPO/data/uncontaminated
RESULTS_DIR=$REPO/data/results/$RUN_IDENTIFIER

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
echo "Run identifier : $RUN_IDENTIFIER"
echo "Results dir    : $RESULTS_DIR"
echo ""

for benchmark_file in "$BENCHMARK_DIR"/*.json; do
    project=$(basename "$benchmark_file" .json)
    output_file="$RESULTS_DIR/$project.json"

    echo "=================================================="
    echo "Project : $project"
    echo "Input   : $benchmark_file"
    echo "Output  : $output_file"
    echo "=================================================="

    PYTHONPATH="$REPO" "$PYTHON" "$SCRIPT" \
        --json-file  "$benchmark_file" \
        --output-file "$output_file"

    echo ""
done

echo "All projects done."
