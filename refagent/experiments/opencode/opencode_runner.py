"""
Opencode runner for CorenameBench.

Mirrors codex_runner.py but drives `opencode run` instead of `codex exec`.

Key differences from codex_runner
----------------------------------
- No IntelliJ MCP (opencode has its own toolset including jdtls when available).
- No IntelliJ server interaction — no open_project / reload_project calls.
- Approval flag: --dangerously-skip-permissions (equivalent of danger-full-access).
- Output format: `--format json` emits JSONL with types:
    step_start, text, tool_use, step_finish
  Token usage is on step_finish parts (not a separate event).

Usage
-----
  # Single project
  PYTHONPATH=. .venv/bin/python refagent/experiments/opencode/opencode_runner.py \\
      --json-file  data/uncontaminated/flink.json \\
      --output-file data/results/opencode_o4-mini-jun-21/flink.json

  # All uncontaminated projects
  PYTHONPATH=. .venv/bin/python refagent/experiments/opencode/opencode_runner.py \\
      --all-projects --run-identifier opencode_o4-mini-jun-21
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import refagent
import refagent.utils.project_manager as pm
from refagent.experiments.prompts import parse_seed_name, build_agent_prompt

OPENCODE_BIN = os.environ.get(
    "OPENCODE_BIN", "/Users/abhiram/.opencode/bin/opencode"
)

# ---------------------------------------------------------------------------
# Pricing table (USD per 1 M tokens)
# ---------------------------------------------------------------------------
MODEL_PRICING: dict[str, dict[str, float]] = {
    "o4-mini":      {"input": 1.10,  "cached_input": 0.275, "output": 4.40},
    "o3":           {"input": 10.00, "cached_input": 2.50,  "output": 40.00},
    "gpt-4o":       {"input": 2.50,  "cached_input": 1.25,  "output": 10.00},
    "gpt-4o-mini":  {"input": 0.15,  "cached_input": 0.075, "output": 0.60},
    "gpt-5.4-mini": {"input": 0.40,  "cached_input": 0.10,  "output": 1.60},
    "gpt-5":        {"input": 15.00, "cached_input": 3.75,  "output": 60.00},
}

PROJECTS_BASE_PATH = Path(
    os.environ.get("PROJECTS_BASE_PATH", str(refagent.data_folder))
)
DEFAULT_BENCHMARK_DIR = str(refagent.data_folder / "uncontaminated")


# ---------------------------------------------------------------------------
# Cost helper
# ---------------------------------------------------------------------------

def _compute_cost(model: str, input_tokens: int, cached_tokens: int, output_tokens: int) -> float:
    lookup = model.split("-202")[0]
    pricing = MODEL_PRICING.get(lookup) or MODEL_PRICING.get(model)
    if pricing is None:
        return -1.0
    non_cached = max(input_tokens - cached_tokens, 0)
    return (
        non_cached      * pricing["input"]
        + cached_tokens * pricing["cached_input"]
        + output_tokens * pricing["output"]
    ) / 1_000_000


# ---------------------------------------------------------------------------
# JSONL event-stream processing
#
# opencode --format json emits one JSON object per line:
#
#   {"type":"step_start",  "part": {...}}
#   {"type":"text",        "part": {"type":"text", "text":"...", ...}}
#   {"type":"tool_use",    "part": {"type":"tool",  "tool":"bash"|"read"|"edit"|...,
#                                   "state":{"status":"completed","input":{...},"output":"..."}}}
#   {"type":"step_finish", "part": {"type":"step-finish", "reason":"stop"|"tool-calls",
#                                   "tokens":{"total":N,"input":N,"output":N,
#                                             "cache":{"write":N,"read":N}},
#                                   "cost": <float USD for this step>}}
#
# Tokens on step_finish are per-step deltas; we sum across all steps.
# Cost on step_finish is also per-step; we sum it (more accurate than our
# pricing table since opencode uses the provider's reported cost).
# ---------------------------------------------------------------------------

def _process_event(obj: dict, state: dict) -> None:
    """Update running state from one parsed JSONL event."""
    event_type = obj.get("type", "")
    part = obj.get("part", {})

    if event_type == "step_finish":
        tok = part.get("tokens", {})
        state["total_input"]   += tok.get("input", 0)
        state["total_output"]  += tok.get("output", 0)
        state["total_cached"]  += tok.get("cache", {}).get("read", 0)
        state["total_tokens"]  += tok.get("total", 0)
        state["total_cost_usd"] += part.get("cost", 0.0)

    elif event_type == "text":
        state["last_message"] = part.get("text", state["last_message"])

    elif event_type == "tool_use":
        tool = part.get("tool", "unknown")
        state["tool_calls"].append({
            "tool":   tool,
            "input":  part.get("state", {}).get("input", {}),
            "output": str(part.get("state", {}).get("output", ""))[:300],
        })


def _relay_line(obj: dict) -> Optional[str]:
    """Return a human-readable one-liner for key events, or None to stay silent."""
    event_type = obj.get("type", "")
    part = obj.get("part", {})

    if event_type == "step_start":
        return "[opencode] ▶ step started"

    if event_type == "step_finish":
        tok = part.get("tokens", {})
        cost = part.get("cost", 0.0)
        return (
            f"[opencode] ✔ step finished  "
            f"in={tok.get('input',0)} out={tok.get('output',0)} "
            f"cost=${cost:.4f}"
        )

    if event_type == "text":
        text = part.get("text", "").strip()
        if text:
            preview = text[:200] + ("…" if len(text) > 200 else "")
            return f"[opencode] 💬 {preview}"

    if event_type == "tool_use":
        tool = part.get("tool", "?")
        inp  = part.get("state", {}).get("input", {})
        # Surface the most useful field per tool type
        if tool == "bash":
            detail = inp.get("command", "")[:120]
        elif tool in ("read", "edit", "write"):
            detail = inp.get("filePath", inp.get("path", ""))
        else:
            detail = str(inp)[:100]
        return f"[opencode] 🔧 {tool}({detail})"

    return None


# ---------------------------------------------------------------------------
# Live-streaming runner
# ---------------------------------------------------------------------------

def _run_opencode_streaming(
    cmd: list[str],
    raw_log_path: Path,
    item_id,
    timeout_sec: int,
) -> tuple[dict, float]:
    """
    Run opencode, stream JSONL line-by-line, relay key events to terminal,
    write every line to raw_log_path, and return (summary, wall_elapsed).
    """
    state = {
        "total_input": 0, "total_cached": 0,
        "total_output": 0, "total_tokens": 0,
        "total_cost_usd": 0.0,
        "last_message": "", "tool_calls": [],
    }

    raw_log_path.parent.mkdir(parents=True, exist_ok=True)
    wall_start  = time.monotonic()
    timed_out   = False

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    stderr_lines: list[str] = []
    def _drain_stderr():
        for line in proc.stderr:
            stderr_lines.append(line)
    threading.Thread(target=_drain_stderr, daemon=True).start()

    deadline = wall_start + timeout_sec

    with open(raw_log_path, "w") as log_fh:
        for raw_line in proc.stdout:
            log_fh.write(raw_line)
            log_fh.flush()

            raw_line = raw_line.strip()
            if not raw_line:
                continue

            if time.monotonic() > deadline:
                print(f"[opencode] ⚠️  Timeout ({timeout_sec}s) — killing process")
                proc.kill()
                timed_out = True
                break

            try:
                obj = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            _process_event(obj, state)

            msg = _relay_line(obj)
            if msg:
                print(msg)

    if not timed_out:
        proc.wait()

    wall_elapsed = time.monotonic() - wall_start

    if proc.returncode and proc.returncode != 0:
        print(f"[opencode] ⚠️  exit code {proc.returncode}")
        if stderr_lines:
            print(f"[opencode] stderr: {''.join(stderr_lines[:5])}")

    # Build tool-call counts summary
    tool_counts: dict[str, int] = {}
    for call in state["tool_calls"]:
        t = call["tool"]
        tool_counts[t] = tool_counts.get(t, 0) + 1

    summary = {
        "token_usage": {
            "input_tokens":        state["total_input"],
            "cached_input_tokens": state["total_cached"],
            "output_tokens":       state["total_output"],
            "total_tokens":        state["total_tokens"],
        },
        "last_message":   state["last_message"],
        "tool_calls":     state["tool_calls"],
        "tool_counts":    tool_counts,
        "total_cost_usd": state["total_cost_usd"],
    }
    return summary, wall_elapsed


# ---------------------------------------------------------------------------
# Core: run opencode on one benchmark item
# ---------------------------------------------------------------------------

def process_item(
    item_data: dict,
    model: Optional[str],
    raw_log_dir: Path,
    timeout_sec: int = 900,
) -> Optional[dict]:
    item_id       = item_data.get("id", "unknown")
    project_name  = item_data.get("project")
    v1_hash       = item_data.get("v1_hash")
    starting_file = item_data.get("starting_file")
    seed_example  = item_data.get("seed_example")

    if seed_example and seed_example.get("type") == "Rename Class":
        starting_file = seed_example["leftSideLocations"][0]["filePath"]
        print(f"[Setup] Rename Class seed — using starting_file: {starting_file}")

    if not all([project_name, v1_hash, starting_file, seed_example]):
        print(f"[Setup] ❌ Missing required fields in item {item_id}")
        return None

    # --- 1. Checkout ---
    try:
        project = pm.EvalProject(project_name)
        project.restore_changes()
        project.checkout(v1_hash, force=True)
        print(f"[Git] ✅ Checked out {v1_hash[:8]} for item {item_id}")
    except Exception as e:
        print(f"[Git] ❌ Checkout failed for item {item_id}: {e}")
        return None

    # --- 2. Build prompt ---
    old_name, new_name = parse_seed_name(seed_example)
    print(f"[Seed] {old_name} -> {new_name}")
    # include_mcp_note=False — opencode uses its own toolset, not IntelliJ MCP
    prompt = build_agent_prompt(
        item_data=item_data,
        starting_file=starting_file,
        old_name=old_name,
        new_name=new_name,
        include_mcp_note=False,
    )

    # --- 3. Run opencode (streaming) ---
    raw_log_path = raw_log_dir / f"item_{item_id}.jsonl"
    cmd = [
        OPENCODE_BIN, "run",
        "--format", "json",
        "--dir", str(project.get_project_path()),
        "--dangerously-skip-permissions",
        prompt.as_single_string(),
    ]
    if model:
        cmd += ["--model", model]

    print(f"[opencode] Starting — raw log → {raw_log_path}")
    summary, wall_elapsed = _run_opencode_streaming(
        cmd, raw_log_path, item_id, timeout_sec
    )

    tok           = summary["token_usage"]
    input_tokens  = tok["input_tokens"]
    cached_tokens = tok["cached_input_tokens"]
    output_tokens = tok["output_tokens"]
    total_tokens  = tok["total_tokens"]
    # Prefer opencode's own reported cost; fall back to our pricing table
    cost_usd = summary["total_cost_usd"] or _compute_cost(
        model or "unknown", input_tokens, cached_tokens, output_tokens
    )
    tool_counts     = summary["tool_counts"]
    total_tool_calls = sum(tool_counts.values())

    print(f"[opencode] Wall time: {wall_elapsed:.1f}s")
    print(
        f"[Tokens]   input={input_tokens} cached={cached_tokens} "
        f"output={output_tokens} total={total_tokens} cost=${cost_usd:.4f}"
    )
    print(f"[Tools]    {total_tool_calls} calls: {tool_counts}")

    # --- 4. Commit ---
    try:
        changed = project.get_changed_files()
        if changed:
            print(f"[Git] Staging all changes ({len(changed)} file(s))")
        else:
            print("[Git] ⚠️  No changed files detected after opencode run")
        commit_msg = f"opencode: rename {old_name} -> {new_name} (item {item_id})"
        commit_hash = project.commit_all(commit_msg)
        print(f"[Git] ✅ Committed as {commit_hash}")
    except Exception as e:
        print(f"[Git] ❌ Commit failed for item {item_id}: {e}")
        commit_hash = None

    return {
        "id": item_id,
        "response": {
            "commit_hash": str(commit_hash) if commit_hash else None,
            "stats": {
                "wall_time_sec":       round(wall_elapsed, 2),
                "input_tokens":        input_tokens,
                "cached_input_tokens": cached_tokens,
                "output_tokens":       output_tokens,
                "total_tokens":        total_tokens,
                "cost_usd":            round(cost_usd, 6),
                "model":               model or "opencode-default",
                "tool_counts":         tool_counts,
                "total_tool_calls":    total_tool_calls,
            },
        },
    }


# ---------------------------------------------------------------------------
# Per-file runner
# ---------------------------------------------------------------------------

def run_benchmark_file(
    json_file: str,
    output_file: str,
    model: Optional[str],
    max_items: Optional[int] = None,
    ref_ids: Optional[list[int]] = None,
    force_run: bool = False,
    codex_timeout_sec: int = 900,
) -> None:
    json_file   = Path(json_file)
    output_file = Path(output_file)

    print(f"\n{'='*60}")
    print(f"Benchmark : {json_file.name}")
    print(f"Output    : {output_file}")
    print(f"Model     : {model or 'opencode default'}")
    print(f"{'='*60}\n")

    with open(json_file) as f:
        all_items: list[dict] = json.load(f)

    results: list[dict] = []
    if output_file.exists() and not force_run:
        with open(output_file) as f:
            results = json.load(f)
    cached_ids: set = {r["id"] for r in results}

    project_name = all_items[0]["project"] if all_items else json_file.stem

    items_to_process = all_items
    if max_items is not None:
        items_to_process = items_to_process[:max_items]
    if ref_ids is not None:
        items_to_process = [i for i in items_to_process if i.get("id") in ref_ids]

    pending = [i for i in items_to_process if force_run or i.get("id") not in cached_ids]
    if not pending:
        print(f"[{project_name}] Nothing to process.")
        return

    raw_log_dir = output_file.parent / "logs" / json_file.stem
    print(f"[{project_name}] Raw opencode logs → {raw_log_dir}/")

    output_file.parent.mkdir(parents=True, exist_ok=True)

    success = 0
    for idx, item in enumerate(pending):
        item_id = item.get("id", "?")
        print(f"\n--- [{project_name}] Item {idx+1}/{len(pending)}  id={item_id} ---")

        result = process_item(
            item,
            model=model,
            raw_log_dir=raw_log_dir,
            timeout_sec=codex_timeout_sec,
        )
        if result:
            results.append(result)
            success += 1
            with open(output_file, "w") as f:
                json.dump(results, f, indent=4)
            print(f"[Save] ✅ {len(results)} results → {output_file}")
        else:
            print(f"[{project_name}] ❌ Failed item {item_id}")

    print(f"\n[{project_name}] Done: {success}/{len(pending)} succeeded.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run opencode agent on CorenameBench and save results."
    )
    parser.add_argument("--json-file",   type=str, default=None)
    parser.add_argument("--output-file", type=str, default=None)
    parser.add_argument("--all-projects", action="store_true")
    parser.add_argument("--benchmark-dir", type=str, default=DEFAULT_BENCHMARK_DIR)
    parser.add_argument("--run-identifier", type=str, default="opencode_default")
    parser.add_argument(
        "--model", type=str, default=None,
        help="Model in provider/model format, e.g. openai/o4-mini. "
             "Omit to use opencode's configured default.",
    )
    parser.add_argument("--max-items", type=int, default=None)
    parser.add_argument(
        "--ref-ids", type=str, default=None,
        help='Comma-separated benchmark IDs, e.g. "2001,2012".',
    )
    parser.add_argument("--force-run", action="store_true")
    parser.add_argument("--timeout-sec", type=int, default=900,
                        help="Per-item timeout for opencode run (seconds).")
    args = parser.parse_args()

    ref_ids = [int(x) for x in args.ref_ids.split(",")] if args.ref_ids else None

    common = dict(
        model=args.model,
        max_items=args.max_items,
        ref_ids=ref_ids,
        force_run=args.force_run,
        codex_timeout_sec=args.timeout_sec,
    )

    if args.all_projects:
        benchmark_dir   = Path(args.benchmark_dir)
        results_base    = refagent.data_folder / "results" / args.run_identifier
        benchmark_files = sorted(benchmark_dir.glob("*.json"))
        if not benchmark_files:
            print(f"No .json files found in {benchmark_dir}", file=sys.stderr)
            sys.exit(1)
        for bf in benchmark_files:
            run_benchmark_file(str(bf), str(results_base / bf.name), **common)

    elif args.json_file:
        if not args.output_file:
            parser.error("--output-file is required with --json-file")
        run_benchmark_file(args.json_file, args.output_file, **common)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
