#!/usr/bin/env python3
import json
import os
import re
import sys

SPLIT_DIR = "/Users/abhiram/Documents/TBE/RefactoringAgentProject/Agent4Refactoring/data/design_patterns/split_files"
DPDF_PATH = "/Users/abhiram/Documents/TBE/RefactoringAgentProject/Agent4Refactoring/data/design_patterns/dpdf_dataset.json"
OUT_PATH = os.path.join(os.path.dirname(__file__), "project_urls_output.json")

url_re = re.compile(r"https?://[^\s\"',]+")

def normalize(s):
    return re.sub(r'[^a-z0-9]', '', s.lower()) if s else ''

# load dpdf dataset mapping (project_name -> github_url set)
dpdf_map = {}
if os.path.exists(DPDF_PATH):
    try:
        with open(DPDF_PATH, 'r', encoding='utf-8') as f:
            dpdf = json.load(f)
        for entry in dpdf:
            pn = entry.get('project_name')
            url = entry.get('github_url')
            if pn and url:
                dpdf_map.setdefault(normalize(pn), set()).add(url)
    except Exception as e:
        print("Warning: failed to load dpdf_dataset.json:", e, file=sys.stderr)

results = {}
for fname in sorted(os.listdir(SPLIT_DIR)):
    if not fname.endswith('.json'):
        continue
    fpath = os.path.join(SPLIT_DIR, fname)
    urls = set()
    project_name_from_file = None
    try:
        with open(fpath, 'r', encoding='utf-8') as f:
            text = f.read()
        try:
            data = json.loads(text)
        except Exception:
            data = None
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    if item.get('github_url'):
                        urls.add(item.get('github_url'))
                    # scan dict values for any http URLs
                    for v in item.values():
                        if isinstance(v, str) and v.startswith('http'):
                            urls.update(url_re.findall(v))
                    if project_name_from_file is None:
                        pn = item.get('project_name')
                        if pn:
                            project_name_from_file = pn
        else:
            urls.update(url_re.findall(text))
    except Exception as e:
        print(f"Error reading {fpath}: {e}", file=sys.stderr)
        continue

    # fallback to dpdf mapping using project_name or filename
    if not urls:
        candidates = []
        if project_name_from_file:
            candidates.append(project_name_from_file)
        candidates.append(os.path.splitext(fname)[0])
        for cand in candidates:
            if not cand:
                continue
            urls_found = dpdf_map.get(normalize(cand))
            if urls_found:
                urls.update(urls_found)

    results[fname] = sorted(urls)

# write output to file and stdout
with open(OUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(results, f, indent=2)

print(json.dumps(results, indent=2))
