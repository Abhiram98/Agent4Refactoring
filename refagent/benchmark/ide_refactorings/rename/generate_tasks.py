import json
import glob
import os
from pathlib import Path
from collections import defaultdict
import re

from refactoring_types.refactorings import RefminerOut, Rename


def get_file_path(candidate):
    """Safely extracts the main filepath from the candidate's leftSideLocations."""
    locs = candidate.get("leftSideLocations", [])
    if locs:
        return locs[0].get("filePath", "")
    return ""

def score_candidate(candidate, selected_paths):
    """
    Scores a candidate based on string isolation from existing selections.
    Smaller common prefix = Larger score!
    """
    c_path = get_file_path(candidate)
    if not selected_paths:
        return float('inf') # Highest priority if nothing exists
        
    longest_prefix = 0
    for s_path in selected_paths:
        prefix = os.path.commonprefix([c_path, s_path])
        longest_prefix = max(longest_prefix, len(prefix))
        
    return 1.0 / (longest_prefix + 1)

def parse_project_name(filename):
    """Maps dataset files back to standardized github repo names."""
    mapping = {
        "camunda": "camunda/camunda-bpm-platform",
        "flink": "apache/flink",
        "graal": "oracle/graal",
        "intellij-community": "JetBrains/intellij-community",
        "kafka": "apache/kafka",
        "liferay-portal": "liferay/liferay-portal",
        "mekhq": "MegaMek/mekhq",
        "osmand": "osmandapp/OsmAnd",
        "spring-boot": "spring-projects/spring-boot",
        "bytechef": "bytechefio/bytechef"
    }
    return mapping.get(filename, filename)

def extract_specific_rename(desc: str) -> str:
    """Attempts to strip out complex RM signature descriptions to provide clean NL commands."""
    # Eg: Rename Method package rawReference(sameDirection boolean) : MarshallerData renamed to package peerReference(sameDirection boolean) ...
    # Simple regex fallback, but keeping original description often safer for raw data processing.
    # We will output a nicely formatted string based directly on RM descriptor
    if " renamed to " in desc:
        parts = desc.split(" renamed to ")
        # Try capturing just the core names via simplistic rules
        return f"Perform {desc}"
    return desc

def main():
    script_dir = Path(__file__).parent.resolve()
    project_root = script_dir.parent.parent.parent.parent
    
    input_dir = project_root / "data" / "ide_refactorings" / "rename" / "corename-bench"
    output_path = project_root / "data" / "ide_refactorings" / "rename" / "tasks.json"
    
    type_bins = defaultdict(list)
    cluster_idx = 0
    
    # 1. Parse into Typed Buckets
    for j_path in glob.glob(str(input_dir / "*.json")):
        raw_name = Path(j_path).stem
        project_name = parse_project_name(raw_name)
        
        with open(j_path) as f:
            try:
                data = json.load(f)
            except Exception as e:
                print(f"Failed loading {j_path}: {e}")
                continue
                
            if isinstance(data, dict):
                data = [data]
                
            for commit_obj in data:
                if not isinstance(commit_obj, dict):
                    continue
                    
                commit = commit_obj.get("v1_hash", "")
                project_name = commit_obj.get("project", project_name)
                clusters = commit_obj.get("clusters", [])
                
                for cluster in clusters:
                    cluster_id = f"{raw_name}-cluster-{cluster_idx}"
                    cluster_idx += 1
                    
                    for inner_item in cluster:
                        candidates = inner_item if isinstance(inner_item, list) else [inner_item]
                        for c in candidates:
                            c_type = c.get("type", "Unknown")
                            if "Rename" not in c_type:
                                continue # ensure we only process Rename variants
                                
                            c["_cluster_id"] = cluster_id
                            c["_project_name"] = project_name
                            c["_commit"] = commit
                            type_bins[c_type].append(c)

    # 2. Heuristic Round-Robin Selection
    cluster_selection_counts = defaultdict(int)
    cluster_selected_paths = defaultdict(list)
    final_tasks = []
    task_id_counter = 1
    
    active_types = list(type_bins.keys())
    
    while active_types:
        progress_made = False
        
        for t in list(active_types):
            candidates = type_bins[t]
            
            # Rule 1: Remove candidates whose clusters already reached max 3 items
            valid_candidates = [c for c in candidates if cluster_selection_counts[c["_cluster_id"]] < 3]
            
            if not valid_candidates:
                active_types.remove(t)
                continue
                
            progress_made = True
            
            # Rule 2: Pick the candidate with the highest isolation distance
            best_candidate = None
            best_score = -1.0
            
            for c in valid_candidates:
                cid = c["_cluster_id"]
                score = score_candidate(c, cluster_selected_paths[cid])
                
                # Rule 3: Major boost if this cluster hasn't been accessed yet
                if cluster_selection_counts[cid] == 0:
                    score += 10.0
                    
                if score > best_score:
                    best_score = score
                    best_candidate = c
                    
            c = best_candidate
            cid = c["_cluster_id"]
            
            cluster_selection_counts[cid] += 1
            cluster_selected_paths[cid].append(get_file_path(c))
            
            # Remove selected candidate from its global type bin
            type_bins[t] = [orig for orig in type_bins[t] if orig is not c]
            
            # Map Output
            desc = c.get("description", "")
            ref_miner = RefminerOut.load_from_dictionary(c)
            if isinstance(ref_miner, Rename):
                instruction_text = ref_miner.print_string_without_type()
            else:
                instruction_text = f"Perform the following renaming refactoring: {desc}"
            
            task = {
                "id": f"rename-{task_id_counter}",
                "instruction": instruction_text,
                "project_name": c["_project_name"],
                "commit": c["_commit"],
                "type": c.get("type"),
                "file_path": get_file_path(c),
                "cluster_id": cid,
                "original_description": desc
            }
            final_tasks.append(task)
            task_id_counter += 1
            
        if not progress_made:
            break
            
    # File write block
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(final_tasks, f, indent=4)
        
    # Statistical Log
    print(f"Generated {len(final_tasks)} individual tasks.")
    print("\n--- Type Distribution ---")
    type_counts = defaultdict(int)
    for t in final_tasks:
        type_counts[t["type"]] += 1
        
    for k, sorted_count in sorted(type_counts.items(), key=lambda item: item[1], reverse=True):
        print(f"{k}: {sorted_count}")
        
    if cluster_selection_counts:
        avg_per = sum(cluster_selection_counts.values()) / len([v for v in cluster_selection_counts.values() if v > 0])
        print(f"\nAverage selected items per hit cluster: {avg_per:.2f}")

if __name__ == '__main__':
    main()
