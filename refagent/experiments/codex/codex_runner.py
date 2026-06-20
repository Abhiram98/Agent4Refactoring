"""
Codex runner for CorenameBench.

Mirrors the workflow of vanilla_LLM.py:
  1. For each project in the benchmark, open it in IntelliJ and wait for indexing.
  2. For each benchmark item:
     a. Checkout v1_hash.
     b. Build the same prompt as vanilla_LLM.py (seed rename + file contents).
        Add an extra note asking Codex to use the IntelliJ MCP rename tool.
     c. Run `codex exec --json -m <model> -C <project_dir> <prompt>` and capture
        the JSONL event stream.
     d. Parse token usage from the last `token_count` event in the stream.
     e. Record wall-clock time.
     f. Commit whatever changes Codex made to the project repo.
     g. Save the result (commit hash + stats) via ResultsManager.
  3. After all items for a project are processed, close the project in IntelliJ.

Usage:
    python codex_runner.py \
        --json-file data/final_dataset/CorenameBech/full_dataset/flink.json \
        --output-file data/results/codex_o4-mini/flink.json \
        --model o4-mini

    # Run all projects:
    python codex_runner.py --all-projects \
        --benchmark-dir data/final_dataset/CorenameBech/full_dataset \
        --run-identifier codex_o4-mini-jun-20 \
        --model o4-mini
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import refagent
import refagent.utils.project_manager as pm
import refagent.experiments.results_manager as rm

# ---------------------------------------------------------------------------
# Pricing table (USD per 1M tokens) — update as needed
# Source: https://openai.com/api/pricing  (June 2026)
# ---------------------------------------------------------------------------
MODEL_PRICING: dict[str, dict[str, float]] = {
    # model-key → {input, cached_input, output}  (per 1M tokens)
    "o4-mini":         {"input": 1.10,  "cached_input": 0.275, "output": 4.40},
    "o3":              {"input": 10.00, "cached_input": 2.50,  "output": 40.00},
    "gpt-4o":          {"input": 2.50,  "cached_input": 1.25,  "output": 10.00},
    "gpt-4o-mini":     {"input": 0.15,  "cached_input": 0.075, "output": 0.60},
    "gpt-5.4-mini":    {"input": 0.40,  "cached_input": 0.10,  "output": 1.60},
    "gpt-5":           {"input": 15.00, "cached_input": 3.75,  "output": 60.00},
}

# How long to wait (seconds) for IntelliJ to finish indexing after opening a project
INTELLIJ_INDEXING_WAIT_SEC = 60

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROJECTS_BASE_PATH = Path(
    os.environ.get("PROJECTS_BASE_PATH", str(refagent.data_folder))
)


def _project_path(project_name: str) -> Path:
    return PROJECTS_BASE_PATH / project_name


def _parse_seed_name(seed_example: dict) -> tuple[str, str]:
    """Extract (old_name, new_name) from a seed_example dict — same logic as vanilla_LLM.py."""
    ref_type = seed_example.get("type", "")
    desc = seed_example.get("description", "")
    old_name = new_name = ""

    if ref_type == "Rename Class":
        m = re.search(
            r"Rename Class .*\.([A-Za-z0-9_]+) renamed to .*\.([A-Za-z0-9_]+)", desc
        )
        if m:
            old_name, new_name = m.group(1), m.group(2)

    elif ref_type == "Rename Method":
        m = re.search(
            r"Rename Method .*? ([A-Za-z0-9_]+)\(.*?\)\s*:\s*.*? renamed to .*? ([A-Za-z0-9_]+)\(",
            desc,
        )
        if m:
            old_name, new_name = m.group(1), m.group(2)

    elif ref_type == "Rename Variable":
        m = re.search(r"Rename Variable ([A-Za-z0-9_]+) ?: .*? to ([A-Za-z0-9_]+) ?:", desc)
        if m:
            old_name, new_name = m.group(1), m.group(2)

    elif ref_type == "Rename Attribute":
        m = re.search(
            r"Rename Attribute ([A-Za-z0-9_]+) ?: .*? to ([A-Za-z0-9_]+) ?: .*? in class",
            desc,
        )
        if m:
            old_name, new_name = m.group(1), m.group(2)

    elif ref_type == "Rename Parameter":
        m = re.search(
            r"Rename Parameter ([A-Za-z0-9_]+) ?: .*? to ([A-Za-z0-9_]+) ?: .*? in method",
            desc,
        )
        if m:
            old_name, new_name = m.group(1), m.group(2)

    # Fallback: pull from leftSide / rightSide codeElement
    if not old_name:
        left = seed_example.get("leftSideLocations", [{}])[0].get("codeElement", "")
        right = seed_example.get("rightSideLocations", [{}])[0].get("codeElement", "")
        old_name = left.split("(")[0].split(" ")[-1].split(".")[-1]
        new_name = right.split("(")[0].split(" ")[-1].split(".")[-1]

    return old_name, new_name


def _build_prompt(item_data: dict, file_content: str, old_name: str, new_name: str) -> str:
    """
    Build the prompt that mirrors vanilla_LLM.py's system + user messages,
    collapsed into a single string for `codex exec`.

    Extra note: ask Codex to use the IntelliJ MCP rename_refactoring tool so
    that all cross-file references are updated atomically.
    """
    improved_commit_message = item_data.get("improved_commit_message", "")
    change_summary = item_data.get("change_summary", "")
    starting_file = item_data.get("starting_file", "")

    system_part = (
        "You are a code refactoring assistant. Your task is to rename identifiers "
        "in the given Java code.\n"
        "You will be given a seed rename. Use it to infer the broader naming concept "
        "being changed and rename ALL occurrences that share the same concept "
        "consistently across the entire project.\n"
    )
    if improved_commit_message:
        system_part += f"Please perform the following action: {improved_commit_message}\n"
    if change_summary:
        system_part += f"{change_summary}\n"

    mcp_note = (
        "\nIMPORTANT: Use the IntelliJ MCP `rename_refactoring` tool to perform "
        "each rename. This ensures all cross-file usages are updated atomically "
        "and consistently via IntelliJ's refactoring engine.\n"
    )

    user_part = (
        f"Seed rename: '{old_name}' -> '{new_name}'\n\n"
        f"File: {starting_file}\n\n"
        f"{file_content}\n\n"
        "Apply the seed rename and propagate it to all conceptually related "
        "identifiers in the project. Use the IntelliJ MCP rename tool for every "
        "rename operation."
    )

    return system_part + mcp_note + "\n" + user_part


def _compute_cost(model: str, input_tokens: int, cached_tokens: int, output_tokens: int) -> float:
    """Return cost in USD for the given token counts."""
    # normalise model name for lookup (strip date suffixes like -2024-xx-xx)
    lookup_key = model.split("-202")[0].split("-20")[0]
    pricing = MODEL_PRICING.get(lookup_key) or MODEL_PRICING.get(model)
    if pricing is None:
        # Unknown model — return -1 to signal "unknown"
        return -1.0
    non_cached_input = max(input_tokens - cached_tokens, 0)
    cost = (
        non_cached_input * pricing["input"]
        + cached_tokens * pricing["cached_input"]
        + output_tokens * pricing["output"]
    ) / 1_000_000
    return cost


def _parse_jsonl_events(jsonl_text: str) -> dict:
    """
    Parse the JSONL event stream written by `codex exec --json` and extract:
      - final total_token_usage (from the last token_count event)
      - last agent message
    """
    token_usage: dict = {}
    last_message: str = ""

    for line in jsonl_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        payload = obj.get("payload", {})
        event_type = payload.get("type", "")

        if event_type == "token_count":
            usage = payload.get("info", {}).get("total_token_usage", {})
            if usage:
                token_usage = usage

        elif event_type in ("agent_message",) and payload.get("phase") == "final_answer":
            last_message = payload.get("message", "")

        # Also catch the response_item final message format
        elif obj.get("type") == "response_item" and payload.get("role") == "assistant":
            content = payload.get("content", [])
            for c in content:
                if c.get("type") == "output_text":
                    last_message = c.get("text", last_message)

    return {"token_usage": token_usage, "last_message": last_message}


# ---------------------------------------------------------------------------
# IntelliJ project management
# ---------------------------------------------------------------------------

def open_intellij_project(project_name: str, wait_sec: int = INTELLIJ_INDEXING_WAIT_SEC) -> None:
    """Open a project in IntelliJ IDEA and wait for indexing to complete."""
    project_dir = str(_project_path(project_name))
    print(f"[IntelliJ] Opening project: {project_dir}")
    subprocess.Popen(
        [
            "open",
            "-na",
            "/Applications/IntelliJ IDEA2025.2.app",
            "--args",
            project_dir,
        ]
    )
    print(f"[IntelliJ] Waiting {wait_sec}s for indexing to complete...")
    time.sleep(wait_sec)
    print("[IntelliJ] Indexing wait complete.")


def close_intellij_project(project_name: str) -> None:
    """
    Close the project in IntelliJ by sending the 'Close Project' action via
    the bundled script tool, or simply by quitting and reopening without it.
    We use `osascript` to send a menu-level close to IntelliJ.
    """
    print(f"[IntelliJ] Closing project: {project_name}")
    script = (
        'tell application "IntelliJ IDEA2025.2"\n'
        "  activate\n"
        "end tell\n"
        'tell application "System Events"\n'
        '  tell process "IntelliJ IDEA2025.2"\n'
        '    click menu item "Close Project" of menu "File" of menu bar 1\n'
        "  end tell\n"
        "end tell\n"
    )
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[IntelliJ] Warning: close project script returned non-zero: {result.stderr}")
    else:
        print("[IntelliJ] Project closed.")
    time.sleep(3)  # brief pause to let IntelliJ settle


# ---------------------------------------------------------------------------
# Core: run codex on one benchmark item
# ---------------------------------------------------------------------------

def process_item(
    item_data: dict,
    model: str,
    timeout_sec: int = 300,
) -> Optional[dict]:
    """
    Run codex on a single benchmark item.

    Returns a result dict on success, or None on failure.
    The result dict has the same shape as vanilla_LLM.py results, plus a
    `stats` key with timing and token information.
    """
    item_id = item_data.get("id", "unknown")
    project_name = item_data.get("project")
    v1_hash = item_data.get("v1_hash")
    starting_file = item_data.get("starting_file")
    seed_example = item_data.get("seed_example")

    # For Rename Class, the starting file is the class file
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
        print(f"[Git] ✅ Checked out {v1_hash} for item {item_id}")
    except Exception as e:
        print(f"[Git] ❌ Checkout failed for item {item_id}: {e}")
        return None

    # --- 2. Read the starting file ---
    try:
        file_path = project.get_project_path() / starting_file
        file_content = file_path.read_text(encoding="utf-8", errors="replace")
        print(f"[File] ✅ Read {starting_file} ({len(file_content)} chars)")
    except Exception as e:
        print(f"[File] ❌ Could not read {starting_file}: {e}")
        return None

    # --- 3. Build prompt ---
    old_name, new_name = _parse_seed_name(seed_example)
    print(f"[Seed] {old_name} -> {new_name}")
    prompt = _build_prompt(item_data, file_content, old_name, new_name)

    # --- 4. Run codex exec ---
    project_dir = str(project.get_project_path())
    cmd = [
        "codex", "exec",
        "--json",
        "-m", model,
        "-C", project_dir,
        "--sandbox", "danger-full-access",
        prompt,
    ]

    print(f"[Codex] Running codex for item {item_id}...")
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
            print(f"[Codex] ⚠️  codex exited with code {proc.returncode}")
            print(f"[Codex] stderr: {proc.stderr[:500]}")
    except subprocess.TimeoutExpired as e:
        wall_elapsed = time.monotonic() - wall_start
        jsonl_output = (e.stdout or b"").decode("utf-8", errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        print(f"[Codex] ⚠️  Timed out after {timeout_sec}s for item {item_id}")

    print(f"[Codex] Wall time: {wall_elapsed:.1f}s")

    # --- 5. Parse token usage ---
    parsed = _parse_jsonl_events(jsonl_output)
    token_usage = parsed["token_usage"]
    input_tokens = token_usage.get("input_tokens", 0)
    cached_tokens = token_usage.get("cached_input_tokens", 0)
    output_tokens = token_usage.get("output_tokens", 0)
    total_tokens = token_usage.get("total_tokens", 0)
    cost_usd = _compute_cost(model, input_tokens, cached_tokens, output_tokens)

    print(
        f"[Tokens] input={input_tokens} cached={cached_tokens} "
        f"output={output_tokens} total={total_tokens} cost=${cost_usd:.4f}"
    )

    # --- 6. Commit whatever codex changed ---
    try:
        changed_files = project.get_changed_files()
        if changed_files:
            project.safe_add(changed_files)
        commit_message = f"codex: rename {old_name} -> {new_name} (item {item_id})"
        commit_hash = project.git_repo.index.commit(commit_message)
        print(f"[Git] ✅ Committed as {commit_hash}")
    except Exception as e:
        print(f"[Git] ❌ Commit failed for item {item_id}: {e}")
        commit_hash = None

    return {
        "id": item_id,
        "response": {
            "commit_hash": str(commit_hash) if commit_hash else None,
            "stats": {
                "wall_time_sec": round(wall_elapsed, 2),
                "input_tokens": input_tokens,
                "cached_input_tokens": cached_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "cost_usd": round(cost_usd, 6),
                "model": model,
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
    max_items: Optional[int] = None,
    ref_ids: Optional[list[int]] = None,
    force_run: bool = False,
    intellij_wait_sec: int = INTELLIJ_INDEXING_WAIT_SEC,
    codex_timeout_sec: int = 300,
) -> None:
    """Process one benchmark JSON file (one project)."""
    json_file = Path(json_file)
    output_file = Path(output_file)

    print(f"\n{'='*60}")
    print(f"Benchmark file : {json_file.name}")
    print(f"Output file    : {output_file}")
    print(f"Model          : {model}")
    print(f"{'='*60}\n")

    with open(json_file) as f:
        all_items: list[dict] = json.load(f)

    # Resume support
    results: list[dict] = []
    if output_file.exists() and not force_run:
        with open(output_file) as f:
            results = json.load(f)
    cached_ids: set = {r["id"] for r in results}

    # Figure out project name from the first item
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

    # Open IntelliJ for this project
    open_intellij_project(project_name, wait_sec=intellij_wait_sec)

    output_file.parent.mkdir(parents=True, exist_ok=True)

    success = 0
    for idx, item in enumerate(pending):
        item_id = item.get("id", "?")
        print(f"\n--- [{project_name}] Item {idx+1}/{len(pending)}  (id={item_id}) ---")

        result = process_item(item, model=model, timeout_sec=codex_timeout_sec)
        if result:
            results.append(result)
            success += 1
            # Persist after every item so we can resume
            with open(output_file, "w") as f:
                json.dump(results, f, indent=4)
            print(f"[Save] ✅ Saved {len(results)} results to {output_file}")
        else:
            print(f"[{project_name}] ❌ Failed item {item_id}")

    # Close IntelliJ for this project
    close_intellij_project(project_name)

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
        default=str(
            refagent.data_folder / "final_dataset" / "CorenameBech" / "full_dataset"
        ),
        help="Directory containing per-project benchmark JSONs (used with --all-projects).",
    )
    parser.add_argument(
        "--run-identifier",
        type=str,
        default="codex_default",
        help="Sub-directory under data/results/ for output (used with --all-projects).",
    )

    # Shared options
    parser.add_argument(
        "--model",
        type=str,
        default="o4-mini",
        help="Model name passed to `codex exec -m`.",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=None,
        help="Maximum number of items to process per file.",
    )
    parser.add_argument(
        "--ref-ids",
        type=str,
        default=None,
        help='Comma-separated list of benchmark IDs to process, e.g. "2001,2002".',
    )
    parser.add_argument(
        "--force-run",
        action="store_true",
        help="Re-run items that already have results.",
    )
    parser.add_argument(
        "--intellij-wait-sec",
        type=int,
        default=INTELLIJ_INDEXING_WAIT_SEC,
        help="Seconds to wait after opening IntelliJ for indexing.",
    )
    parser.add_argument(
        "--codex-timeout-sec",
        type=int,
        default=300,
        help="Per-item timeout for `codex exec` (seconds).",
    )

    args = parser.parse_args()

    ref_ids = (
        [int(x) for x in args.ref_ids.split(",")]
        if args.ref_ids
        else None
    )

    if args.all_projects:
        benchmark_dir = Path(args.benchmark_dir)
        results_base = refagent.data_folder / "results" / args.run_identifier
        benchmark_files = sorted(benchmark_dir.glob("*.json"))
        if not benchmark_files:
            print(f"No .json files found in {benchmark_dir}", file=sys.stderr)
            sys.exit(1)
        print(f"Found {len(benchmark_files)} benchmark file(s) in {benchmark_dir}")
        for bf in benchmark_files:
            out = results_base / bf.name
            run_benchmark_file(
                json_file=str(bf),
                output_file=str(out),
                model=args.model,
                max_items=args.max_items,
                ref_ids=ref_ids,
                force_run=args.force_run,
                intellij_wait_sec=args.intellij_wait_sec,
                codex_timeout_sec=args.codex_timeout_sec,
            )
    elif args.json_file:
        if args.output_file is None:
            parser.error("--output-file is required when using --json-file")
        run_benchmark_file(
            json_file=args.json_file,
            output_file=args.output_file,
            model=args.model,
            max_items=args.max_items,
            ref_ids=ref_ids,
            force_run=args.force_run,
            intellij_wait_sec=args.intellij_wait_sec,
            codex_timeout_sec=args.codex_timeout_sec,
        )
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
