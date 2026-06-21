#!/usr/bin/env bash
# Evaluate all result JSONs produced by codex_runner.py and aggregate.
#
# Usage:
#   ./evaluate.sh <run_identifier>
#   ./evaluate.sh codex_o4-mini-jun-20

set -euo pipefail

#RUN_IDENTIFIER=""
RESULTS_DIR="/Users/abhiram/Documents/TBE/RefactoringAgentProject/Agent4Refactoring/data/results/codex_o4-mini-jun-20"
BENCHMARK_DIR="/Users/abhiram/Documents/TBE/RefactoringAgentProject/Agent4Refactoring/data/uncontaminated"
PYTHON="/Users/abhiram/Documents/TBE/RefactoringAgentProject/ref_venv/bin/python"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ ! -d "$RESULTS_DIR" ]]; then
  echo "Results directory not found: $RESULTS_DIR"
  exit 1
fi

for f in "$RESULTS_DIR"/*.json; do
  name=$(basename "$f")
  [[ "$name" == report-* ]] && continue
  benchmark_file="$BENCHMARK_DIR/$name"
  if [[ ! -f "$benchmark_file" ]]; then
    echo "Skipping $name: no matching benchmark file found in $BENCHMARK_DIR"
    continue
  fi
  echo "Evaluating $name ..."
  "$PYTHON" \
    /Users/abhiram/Documents/TBE/RefactoringAgentProject/Agent4Refactoring/refagent/experiments/evaluate_agent.py \
    "$f" \
    --without-seed \
    --benchmark_file_path "$benchmark_file"
done

echo ""
echo "Aggregating reports..."
"$PYTHON" "$SCRIPT_DIR/../vanilla/aggregate_reports.py" "$RESULTS_DIR"
