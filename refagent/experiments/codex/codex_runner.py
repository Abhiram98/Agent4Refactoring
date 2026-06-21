"""
Codex runner for CorenameBench.

Workflow per benchmark item
---------------------------
1. Checkout v1_hash, wait for IntelliJ to re-index.
2. Build a prompt pointing codex at the starting file + seed rename.
3. Run `codex exec --json` and stream its JSONL output line-by-line so that:
     • agent messages are printed live (no hung-looking terminal)
     • the full raw log is saved alongside results for debugging
4. Parse token usage and IntelliJ MCP call counts from the stream.
5. Commit whatever files were changed, save result JSON.

Benchmark sources
-----------------
  data/uncontaminated/*.json   — main corename benchmark (10 projects)
  data/renas/renas_oracle.json — renas oracle

Usage
-----
  # Single project
  PYTHONPATH=. .venv/bin/python refagent/experiments/codex/codex_runner.py \\
      --json-file  data/uncontaminated/flink.json \\
      --output-file data/results/codex_gpt-5.4-mini-jun-20/flink.json \\
      --model gpt-5.4-mini

  # All uncontaminated projects
  PYTHONPATH=. .venv/bin/python refagent/experiments/codex/codex_runner.py \\
      --all-projects --run-identifier codex_gpt-5.4-mini-jun-20 --model gpt-5.4-mini
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
import refagent.utils.intellij_server as ij_utils
from refagent.experiments.prompts import parse_seed_name, build_agent_prompt

# ---------------------------------------------------------------------------
# Pricing table (USD per 1 M tokens) — update as needed.
# Source: https://openai.com/api/pricing  (June 2026)
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
# JSONL event-stream parser
# ---------------------------------------------------------------------------

def _process_event(obj: dict, state: dict) -> None:
    """
    Update running state from one parsed JSONL event object.
    state keys: total_input, total_cached, total_output, total_tokens,
                last_message, mcp_tool_calls
    """
    event_type = obj.get("type", "")

    if event_type == "turn.completed":
        u = obj.get("usage", {})
        state["total_input"]   += u.get("input_tokens", 0)
        state["total_cached"]  += u.get("cached_input_tokens", 0)
        state["total_output"]  += u.get("output_tokens", 0)
        state["total_tokens"]  += u.get("input_tokens", 0) + u.get("output_tokens", 0)

    elif event_type == "item.completed":
        item = obj.get("item", {})
        item_type = item.get("type", "")

        if item_type == "agent_message":
            state["last_message"] = item.get("text", state["last_message"])

        elif item_type == "mcp_tool_call_end":
            inv = item.get("invocation", {})
            if inv.get("server") == "intellij_idea_mcp":
                state["mcp_tool_calls"].append({
                    "tool":      inv.get("tool", "unknown"),
                    "call_id":   item.get("call_id", ""),
                    "arguments": inv.get("arguments", {}),
                })


def _summarise_state(state: dict, model: str) -> dict:
    input_tokens  = state["total_input"]
    cached_tokens = state["total_cached"]
    output_tokens = state["total_output"]
    total_tokens  = state["total_tokens"]
    mcp_tool_calls = state["mcp_tool_calls"]

    mcp_call_counts: dict[str, int] = {}
    for call in mcp_tool_calls:
        t = call["tool"]
        mcp_call_counts[t] = mcp_call_counts.get(t, 0) + 1

    return {
        "token_usage": {
            "input_tokens":        input_tokens,
            "cached_input_tokens": cached_tokens,
            "output_tokens":       output_tokens,
            "total_tokens":        total_tokens,
        },
        "last_message":    state["last_message"],
        "mcp_tool_calls":  mcp_tool_calls,
        "mcp_call_counts": mcp_call_counts,
        "cost_usd":        _compute_cost(model, input_tokens, cached_tokens, output_tokens),
    }


# ---------------------------------------------------------------------------
# Live-streaming codex runner
# ---------------------------------------------------------------------------

# Events we surface to the terminal so the user can see progress.
_RELAY_ITEM_TYPES = {"agent_message", "mcp_tool_call_end", "error"}
_RELAY_TOP_TYPES  = {"turn.started", "turn.completed", "thread.started"}


def _relay_line(obj: dict) -> Optional[str]:
    """
    Return a human-readable summary of a JSONL event, or None to stay silent.
    Only a subset of events are relayed to avoid noise.
    """
    top = obj.get("type", "")

    if top == "turn.started":
        return "[Codex] ▶ turn started"

    if top == "turn.completed":
        u = obj.get("usage", {})
        return (
            f"[Codex] ✔ turn completed  "
            f"in={u.get('input_tokens',0)} out={u.get('output_tokens',0)}"
        )

    if top == "item.completed":
        item = obj.get("item", {})
        itype = item.get("type", "")

        if itype == "agent_message":
            text = item.get("text", "").strip()
            # Truncate long messages to keep the terminal readable
            preview = text[:200] + ("…" if len(text) > 200 else "")
            return f"[Codex] 💬 {preview}"

        if itype == "mcp_tool_call_end":
            inv = item.get("invocation", {})
            if inv.get("server") == "intellij_idea_mcp":
                args = inv.get("arguments", {})
                return f"[Codex] 🔧 MCP {inv.get('tool')}({args})"

        if itype == "error":
            return f"[Codex] ❌ error: {item.get('message','')}"

    return None


def _run_codex_streaming(
    cmd: list[str],
    raw_log_path: Path,
    item_id,
    timeout_sec: int,
    model: str,
) -> tuple[dict, float]:
    """
    Run codex, stream its stdout line-by-line, relay key events to the
    terminal, write every line to raw_log_path, and parse stats.

    Returns (summary_dict, wall_elapsed_seconds).
    """
    state = {
        "total_input": 0, "total_cached": 0,
        "total_output": 0, "total_tokens": 0,
        "last_message": "", "mcp_tool_calls": [],
    }

    raw_log_path.parent.mkdir(parents=True, exist_ok=True)
    wall_start = time.monotonic()
    timed_out = False

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,          # line-buffered
    )

    # Drain stderr in a background thread so it never blocks stdout reading.
    stderr_lines: list[str] = []
    def _drain_stderr():
        for line in proc.stderr:
            stderr_lines.append(line)
    threading.Thread(target=_drain_stderr, daemon=True).start()

    deadline = wall_start + timeout_sec

    with open(raw_log_path, "w") as log_fh:
        for raw_line in proc.stdout:
            # Write raw line unconditionally to the log file.
            log_fh.write(raw_line)
            log_fh.flush()

            raw_line = raw_line.strip()
            if not raw_line:
                continue

            # Check timeout
            if time.monotonic() > deadline:
                print(f"[Codex] ⚠️  Timeout ({timeout_sec}s) reached — killing process")
                proc.kill()
                timed_out = True
                break

            # Parse and update state
            try:
                obj = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            _process_event(obj, state)

            # Relay to terminal
            msg = _relay_line(obj)
            if msg:
                print(msg)

    if not timed_out:
        proc.wait()

    wall_elapsed = time.monotonic() - wall_start

    if proc.returncode and proc.returncode != 0:
        print(f"[Codex] ⚠️  exit code {proc.returncode}")
        if stderr_lines:
            print(f"[Codex] stderr: {''.join(stderr_lines[:5])}")

    summary = _summarise_state(state, model)
    return summary, wall_elapsed


# ---------------------------------------------------------------------------
# IntelliJ helpers
# ---------------------------------------------------------------------------

def _open_and_index(
    project_name: str,
    ij_server: ij_utils.IntellijServer,
    initial_wait_sec: int = 10,
) -> None:
    project_path = PROJECTS_BASE_PATH / project_name
    print(f"[IntelliJ] Opening {project_path} ...")
    subprocess.Popen(
        ["open", "-na", "/Applications/IntelliJ IDEA2025.2.app", "--args", str(project_path)]
    )
    print(f"[IntelliJ] Waiting {initial_wait_sec}s for IntelliJ to come up ...")
    time.sleep(initial_wait_sec)
    _wait_for_index(project_name, ij_server)


def _wait_for_index(project_name: str, ij_server: ij_utils.IntellijServer) -> None:
    project_path = PROJECTS_BASE_PATH / project_name
    print(f"[IntelliJ] Signalling open_project for {project_name} ...")
    ij_server.open_project(project_path=project_path)
    ij_server.reset_project_reload_counters()
    print("[IntelliJ] Waiting for indexing ...")
    ij_server.reload_project()
    print("[IntelliJ] Indexing complete.")


# ---------------------------------------------------------------------------
# Core: run codex on one benchmark item
# ---------------------------------------------------------------------------

def process_item(
    item_data: dict,
    model: str,
    ij_server: ij_utils.IntellijServer,
    raw_log_dir: Path,
    timeout_sec: int = 300,
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

    # --- 2. Re-index ---
    _wait_for_index(project_name, ij_server)

    # --- 3. Build prompt ---
    old_name, new_name = parse_seed_name(seed_example)
    print(f"[Seed] {old_name} -> {new_name}")
    prompt = build_agent_prompt(
        item_data=item_data,
        starting_file=starting_file,
        old_name=old_name,
        new_name=new_name,
    )

    # --- 4. Run codex (streaming) ---
    raw_log_path = raw_log_dir / f"item_{item_id}.jsonl"
    cmd = [
        "codex", "exec",
        "--json",
        "-m", model,
        "-C", str(project.get_project_path()),
        "--sandbox", "danger-full-access",
        "-c", 'approvals_reviewer="auto_review"',
        "-c", 'mcp_servers.intellij_idea_mcp.tools.find_files_by_name_keyword.approval_mode="auto"',
        "-c", 'mcp_servers.intellij_idea_mcp.tools.rename_refactoring.approval_mode="auto"',
        prompt.as_single_string(),
    ]

    print(f"[Codex] Starting — raw log → {raw_log_path}")
    summary, wall_elapsed = _run_codex_streaming(
        cmd, raw_log_path, item_id, timeout_sec, model
    )

    tok             = summary["token_usage"]
    input_tokens    = tok["input_tokens"]
    cached_tokens   = tok["cached_input_tokens"]
    output_tokens   = tok["output_tokens"]
    total_tokens    = tok["total_tokens"]
    cost_usd        = summary["cost_usd"]
    mcp_call_counts = summary["mcp_call_counts"]
    total_mcp_calls = sum(mcp_call_counts.values())

    print(f"[Codex] Wall time: {wall_elapsed:.1f}s")
    print(
        f"[Tokens] input={input_tokens} cached={cached_tokens} "
        f"output={output_tokens} total={total_tokens} cost=${cost_usd:.4f}"
    )
    print(f"[MCP]    intellij calls: {total_mcp_calls}  breakdown: {mcp_call_counts}")

    # --- 5. Commit ---
    try:
        # Use commit_all (git add -A + commit) rather than selectively staging
        # get_changed_files() output. IntelliJ's rename_refactoring can produce
        # renamed/moved files where the status line format breaks selective
        # staging, and untracked new files are missed entirely by git add <file>.
        changed = project.get_changed_files()
        if changed:
            print(f"[Git] Staging all changes ({len(changed)} file(s) reported by git status)")
        else:
            print("[Git] ⚠️  No changed files detected after codex run")
        commit_msg = f"codex: rename {old_name} -> {new_name} (item {item_id})"
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
                "model":               model,
                "mcp_call_counts":     mcp_call_counts,
                "total_mcp_calls":     total_mcp_calls,
            },
        },
    }


# ---------------------------------------------------------------------------
# Per-file runner
# ---------------------------------------------------------------------------

def run_benchmark_file(
    json_file: str,
    output_file: str,
    model: str,
    ij_server: ij_utils.IntellijServer,
    max_items: Optional[int] = None,
    ref_ids: Optional[list[int]] = None,
    force_run: bool = False,
    initial_wait_sec: int = 10,
    codex_timeout_sec: int = 300,
) -> None:
    json_file   = Path(json_file)
    output_file = Path(output_file)

    print(f"\n{'='*60}")
    print(f"Benchmark : {json_file.name}")
    print(f"Output    : {output_file}")
    print(f"Model     : {model}")
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
        print(f"[{project_name}] Nothing to process (all items already done).")
        return

    # Raw logs go next to the results file, in a logs/ sub-directory.
    raw_log_dir = output_file.parent / "logs" / json_file.stem
    print(f"[{project_name}] Raw codex logs → {raw_log_dir}/")

    _open_and_index(project_name, ij_server, initial_wait_sec=initial_wait_sec)

    output_file.parent.mkdir(parents=True, exist_ok=True)

    success = 0
    for idx, item in enumerate(pending):
        item_id = item.get("id", "?")
        print(f"\n--- [{project_name}] Item {idx+1}/{len(pending)}  id={item_id} ---")

        result = process_item(
            item,
            model=model,
            ij_server=ij_server,
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
        description="Run Codex agent on CorenameBench and save results."
    )
    parser.add_argument("--json-file",   type=str, default=None)
    parser.add_argument("--output-file", type=str, default=None)
    parser.add_argument("--all-projects", action="store_true")
    parser.add_argument("--benchmark-dir", type=str, default=DEFAULT_BENCHMARK_DIR)
    parser.add_argument("--run-identifier", type=str, default="codex_default")
    parser.add_argument("--model", type=str, default="gpt-5.4-mini",
                        help="Model name passed to `codex exec -m`.")
    parser.add_argument("--max-items", type=int, default=None)
    parser.add_argument("--ref-ids", type=str, default=None,
                        help='Comma-separated benchmark IDs, e.g. "2001,2012".')
    parser.add_argument("--force-run", action="store_true")
    parser.add_argument("--ij-server-url", type=str, default=refagent.IJ_SERVER_URL)
    parser.add_argument("--initial-wait-sec", type=int, default=10)
    parser.add_argument("--codex-timeout-sec", type=int, default=900)
    args = parser.parse_args()

    ref_ids = [int(x) for x in args.ref_ids.split(",")] if args.ref_ids else None
    ij_server = ij_utils.IntellijServer(server_url=args.ij_server_url)

    common = dict(
        model=args.model,
        ij_server=ij_server,
        max_items=args.max_items,
        ref_ids=ref_ids,
        force_run=args.force_run,
        initial_wait_sec=args.initial_wait_sec,
        codex_timeout_sec=args.codex_timeout_sec,
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
