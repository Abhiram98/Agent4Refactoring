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
    results = defaultdict(list)
    total_files_analyzed = 0
    refactoring_counts = defaultdict(int)
    
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
                            # Count refactorings by type
                            for ref in rename_refs:
                                refactoring_counts[ref['type']] += 1
                            
                            # Store the results
                            result = {
                                'file': file.name,
                                'repository': repository,
                                'commit_sha': commit_sha,
                                'refactorings': rename_refs
                            }
                            results[batch_dir.name].append(result)
                    
            except json.JSONDecodeError:
                print(f"Error reading {file}")
                continue
            except Exception as e:
                print(f"Error processing {file}: {e}")
                continue
                
    return results, total_files_analyzed, refactoring_counts

def save_results_to_csv(results, output_dir):
    """
    Save the results to CSV files
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)
    
    # Save summary CSV with all rename refactorings
    summary_file = output_dir / "rename_refactorings_summary.csv"
    with open(summary_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'Batch',
            'File',
            'Repository',
            'Commit SHA',
            'Refactoring Type',
            'Description'
        ])
        
        for batch, batch_results in results.items():
            for file_result in batch_results:
                for refactoring in file_result['refactorings']:
                    writer.writerow([
                        batch,
                        file_result['file'],
                        file_result['repository'],
                        file_result['commit_sha'],
                        refactoring['type'],
                        refactoring.get('description', '')
                    ])
    
    # Save detailed results per refactoring type
    for refactoring_type in RENAME_TYPES:
        type_file = output_dir / f"{refactoring_type.lower().replace(' ', '_')}_details.csv"
        with open(type_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Batch',
                'File',
                'Repository',
                'Commit SHA',
                'Description'
            ])
            
            for batch, batch_results in results.items():
                for file_result in batch_results:
                    for refactoring in file_result['refactorings']:
                        if refactoring['type'] == refactoring_type:
                            writer.writerow([
                                batch,
                                file_result['file'],
                                file_result['repository'],
                                file_result['commit_sha'],
                                refactoring.get('description', '')
                            ])

def main():
    # Setup paths
    base_dir = Path(os.getcwd())
    results_dir = base_dir / "refactoring_results"
    output_dir = base_dir / "rename_analysis_results"
    
    print("Analyzing refactoring results for rename refactorings...")
    results, total_files_analyzed, refactoring_counts = collect_rename_refactorings(results_dir)
    
    print("\nSaving results to CSV files...")
    save_results_to_csv(results, output_dir)
    
    # Print summary
    total_files_with_renames = sum(len(files) for files in results.values())
    print(f"\nAnalysis complete!")
    print(f"Total files analyzed: {total_files_analyzed}")
    print(f"Files with rename refactorings: {total_files_with_renames} ({(total_files_with_renames/total_files_analyzed*100):.1f}% of analyzed)")
    print(f"Results saved in: {output_dir}")
    
    # Print breakdown by refactoring type
    print("\nBreakdown by refactoring type:")
    total_renames = sum(refactoring_counts.values())
    for refactoring_type, count in sorted(refactoring_counts.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / total_renames * 100) if total_renames > 0 else 0
        print(f"{refactoring_type}: {count} ({percentage:.1f}%)")

if __name__ == "__main__":
    main() 