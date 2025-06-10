import os
import json
from pathlib import Path
from collections import defaultdict
import csv

# Define the rename refactoring types we're interested in
RENAME_TYPES = {
    'Rename Class',
    'Rename Method',
    'Rename Variable',
    'Rename Parameter',
    'Rename Attribute',
    'Rename Package'
}

def collect_rename_refactorings(results_dir):
    """
    Analyze refactoring results and collect rename refactorings from batch directories
    """
    results = []
    total_files_analyzed = 0
    count = 0
    
    print(f"Analyzing refactorings from: {results_dir}")
    
    # Process each batch directory
    for batch_dir in sorted(Path(results_dir).glob("batch_*")):
        if not batch_dir.is_dir():
            continue
            
        print(f"\nProcessing {batch_dir.name}...")
        
        # Process each refactoring file in the batch
        for file in batch_dir.glob("refactoring_*.json"):
            total_files_analyzed += 1
            
            try:
                with open(file, 'r') as f:
                    data = json.load(f)
                    
                    # Check if the file has the expected structure
                    if 'commits' not in data:
                        print(f"Warning: {file.name} doesn't have 'commits' field, skipping")
                        continue
                    
                    # Process each commit in the file
                    for commit in data['commits']:
                        commit_sha = commit.get('sha1', 'unknown')
                        repository = commit.get('repository', 'unknown')
                        
                        # Get refactorings for this commit
                        refactorings = commit.get('refactorings', [])
                        
                        # Filter rename refactorings
                        rename_refs = [ref for ref in refactorings if ref['type'] in RENAME_TYPES]
                        
                        if rename_refs:
                            temp = commit.copy()
                            temp['refactorings'] = rename_refs
                            results.append(temp)
                            count += 1
                    
            except json.JSONDecodeError:
                print(f"Error reading {file}")
                continue
            except Exception as e:
                print(f"Error processing {file}: {e}")
                continue
                
    return results, total_files_analyzed, count

def save_results_to_json(results, output_file):
    # Convert to Path object if it's a string
    if isinstance(output_file, str):
        output_file = Path(output_file)
    
    # Create output directory if it doesn't exist
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)

def collect_rename_refactorings_count(results_dir):
    """
    Analyze refactoring results and collect rename refactorings from batch directories
    """
    results = []
    total_files_analyzed = 0
    count = 0
    
    print(f"Analyzing refactorings from: {results_dir}")
    
    # Process each batch directory
    for batch_dir in sorted(Path(results_dir).glob("batch_*")):
        if not batch_dir.is_dir():
            continue
            
        print(f"\nProcessing {batch_dir.name}...")
        
        # Process each refactoring file in the batch
        for file in batch_dir.glob("refactoring_*.json"):
            total_files_analyzed += 1
            
            try:
                with open(file, 'r') as f:
                    data = json.load(f)
                    
                    # Check if the file has the expected structure
                    if 'commits' not in data:
                        print(f"Warning: {file.name} doesn't have 'commits' field, skipping")
                        continue
                    
                    # Process each commit in the file
                    for commit in data['commits']:
                        temp = {}
                        commit_sha = commit.get('sha1', 'unknown')
                        repository = commit.get('repository', 'unknown')
                        
                        # Get refactorings for this commit
                        refactorings = commit.get('refactorings', [])
                        
                        # Filter rename refactorings
                        rename_refs = [ref for ref in refactorings if ref['type'] in RENAME_TYPES]
                        
                        if rename_refs:
                            temp['commit'] = commit_sha
                            temp['count'] = len(rename_refs)
                            results.append(temp)
                            count += 1
                    
            except json.JSONDecodeError:
                print(f"Error reading {file}")
                continue
            except Exception as e:
                print(f"Error processing {file}: {e}")
                continue
                
    return results, total_files_analyzed, count

def save_results_to_csv(results, output_path):
    columns_to_use = ['commit', 'count']
    
    # Convert to Path object if it's a string
    if isinstance(output_path, str):
        output_path = Path(output_path)
    
    # If it's a directory path, append the filename
    if output_path.is_dir() or not output_path.suffix:
        output_file = output_path / "rename_analysis_results_count.csv"
        # Create parent directory if needed
        output_file.parent.mkdir(parents=True, exist_ok=True)
    else:
        # It's already a file path, just ensure parent directory exists
        output_file = output_path
        output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns_to_use)
        writer.writeheader()
        writer.writerows(results)

def main():
    # Setup paths
    base_dir = Path(os.getcwd())
    results_dir = base_dir / "refactoring_results_camunda"
    output_dir = base_dir / "rename_analysis_results_camunda"
    
    print("Analyzing refactoring results for rename refactorings...")
    results, total_files_analyzed, count = collect_rename_refactorings(results_dir)

    print(f"Total Rename commit count: {count}")
    
    print("\nSaving results to JSON file...")
    save_results_to_json(results, output_dir / "rename_analysis_results.json")
    
    # Print summary
    total_files_with_renames = len(results)
    print(f"\nAnalysis complete!")
    print(f"Total files analyzed: {total_files_analyzed}")
    print(f"Commits with rename refactorings: {total_files_with_renames}")
    if total_files_analyzed > 0:
        print(f"Percentage of files with renames: {(total_files_with_renames/total_files_analyzed*100):.1f}%")
    print(f"Results saved in: {output_dir}")
    
    # Print breakdown by refactoring type
    # print("\nBreakdown by refactoring type:")
    # total_renames = sum(refactoring_counts.values())
    # for refactoring_type, count in sorted(refactoring_counts.items(), key=lambda x: x[1], reverse=True):
    #     percentage = (count / total_renames * 100) if total_renames > 0 else 0
    #     print(f"{refactoring_type}: {count} ({percentage:.1f}%)")

if __name__ == "__main__":
    main() 