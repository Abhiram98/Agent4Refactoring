import os
import json
import hashlib
from pathlib import Path

import refagent


def generate_id(item, project_name):
    """
    Generates a deterministic unique ID based on identifying fields.
    """
    # Use repo name, pattern, file, and commit SHA as the key
    # We use the project name extracted from repo_path if available, 
    # otherwise fallback to what we have.
    pattern = item.get("pattern", "")
    pattern_file = item.get("pattern_file", "")
    commit_sha = item.get("birth_commit_sha", "")
    
    key_string = f"{project_name}:{pattern}:{pattern_file}:{commit_sha}"
    return hashlib.sha256(key_string.encode()).hexdigest()[:16]

def aggregate_files(input_dir, output_file):
    input_path = Path(input_dir)
    all_data = {}
    
    files = list(input_path.glob("*.json"))
    print(f"Found {len(files)} JSON files in {input_dir}")
    
    for file_path in files:
        with open(file_path, "r") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                print(f"Skipping {file_path.name}: Invalid JSON")
                continue
        
        if not isinstance(data, list):
            print(f"Skipping {file_path.name}: Root is not a list")
            continue
            
        for item in data:
            # Check if it's Format A (has pattern and birth_commit_sha)
            if "pattern" in item and "birth_commit_sha" in item:
                # NEW: Filter by is_likely_refactoring
                is_likely_refactor = item.get("greenfield", {}).get("is_likely_refactoring", False)
                if not is_likely_refactor:
                    continue

                repo_path = item.get("repo_path", "")
                project_name = os.path.basename(repo_path.rstrip("/")) if repo_path else file_path.name.split("_")[0]
                
                uid = generate_id(item, project_name)
                
                # Keep the record. If it already exists, candidates_llm versions 
                # usually have more info (like detection_reasoning or llm_is_refactoring),
                # so we can prioritize items with more fields OR just overwrite.
                # Here we'll take the one with 'detection_reasoning' if possible.
                if uid in all_data:
                    existing = all_data[uid]
                    # Simple heuristic: if new item has reasoning and old one doesn't, swap.
                    if item.get("detection_reasoning") and not existing.get("detection_reasoning"):
                        item["id"] = uid # Update the ID field in the item itself
                        all_data[uid] = item
                else:
                    item["id"] = uid
                    all_data[uid] = item
            else:
                # This might be Format B (commits) or something else.
                # Skip for now as it's not a "data point" in the same sense.
                pass

    # Sort by project and pattern for consistent output
    sorted_items = sorted(all_data.values(), key=lambda x: (os.path.basename(x.get("repo_path", "").rstrip("/")), x.get("pattern", ""), x.get("pattern_file", "")))
    
    with open(output_file, "w") as f:
        json.dump(sorted_items, f, indent=2)

    for i in sorted_items:
        repo_path = i.get("repo_path", "")
        project_name = os.path.basename(repo_path.rstrip("/"))
        print(project_name)
        mapping = {
            'AxonFramework': 'AxonFramework/AxonFramework',
            'ant': 'apache/ant',
            'camunda': 'camunda/camunda',
            'cayenne': 'apache/cayenne',
            'cucumber-jvm': 'cucumber/cucumber-jvm',
            'flink': 'apache/flink',
            'hbase': 'apache/hbase',
        }
        i['human_validation'] = False
        i['git_url'] = f'https://github.com/{mapping.get(project_name)}/commit/{i.get('birth_commit_sha', '')}'
        print(i['git_url'])
    with open(output_file+"human_validation.json", "w") as f:
        json.dump(sorted_items, f, indent=2)

    print(f"Successfully aggregated {len(sorted_items)} unique data points into {output_file}")

if __name__ == "__main__":
    MINER_DIR = str(refagent.data_folder.joinpath("design_patterns/miner").absolute())
    OUTPUT_FILE = str(refagent.data_folder.joinpath("design_patterns/aggregated_candidates.json").absolute())
    
    aggregate_files(MINER_DIR, OUTPUT_FILE)
