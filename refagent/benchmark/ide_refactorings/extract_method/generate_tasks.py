import json
import os
import glob
from pathlib import Path

def main():
    # Setup paths relative to the project root
    script_dir = Path(__file__).parent.resolve()
    # Script is at refagent/benchmark/ide_refactorings/generate_tasks.py
    # So project root is 3 folders up
    project_root = script_dir.parent.parent.parent.parent
    
    input_dir = project_root / "data" / "ide_refactorings" / "extract-method" / "em-assist-benchmark"
    output_path = project_root / "data" / "ide_refactorings" / "extract-method" / "tasks.json"
    
    json_files = glob.glob(str(input_dir / "*.json"))
    
    all_tasks = []
    task_counter = 1
    
    for file_path in json_files:
        with open(file_path, "r") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                print(f"Failed to parse {file_path}")
                continue
                
        if isinstance(data, dict):
            # Just in case some files are dicts instead of lists
            data = [data]
            
        for item in data:
            if not isinstance(item, dict):
                continue
                
            oracle = item.get("oracle", {})
            if not oracle:
                continue
                
            line_start = oracle.get("line_start")
            line_end = oracle.get("line_end")
            filename_path = oracle.get("filename", "")
            filename = os.path.basename(filename_path)
            method_name = item.get("host_functionName")
            extracted_name = item.get("extracted_method_functionName")
            
            if line_start is None or line_end is None or not method_name or not extracted_name or not filename:
                print(f"Skipping task due to missing fields in {file_path}")
                continue
                
            instruction = f"Extract Function from lines {line_start}-{line_end} in {method_name} method and name it {extracted_name} in {filename}"
            
            task = {
                "id": f"extract-method-{task_counter}",
                "instruction": instruction,
                "project_name": item.get("projectName"),
                "url": item.get("url"),
                "commit": item.get("ParentSHA"),
                "gold_commit": item.get("sha"),
                "host_method_name": method_name,
                "extracted_method_name": extracted_name,
                "oracle": oracle
            }
            
            all_tasks.append(task)
            task_counter += 1
            
    # Make sure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w") as f:
        json.dump(all_tasks, f, indent=4)
        print(f"Successfully generated {len(all_tasks)} tasks to {output_path}")

if __name__ == "__main__":
    main()
