#!/usr/bin/env python3
"""
Split dpdf_dataset.json into separate JSON files per project_name.
Outputs are written to the split_files directory.
"""
import json
import os
import re

SRC = "/Users/abhiram/Documents/TBE/RefactoringAgentProject/Agent4Refactoring/data/design_patterns/dpdf_dataset.json"
OUT_DIR = "/Users/abhiram/Documents/TBE/RefactoringAgentProject/Agent4Refactoring/data/design_patterns/split_files"

os.makedirs(OUT_DIR, exist_ok=True)

with open(SRC, "r", encoding="utf-8") as f:
    data = json.load(f)

by_project = {}
for item in data:
    proj = item.get("project_name") or "UNKNOWN"
    by_project.setdefault(proj, []).append(item)

for proj, items in by_project.items():
    # sanitize filename
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", proj).strip("_")
    if not safe:
        safe = "UNKNOWN"
    out_path = os.path.join(OUT_DIR, f"{safe}.json")
    with open(out_path, "w", encoding="utf-8") as out_f:
        json.dump(items, out_f, indent=2, ensure_ascii=False)

print(f"Wrote {len(by_project)} project files to: {OUT_DIR}")
