import os
import subprocess
from pathlib import Path
import argparse
from tqdm import tqdm
import concurrent.futures
from typing import List

CPU_COUNT = os.cpu_count()

def get_default_branch(repo_path):
    """Get the default branch name of the repository"""
    try:
        # Change to repository directory
        original_dir = os.getcwd()
        os.chdir(repo_path)
        
        # Get default branch name
        cmd = "git symbolic-ref refs/remotes/origin/HEAD | sed 's@^refs/remotes/origin/@@'"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode != 0:
            # Try alternative method if the first one fails
            cmd = "git branch -r | grep 'origin/HEAD' | cut -d'/' -f3"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
        # Change back to original directory
        os.chdir(original_dir)
        
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except Exception as e:
        print(f"Error getting default branch: {e}")
        return None

def get_commits(repo_path, branch=None):
    """Get all commit SHAs from a local Git repository"""
    try:
        # Change to repository directory
        original_dir = os.getcwd()
        os.chdir(repo_path)
        
        # If branch is not specified, try to get the default branch
        if not branch:
            branch = get_default_branch(repo_path)
            if not branch:
                print("Could not determine default branch. Please specify a branch name.")
                return []
            print(f"Using default branch: {branch}")
        
        print(f"\nFetching all commits from branch '{branch}'...")
        
        # Get all commit SHAs without any limit
        cmd = f"git rev-list --reverse {branch}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"Error running git command: {result.stderr}")
            return []
            
        commits = result.stdout.strip().split('\n')
        print(f"Found {len(commits)} commits")
        
        # Change back to original directory
        os.chdir(original_dir)
        return commits
        
    except Exception as e:
        print(f"Error fetching commits: {e}")
        return []

def save_commits_to_file(commits, output_file):
    """Save commit SHAs to a file"""
    try:
        with open(output_file, 'w') as f:
            for commit in commits:
                f.write(f"{commit}\n")
        print(f"Saved {len(commits)} commit SHAs to {output_file}")
    except Exception as e:
        print(f"Error saving commits to file: {e}")

def split_into_n_batches(items: List[str], n: int) -> List[List[str]]:
    """Split a list into exactly n batches with equal size, adding any remainder to the last batch"""
    if not items:
        return []
    if n <= 0:
        raise ValueError("Number of batches must be positive")
    if n > len(items):
        n = len(items)
    
    # Calculate the base size of each batch
    base_size = len(items) // n
    
    # Create exactly n batches
    batches = []
    for i in range(n-1):  # Create n-1 batches of equal size
        start_idx = i * base_size
        end_idx = start_idx + base_size
        batches.append(items[start_idx:end_idx])
    
    # Last batch gets the remainder
    batches.append(items[(n-1)*base_size:])
    
    return batches

def process_commit_batch(repo_path: str, batch: List[str], output_dir: str, batch_index: int) -> bool:
    """Process a batch of commits using RefactoringMiner"""
    try:
        # Create output directory for this batch
        batch_output_dir = Path(output_dir) / f"batch_{batch_index}"
        batch_output_dir.mkdir(exist_ok=True)
        
        # Skip if batch has less than 2 commits (can't compare)
        if len(batch) < 2:
            print(f"Batch {batch_index} has only {len(batch)} commit(s), skipping...")
            return True
        
        # Get the first and last commit in the batch
        start_commit = batch[0]
        end_commit = batch[-1]
        
        print(f"Processing batch {batch_index} ({len(batch)} commits) from {start_commit} to {end_commit}")
        # Create output file path
        output_file = batch_output_dir / f"refactoring_{start_commit[:7]}_{end_commit[:7]}.json"
        
        # Run RefactoringMiner between start and end commit
        cmd = f"RefactoringMiner -bc {repo_path} {start_commit} {end_commit} -json {output_file}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"Error processing commits {start_commit[:7]} to {end_commit[:7]}: {result.stderr}")
            return False
            
        print(f"Processed batch {batch_index} ({len(batch)} commits) from {start_commit[:7]} to {end_commit[:7]}")
        return True
    except Exception as e:
        print(f"Error processing batch {batch_index}: {e}")
        return False

def process_commits_with_refactoringminer(repo_path: str, commits: List[str], output_dir: str, num_threads: int = CPU_COUNT):
    """Process commits in parallel using RefactoringMiner"""
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    # Ensure we have enough commits to process
    if len(commits) < 2:
        print("Not enough commits to process")
        return
    
    # Adjust number of threads if needed
    # We want at least 1 commit per batch, but ideally more
    if len(commits) < num_threads:
        num_threads = len(commits)
        print(f"Adjusting to {num_threads} threads based on number of commits")
    
    # Split commits into exactly num_threads batches
    batches = split_into_n_batches(commits, num_threads)
    
    # Verify we have the right number of batches
    actual_batch_count = len(batches)
    if actual_batch_count != num_threads:
        print(f"Warning: Created {actual_batch_count} batches instead of requested {num_threads}")
    
    print(f"\nProcessing {len(commits)} commits in {actual_batch_count} batches using {num_threads} threads...")
    
    # Process batches in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = []
        for i, batch in enumerate(batches):
            future = executor.submit(process_commit_batch, repo_path, batch, str(output_path), i)
            futures.append(future)
        
        # Wait for all batches to complete
        for i, future in enumerate(concurrent.futures.as_completed(futures)):
            success = future.result()
            if success:
                print(f"Batch {i} completed successfully")
            else:
                print(f"Batch {i} failed")

def main():
    parser = argparse.ArgumentParser(description='Collect commit SHAs and process with RefactoringMiner')
    parser.add_argument('--repo_path', help='Path to the local Git repository')
    parser.add_argument('--branch', help='Branch to collect commits from (default: auto-detect)')
    parser.add_argument('--output', default='commits.txt', help='Output file to save commit SHAs (default: commits.txt)')
    parser.add_argument('--refactoring-output', default='refactoring_results', 
                       help='Directory to save RefactoringMiner results (default: refactoring_results)')
    parser.add_argument('--threads', type=int, default=10, 
                       help='Number of threads for parallel processing (default: # of CPU_COUNT)')
    
    args = parser.parse_args()
    
    # Verify repository path exists
    repo_path = Path(args.repo_path)
    if not repo_path.exists():
        print(f"Error: Repository path '{repo_path}' does not exist")
        return
        
    # Verify it's a Git repository
    if not (repo_path / '.git').exists():
        print(f"Error: '{repo_path}' is not a Git repository")
        return
    
    try:
        # Get commits
        commits = get_commits(str(repo_path), args.branch)
        
        if commits:
            # Save commits to file
            save_commits_to_file(commits, args.output)
            
            # Process commits with RefactoringMiner
            process_commits_with_refactoringminer(
                str(repo_path),
                commits,
                args.refactoring_output,
                args.threads
            )
            
    except Exception as e:
        print(f"Error processing repository: {e}")

if __name__ == "__main__":
    main() 