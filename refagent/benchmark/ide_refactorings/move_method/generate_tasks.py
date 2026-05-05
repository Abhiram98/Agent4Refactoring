import json
import os
import glob
import re
from pathlib import Path

def parse_project_name(url):
    if "github.com/" in url:
        return url.split("github.com/")[-1].replace(".git", "")
    return url

def main():
    script_dir = Path(__file__).parent.resolve()
    project_root = script_dir.parent.parent.parent.parent
    
    input_dir = project_root / "data" / "ide_refactorings" / "move-method" / "mm-asssit-benchmark"
    output_path = project_root / "data" / "ide_refactorings" / "move-method" / "tasks.json"
    
    json_files = glob.glob(str(input_dir / "*.json"))
    
    all_tasks = []
    task_counter = 1
    
    # Regex to capture parts of the Extract And Move Method description
    # Example: "Extract And Move Method public getWindowSize() : Optional<Duration> extracted from private createEndingState() : State<T> in class org.apache.flink.cep.nfa.compiler.NFACompiler.NFAFactoryCompiler & moved to class org.apache.flink.cep.pattern.Quantifier.Times"
    desc_regex = re.compile(r"Extract And Move Method (.*?) extracted from (.*?) in class (.*?) & moved to class (.*)")
    
    # Regex to extract the method name from its signature, e.g., "public getWindowSize() : Optional<Duration>" -> "getWindowSize"
    name_regex = re.compile(r"(\w+)\s*\(")
    
    for file_path in json_files:
        with open(file_path, "r") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                print(f"Failed to parse {file_path}")
                continue
                
        if isinstance(data, dict):
            data = [data]
            
        for item in data:
            if not isinstance(item, dict):
                continue
                
            extraction_results = item.get("extraction_results", {})
            if not extraction_results.get("success"):
                # Skip if the pre-requisite extraction failed or is missing
                continue
                
            base_commit = extraction_results.get("newCommitHash")
            gold_commit = item.get("sha1")
            
            refactoring = item.get("move_method_refactoring", {})
            desc = refactoring.get("description", "")
            
            match = desc_regex.search(desc)
            if not match:
                print(f"Regex mismatch for description: {desc}")
                continue
                
            method_signature = match.group(1).strip()
            source_class = match.group(3).strip()
            target_class = match.group(4).strip()
            
            name_match = name_regex.search(method_signature)
            method_name = name_match.group(1) if name_match else None
            
            if not method_name:
                print(f"Could not extract method name from signature: {method_signature}")
                continue
                
            project_name = parse_project_name(item.get("repository", ""))
            
            instruction = f"Move method {method_name} from class {source_class} to class {target_class}"
            
            task = {
                "id": f"move-method-{task_counter}",
                "instruction": instruction,
                "project_name": project_name,
                "url": item.get("url"),
                "base_commit": base_commit,
                "gold_commit": gold_commit,
                "branch_name": extraction_results.get("newBranchName"),
                "method_name": method_name,
                "source_class": source_class,
                "target_class": target_class,
                "ref_id": item.get("ref_id"),
                "original_description": desc
            }
            
            all_tasks.append(task)
            task_counter += 1
            
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w") as f:
        json.dump(all_tasks, f, indent=4)
        print(f"Successfully generated {len(all_tasks)} move-method tasks to {output_path}")

if __name__ == "__main__":
    main()
