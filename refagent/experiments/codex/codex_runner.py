"""
Codex runner for CorenameBench.

Mirrors the workflow of vanilla_LLM.py:
  1. For each project in the benchmark, open it in IntelliJ and wait for
     indexing via ij_server.reload_project() (blocking HTTP call).
  2. For each benchmark item:
     a. Checkout v1_hash, then wait for IntelliJ to re-index.
     b. Build the same prompt as vanilla_LLM.py via the shared
        refagent.experiments.prompts module, plus a note to use the MCP
        rename tool.
     c. Run `codex exec --json -m <model> -C <project_dir> <prompt>` and
        capture the JSONL event stream.
     d. Parse token usage from the last `token_count` event.
     e. Record wall-clock time and compute cost.
     f. Commit whatever changes Codex made.
     g. Save the result (commit hash + stats) incrementally.
  3. After all items for a project are done, open the next project in
     IntelliJ (which implicitly switches context away from the old one).

Benchmark sources
-----------------
  data/uncontaminated/*.json          — main corename benchmark (10 projects)
  data/renas/renas_oracle.json        — renas oracle

Usage
-----
  # Single project
  PYTHONPATH=. .venv/bin/python refagent/experiments/codex/codex_runner.py \\
      --json-file data/uncontaminated/flink.json \\
      --output-file data/results/codex_o4-mini-jun-20/flink.json \\
      --model o4-mini

  # All uncontaminated projects
  PYTHONPATH=. .venv/bin/python refagent/experiments/codex/codex_runner.py \\
      --all-projects \\
      --run-identifier codex_o4-mini-jun-20 \\
      --model o4-mini
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import refagent
import refagent.utils.project_manager as pm
import refagent.utils.intellij_server as ij_utils
from refagent.experiments.prompts import parse_seed_name, build_rename_prompt

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

# Default benchmark directory (the uncontaminated split)
DEFAULT_BENCHMARK_DIR = str(refagent.data_folder / "uncontaminated")

# ---------------------------------------------------------------------------
# Cost helper
# ---------------------------------------------------------------------------

def _compute_cost(model: str, input_tokens: int, cached_tokens: int, output_tokens: int) -> float:
    """Return cost in USD; -1.0 if the model is not in the pricing table."""
    # Strip date suffixes like -2024-11-xx
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

def _parse_jsonl_events(jsonl_text: str) -> dict:
    """
    Parse the JSONL stream emitted by `codex exec --json`.

    Returns:
      token_usage      — final cumulative token counts (from the last
                         token_count event)
      last_message     — final assistant message
      mcp_tool_calls   — list of every IntelliJ MCP tool call, each entry:
                           {"tool": str, "call_id": str, "arguments": dict}
      mcp_call_counts  — dict mapping tool_name -> call count, e.g.
                           {"rename_refactoring": 3, "find_files_by_name_keyword": 1}
    """
    token_usage: dict = {}
    last_message: str = ""
    mcp_tool_calls: list = []

    for raw in jsonl_text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue

        payload = obj.get("payload", {})
        event_type = payload.get("type", "")

        if event_type == "token_count":
            usage = payload.get("info", {}).get("total_token_usage", {})
            if usage:
                token_usage = usage

        elif event_type == "mcp_tool_call_end":
            invocation = payload.get("invocation", {})
            # Only count calls to the IntelliJ MCP server.
            if invocation.get("server") == "intellij_idea_mcp":
                mcp_tool_calls.append({
                    "tool":      invocation.get("tool", "unknown"),
                    "call_id":   payload.get("call_id", ""),
                    "arguments": invocation.get("arguments", {}),
                })

        elif event_type == "agent_message" and payload.get("phase") == "final_answer":
            last_message = payload.get("message", last_message)

        elif obj.get("type") == "response_item" and payload.get("role") == "assistant":
            for c in payload.get("content", []):
                if c.get("type") == "output_text":
                    last_message = c.get("text", last_message)

    # Aggregate call counts per tool name.
    mcp_call_counts: dict[str, int] = {}
    for call in mcp_tool_calls:
        tool = call["tool"]
        mcp_call_counts[tool] = mcp_call_counts.get(tool, 0) + 1

    return {
        "token_usage":     token_usage,
        "last_message":    last_message,
        "mcp_tool_calls":  mcp_tool_calls,
        "mcp_call_counts": mcp_call_counts,
    }


# ---------------------------------------------------------------------------
# IntelliJ helpers
# ---------------------------------------------------------------------------

def _open_and_index(
    project_name: str,
    ij_server: ij_utils.IntellijServer,
    initial_wait_sec: int = 10,
) -> None:
    """
    Open a project in IntelliJ, wait briefly for the process to come up,
    then block on reload_project() until indexing is done.
    """
    project_path = PROJECTS_BASE_PATH / project_name
    print(f"[IntelliJ] Opening {project_path} ...")
    subprocess.Popen(
        ["open", "-na", "/Applications/IntelliJ IDEA2025.2.app", "--args", str(project_path)]
    )
    # Give IntelliJ a moment to launch / switch to the new project before
    # we hit the HTTP server.
    print(f"[IntelliJ] Waiting {initial_wait_sec}s for IntelliJ to come up ...")
    time.sleep(initial_wait_sec)

    _wait_for_index(project_name, ij_server)


def _wait_for_index(project_name: str, ij_server: ij_utils.IntellijServer) -> None:
    """
    Call ij_server.open_project() so IntelliJ knows which project we care
    about, then block on reload_project() until the index is ready.
    """
    project_path = PROJECTS_BASE_PATH / project_name
    print(f"[IntelliJ] Signalling open_project for {project_name} ...")
    ij_server.open_project(project_path=project_path)
    print("[IntelliJ] Waiting for indexing (reload_project) ...")
    ij_server.reload_project()
    print("[IntelliJ] Indexing complete.")


# ---------------------------------------------------------------------------
# Core: run codex on one benchmark item
# ---------------------------------------------------------------------------

def process_item(
    item_data: dict,
    model: str,
    ij_server: ij_utils.IntellijServer,
    timeout_sec: int = 300,
) -> Optional[dict]:
    """
    Run codex on a single benchmark item.

    Returns a result dict on success (same shape as vanilla_LLM.py, plus a
    `stats` sub-key), or None on failure.
    """
    item_id      = item_data.get("id", "unknown")
    project_name = item_data.get("project")
    v1_hash      = item_data.get("v1_hash")
    starting_file = item_data.get("starting_file")
    seed_example  = item_data.get("seed_example")

    # For Rename Class the canonical file is the class declaration file.
    if seed_example and seed_example.get("type") == "Rename Class":
        starting_file = seed_example["leftSideLocations"][0]["filePath"]
        print(f"[Setup] Rename Class seed — using starting_file: {starting_file}")

    if not all([project_name, v1_hash, starting_file, seed_example]):
        print(f"[Setup] ❌ Missing required fields in item {item_id}")
        return None

    # --- 1. Checkout v1_hash ---
    try:
        project = pm.EvalProject(project_name)
        project.restore_changes()
        project.checkout(v1_hash, force=True)
        print(f"[Git] ✅ Checked out {v1_hash[:8]} for item {item_id}")
    except Exception as e:
        print(f"[Git] ❌ Checkout failed for item {item_id}: {e}")
        return None

    # --- 2. Wait for IntelliJ to re-index after the checkout ---
    _wait_for_index(project_name, ij_server)

    # --- 3. Read the starting file ---
    try:
        file_content = (project.get_project_path() / starting_file).read_text(
            encoding="utf-8", errors="replace"
        )
        print(f"[File] ✅ Read {starting_file} ({len(file_content)} chars)")
    except Exception as e:
        print(f"[File] ❌ Could not read {starting_file}: {e}")
        return None

    # --- 4. Build prompt (shared with vanilla_LLM, MCP note added) ---
    old_name, new_name = parse_seed_name(seed_example)
    print(f"[Seed] {old_name} -> {new_name}")
    prompt = build_rename_prompt(
        item_data=item_data,
        file_content=file_content,
        old_name=old_name,
        new_name=new_name,
        include_mcp_note=True,
    )

    # --- 5. Run codex exec ---
    project_dir = str(project.get_project_path())
    cmd = [
        "codex", "exec",
        "--json",
        "-m", model,
        "-C", project_dir,
        "--sandbox", "danger-full-access",
        prompt.as_single_string(),
    ]

    print(f"[Codex] Running for item {item_id} ...")
    wall_start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        wall_elapsed = time.monotonic() - wall_start
        jsonl_output = proc.stdout
        if proc.returncode != 0:
            print(f"[Codex] ⚠️  exit code {proc.returncode}")
            print(f"[Codex] stderr: {proc.stderr[:400]}")
    except subprocess.TimeoutExpired as exc:
        wall_elapsed = time.monotonic() - wall_start
        stdout = exc.stdout or b""
        jsonl_output = stdout.decode("utf-8", errors="replace") if isinstance(stdout, bytes) else (stdout or "")
        print(f"[Codex] ⚠️  Timed out after {timeout_sec}s for item {item_id}")

    print(f"[Codex] Wall time: {wall_elapsed:.1f}s")

    # --- 6. Parse token usage from the JSONL stream ---
    parsed = _parse_jsonl_events(jsonl_output)
    tok = parsed["token_usage"]
    input_tokens  = tok.get("input_tokens", 0)
    cached_tokens = tok.get("cached_input_tokens", 0)
    output_tokens = tok.get("output_tokens", 0)
    total_tokens  = tok.get("total_tokens", 0)
    cost_usd      = _compute_cost(model, input_tokens, cached_tokens, output_tokens)
    mcp_call_counts = parsed["mcp_call_counts"]
    total_mcp_calls = sum(mcp_call_counts.values())

    print(
        f"[Tokens] input={input_tokens} cached={cached_tokens} "
        f"output={output_tokens} total={total_tokens} cost=${cost_usd:.4f}"
    )
    print(f"[MCP]    intellij tool calls: {total_mcp_calls}  breakdown: {mcp_call_counts}")

    # --- 7. Commit whatever Codex changed ---
    try:
        changed = project.get_changed_files()
        if changed:
            project.safe_add(changed)
        commit_msg = f"codex: rename {old_name} -> {new_name} (item {item_id})"
        commit_hash = project.git_repo.index.commit(commit_msg)
        print(f"[Git] ✅ Committed as {commit_hash}")
    except Exception as e:
        print(f"[Git] ❌ Commit failed for item {item_id}: {e}")
        commit_hash = None

    return {
        "id": item_id,
        "response": {
            "commit_hash": str(commit_hash) if commit_hash else None,
            "stats": {
                "wall_time_sec":        round(wall_elapsed, 2),
                "input_tokens":         input_tokens,
                "cached_input_tokens":  cached_tokens,
                "output_tokens":        output_tokens,
                "total_tokens":         total_tokens,
                "cost_usd":             round(cost_usd, 6),
                "model":                model,
                "mcp_call_counts":      mcp_call_counts,
                "total_mcp_calls":      total_mcp_calls,
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
    """Process one benchmark JSON file (one project)."""
    json_file   = Path(json_file)
    output_file = Path(output_file)

    print(f"\n{'='*60}")
    print(f"Benchmark : {json_file.name}")
    print(f"Output    : {output_file}")
    print(f"Model     : {model}")
    print(f"{'='*60}\n")

    with open(json_file) as f:
        all_items: list[dict] = json.load(f)

    # Resume support
    results: list[dict] = []
    if output_file.exists() and not force_run:
        with open(output_file) as f:
            results = json.load(f)
    cached_ids: set = {r["id"] for r in results}

    project_name = all_items[0]["project"] if all_items else json_file.stem

    # Filter items
    items_to_process = all_items
    if max_items is not None:
        items_to_process = items_to_process[:max_items]
    if ref_ids is not None:
        items_to_process = [i for i in items_to_process if i.get("id") in ref_ids]

    pending = [i for i in items_to_process if force_run or i.get("id") not in cached_ids]
    if not pending:
        print(f"[{project_name}] Nothing to process (all items already done).")
        return

    # Open IntelliJ for this project and wait for the initial index.
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
            timeout_sec=codex_timeout_sec,
        )
        if result:
            results.append(result)
            success += 1
            with open(output_file, "w") as f:
                json.dump(results, f, indent=4)
            print(f"[Save] ✅ {len(results)} results -> {output_file}")
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

    # Single-file mode
    parser.add_argument(
        "--json-file",
        type=str,
        default=None,
        help="Path to a single CorenameBench project JSON file.",
    )
    parser.add_argument(
        "--output-file",
        type=str,
        default=None,
        help="Where to write results JSON (single-file mode).",
    )

    # All-projects mode
    parser.add_argument(
        "--all-projects",
        action="store_true",
        help="Process all .json files in --benchmark-dir.",
    )
    parser.add_argument(
        "--benchmark-dir",
        type=str,
        default=DEFAULT_BENCHMARK_DIR,
        help="Directory containing per-project benchmark JSONs.",
    )
    parser.add_argument(
        "--run-identifier",
        type=str,
        default="codex_default",
        help="Sub-directory under data/results/ for output (--all-projects mode).",
    )

    # Shared options
    parser.add_argument("--model", type=str, default="o4-mini",
                        help="Model name passed to `codex exec -m`.")
    parser.add_argument("--max-items", type=int, default=None,
                        help="Maximum items to process per file.")
    parser.add_argument("--ref-ids", type=str, default=None,
                        help='Comma-separated benchmark IDs, e.g. "2001,2002".')
    parser.add_argument("--force-run", action="store_true",
                        help="Re-run items that already have results.")
    parser.add_argument("--ij-server-url", type=str,
                        default=refagent.IJ_SERVER_URL,
                        help="URL of the IntelliJ HTTP server (default: IJ_SERVER_URL env var).")
    parser.add_argument("--initial-wait-sec", type=int, default=10,
                        help="Seconds to wait after `open` before hitting the IJ server.")
    parser.add_argument("--codex-timeout-sec", type=int, default=300,
                        help="Per-item timeout for `codex exec` (seconds).")

    args = parser.parse_args()

    ref_ids = (
        [int(x) for x in args.ref_ids.split(",")]
        if args.ref_ids else None
    )

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
        benchmark_dir = Path(args.benchmark_dir)
        results_base  = refagent.data_folder / "results" / args.run_identifier
        benchmark_files = sorted(benchmark_dir.glob("*.json"))
        if not benchmark_files:
            print(f"No .json files found in {benchmark_dir}", file=sys.stderr)
            sys.exit(1)
        print(f"Found {len(benchmark_files)} benchmark file(s) in {benchmark_dir}")
        for bf in benchmark_files:
            run_benchmark_file(
                json_file=str(bf),
                output_file=str(results_base / bf.name),
                **common,
            )

    elif args.json_file:
        if args.output_file is None:
            parser.error("--output-file is required with --json-file")
        run_benchmark_file(
            json_file=args.json_file,
            output_file=args.output_file,
            **common,
        )

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
