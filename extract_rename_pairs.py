import json
import os
import re
import argparse
from pathlib import Path

# Import the utilities from the codebase
import refagent
import refagent.utils.project_manager as pm
import refagent.utils.refminer_utils as rminer

# Define rename types for filtering RefactoringMiner output
RENAME_TYPES = {
    'Rename Class',
    'Rename Method',
    'Rename Variable',
    'Rename Parameter',
    'Rename Attribute',
    'Rename Package'
}


def extract_rename_pairs(refactoring_changes):
    """Extract rename pairs from refactoring changes using regex patterns."""
    rename_pairs = set()
    
    for refactoring_change in refactoring_changes:
        if refactoring_change['type'] not in RENAME_TYPES:
            continue
            
        old_name = ''
        new_name = ''
        
        if refactoring_change['type'] == 'Rename Class':
            match = re.search(r"Rename Class .*\.([A-Za-z0-9_]+) renamed to .*\.([A-Za-z0-9_]+)", refactoring_change['description'])
            if match:
                old_name = match.group(1)
                new_name = match.group(2)
            
        elif refactoring_change['type'] == 'Rename Method':
            match = re.search(r"Rename Method .*? ([A-Za-z0-9_]+)\(.*?\)\s*:\s*.*? renamed to .*? ([A-Za-z0-9_]+)\(", refactoring_change['description'])
            if match:
                old_name = match.group(1)
                new_name = match.group(2)
            
        elif refactoring_change['type'] == 'Rename Variable':
            match = re.search(r"Rename Variable ([A-Za-z0-9_]+) ?: .*? to ([A-Za-z0-9_]+) ?: .*?", refactoring_change['description'])
            if match:
                old_name = match.group(1)
                new_name = match.group(2)
                
        elif refactoring_change['type'] == 'Rename Attribute':
            match = re.search(r"Rename Attribute ([A-Za-z0-9_]+) ?: .*? to ([A-Za-z0-9_]+) ?: .*? in class", refactoring_change['description'])
            if match:
                old_name = match.group(1)
                new_name = match.group(2)
                
        elif refactoring_change['type'] == 'Rename Parameter':    
            match = re.search(r"Rename Parameter ([A-Za-z0-9_]+) ?: .*? to ([A-Za-z0-9_]+) ?: .*? in method", refactoring_change['description'])
            if match:
                old_name = match.group(1)
                new_name = match.group(2)
        
        if old_name and new_name:
            rename_type = refactoring_change['type'].lower().replace('_', ' ').title()
            rename_pairs.add((rename_type, f'{old_name} -> {new_name}'))
    
    return rename_pairs


def run_refactoring_miner_on_commit(project_name, commit_hash):
    """Run RefactoringMiner on a specific commit and extract rename pairs."""
    
    print(f"Processing project: {project_name}")
    print(f"Commit hash: {commit_hash}")
    
    # Step 1: Setup project and checkout to commit
    try:
        project = pm.EvalProject(project_name)
        project.checkout(commit_hash, force=True)
        print(f"Successfully checked out to {commit_hash}")
        
    except Exception as e:
        print(f"Error setting up project {project_name}: {e}")
        return None
    
    # Step 2: Run RefactoringMiner on the commit
    try:
        print("Running RefactoringMiner on commit...")
        all_refactorings = rminer.default_runner.run(project.get_project_path(), str(commit_hash))
        
        print(f"Total refactorings detected: {len(all_refactorings)}")
        
        # Filter for rename refactorings only
        rename_refactorings = [r for r in all_refactorings if r.type in RENAME_TYPES]
        print(f"Rename refactorings detected: {len(rename_refactorings)}")
        
        # Convert to dictionaries for processing
        refactoring_changes = [r.model_dump() for r in rename_refactorings]
        
        # Extract rename pairs
        rename_pairs = extract_rename_pairs(refactoring_changes)
        
        return {
            "project_name": project_name,
            "commit_hash": commit_hash,
            "total_refactorings": len(all_refactorings),
            "rename_refactorings": len(rename_refactorings),
            "rename_pairs": list(rename_pairs),
            "raw_refactorings": refactoring_changes
        }
        
    except Exception as e:
        print(f"Error running RefactoringMiner: {e}")
        return None


def main():
    """Main function to run the script."""
    
    # Parse command line arguments
    # parser = argparse.ArgumentParser(description='Extract rename pairs from a specific commit using RefactoringMiner')
    # parser.add_argument('--project', type=str, required=True,
    #                     help='Project name (e.g., "argouml", "ratpack", "flink")')
    # parser.add_argument('--commit', type=str, required=True,
    #                     help='Commit hash to analyze')
    # parser.add_argument('--output-file', type=str, default='rename_pairs.json',
    #                     help='Output JSON file to save results (default: rename_pairs.json)')
    #
    # args = parser.parse_args()
    
    # Configuration
    project_name = "intellij-community"
    commit_hash = "5bb7a69aefc61c81d7bacf9eb878987434b7bc33"
    # output_file = args.output_file
    
    print("=== Rename Pair Extraction ===")
    print(f"Project: {project_name}")
    print(f"Commit: {commit_hash}")
    # print(f"Output file: {output_file}")
    print()
    
    # Run RefactoringMiner and extract rename pairs
    result = run_refactoring_miner_on_commit(project_name, commit_hash)
    
    if result:
        print(f"\n=== Results ===")
        print(f"Total refactorings: {result['total_refactorings']}")
        print(f"Rename refactorings: {result['rename_refactorings']}")
        print(f"Rename pairs extracted: {len(result['rename_pairs'])}")
        
        # Extract unique rename pairs with their types
        unique_pairs = set(result['rename_pairs'])
        
        print(f"\n=== Unique Rename Pairs ===")
        print(f"Total unique pairs: {len(unique_pairs)}")
        for rename_type, pair in sorted(unique_pairs):
            print(f"{rename_type}: {pair}")
        
        # # Save results to JSON file
        # with open(output_file, 'w') as f:
        #     json.dump(result, f, indent=4)
        # print(f"\nResults saved to: {output_file}")
        #
    else:
        print("Failed to extract rename pairs.")


if __name__ == "__main__":
    main() 