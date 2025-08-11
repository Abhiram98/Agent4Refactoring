import os
import subprocess
from pathlib import Path
import argparse
from tqdm import tqdm
import concurrent.futures
from typing import List
from datetime import datetime
import pandas as pd
import json

CPU_COUNT = os.cpu_count() - 4


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


def get_commits(repo_path, branch=None, max_commits=10000):
    """Get the latest commits from a local Git repository"""
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

        print(f"\nFetching latest {max_commits} commits from branch '{branch}'...")

        # Get the latest commits (newest first) with a limit
        cmd = f"git rev-list --max-count={max_commits} {branch}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"Error running git command: {result.stderr}")
            return []

        commits = result.stdout.strip().split('\n')
        # Reverse to get chronological order (oldest first) for RefactoringMiner processing
        commits = commits[::-1]
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
        # Create directory if it doesn't exist
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Check if file already exists to determine write mode
        file_exists = output_path.exists()
        mode = 'a' if file_exists else 'w'

        with open(output_file, mode) as f:
            for commit in commits:
                f.write(f"{commit}\n")

        action = "Appended" if file_exists else "Saved"
        print(f"{action} {len(commits)} commit SHAs to {output_file}")
    except Exception as e:
        print(f"Error saving commits to file: {e}")


def split_into_batches_with_max_size(items: List[str], max_batch_size: int, num_threads: int) -> List[List[str]]:
    """Split a list into batches with a maximum size limit"""
    if not items:
        return []
    if max_batch_size <= 0:
        raise ValueError("Maximum batch size must be positive")

    # Ensure minimum batch size of 2 commits
    min_batch_size = 2
    # Calculate optimal batch size, ensuring it's at least 2 commits
    optimal_batch_size = max(min_batch_size, min(max_batch_size, max(2, len(items) // num_threads)))

    batches = []
    for i in range(0, len(items), optimal_batch_size):
        batch = items[i:i + optimal_batch_size]
        if len(batch) >= min_batch_size:  # Only add batches with at least 2 commits
            batches.append(batch)

    return batches


def process_commit_batch(repo_path: str, batch: List[str], output_dir: str, batch_index: int,
                         timeout_factor: int = 1) -> bool:
    """Process a batch of commits using RefactoringMiner"""
    try:
        # Create output directory for this batch
        batch_output_dir = Path(output_dir) / f"batch_{batch_index}"
        batch_output_dir.mkdir(parents=True, exist_ok=True)

        # Skip if batch has less than 2 commits (can't compare)
        if len(batch) < 2:
            print(f"Warning: Batch {batch_index} has only {len(batch)} commit(s), skipping...")
            return False  # Return False to indicate skipped batch

        # Get the first and last commit in the batch
        start_commit = batch[0]
        end_commit = batch[-1]

        print(f"Processing batch {batch_index} ({len(batch)} commits) from {start_commit[:7]} to {end_commit[:7]}")
        # Create output file path
        output_file = batch_output_dir / f"refactoring_{start_commit[:7]}_{end_commit[:7]}.json"

        # Calculate timeout based on batch size (30 minutes per 100 commits, minimum 10 minutes)
        # Multiply by timeout_factor for retries
        timeout_minutes = max(10, (len(batch) // 100) * 30) * timeout_factor
        timeout_seconds = timeout_minutes * 60

        # Run RefactoringMiner between start and end commit with dynamic timeout
        cmd = f"RefactoringMiner -bc {repo_path} {start_commit} {end_commit} -json {output_file}"
        print(f"Running batch {batch_index} with {timeout_minutes}-minute timeout...")
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout_seconds)

        if result.returncode != 0:
            print(f"Error processing commits {start_commit[:7]} to {end_commit[:7]}: {result.stderr}")
            return False

        print(f"Processed batch {batch_index} ({len(batch)} commits) from {start_commit[:7]} to {end_commit[:7]}")
        return True
    except subprocess.TimeoutExpired:
        print(f"Timeout: Batch {batch_index} processing took longer than {timeout_minutes} minutes")
        return False
    except Exception as e:
        print(f"Error processing batch {batch_index}: {e}")
        return False


def process_commits_with_refactoringminer(repo_path: str, commits: List[str], output_dir: str,
                                          num_threads: int = CPU_COUNT, max_batch_size: int = 500,
                                          start_batch_index: int = 0):
    """Process commits in parallel using RefactoringMiner"""
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Ensure we have enough commits to process
    if len(commits) < 2:
        print("Not enough commits to process")
        return

    # Split commits into batches with size limit
    batches = split_into_batches_with_max_size(commits, max_batch_size, num_threads)

    actual_batch_count = len(batches)
    avg_batch_size = len(commits) // actual_batch_count if actual_batch_count > 0 else 0

    print(
        f"\nProcessing {len(commits)} commits in {actual_batch_count} batches (avg {avg_batch_size} commits per batch)")
    print(f"Maximum batch size: {max_batch_size}")
    print(f"Using {min(num_threads, actual_batch_count)} threads...")

    successful_batches = 0
    failed_batches = 0
    failed_batch_indices = []

    # Process batches in parallel, but limit concurrent batches to num_threads
    max_workers = min(num_threads, actual_batch_count)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for i, batch in enumerate(batches):
            future = executor.submit(process_commit_batch, repo_path, batch, str(output_path), i + start_batch_index,
                                     timeout_factor=1)
            futures.append((i, future))

        # Wait for all batches to complete
        for i, future in futures:
            success = future.result()
            if success:
                print(f"Batch {i + start_batch_index} completed successfully")
                successful_batches += 1
            else:
                print(f"Batch {i + start_batch_index} failed")
                failed_batches += 1
                failed_batch_indices.append(i + start_batch_index)

    # Retry failed batches with smaller size and increased timeout
    if failed_batch_indices:
        print(f"\nRetrying {len(failed_batch_indices)} failed batches with smaller size and increased timeout...")
        retry_batches = []
        for i in failed_batch_indices:
            original_batch = batches[i - start_batch_index]
            # Split failed batch into smaller batches of 100 commits each
            for j in range(0, len(original_batch), 100):
                if j + 100 <= len(original_batch):  # Ensure we have at least 100 commits
                    retry_batches.append(original_batch[j:j + 100])
                else:
                    # Handle remaining commits
                    retry_batches.append(original_batch[j:])

        print(f"Created {len(retry_batches)} smaller batches for retry")

        # Process retry batches with increased timeout (factor of 2)
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            retry_futures = []
            for i, batch in enumerate(retry_batches):
                future = executor.submit(process_commit_batch, repo_path, batch, str(output_path),
                                         f"retry_{i + start_batch_index}", timeout_factor=2)
                retry_futures.append(future)

            # Wait for all retry batches to complete
            for i, future in enumerate(concurrent.futures.as_completed(retry_futures)):
                success = future.result()
                if success:
                    print(f"Retry batch {i + start_batch_index} completed successfully")
                    successful_batches += 1
                else:
                    print(f"Retry batch {i + start_batch_index} failed")
                    failed_batches += 1

    print(f"\n=== RefactoringMiner Processing Complete ===")
    print(f"Total batches: {actual_batch_count}")
    print(f"Successful: {successful_batches}")
    print(f"Failed: {failed_batches}")
    print(f"Results saved to: {output_path}")

    return actual_batch_count, successful_batches, failed_batches


def get_commit_date(repo_path, commit_sha):
    """Get the commit date for a given commit SHA"""
    try:
        original_dir = os.getcwd()
        os.chdir(repo_path)

        # Get commit date in ISO format
        cmd = f"git show -s --format=%ci {commit_sha}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

        os.chdir(original_dir)

        if result.returncode == 0:
            date_str = result.stdout.strip()
            # Parse the date (format: 2024-01-01 12:34:56 +0000)
            commit_date = datetime.strptime(date_str.split(' ')[0], "%Y-%m-%d")
            return commit_date
        else:
            print(f"Error getting date for commit {commit_sha}")
            return None
    except Exception as e:
        print(f"Error getting commit date: {e}")
        return None


def get_commit_timestamp(commit_sha, repo_path):
    """Get the timestamp of a commit"""
    try:
        original_dir = os.getcwd()
        os.chdir(repo_path)

        # Get commit timestamp in ISO format
        cmd = f"git show -s --format=%ci {commit_sha}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

        os.chdir(original_dir)

        if result.returncode == 0:
            timestamp_str = result.stdout.strip()
            # Parse the timestamp
            timestamp = pd.to_datetime(timestamp_str)
            return timestamp
        else:
            print(f"Error getting timestamp for commit {commit_sha}: {result.stderr}")
            return None
    except Exception as e:
        print(f"Error processing commit {commit_sha}: {e}")
        return None


def filter_commits_by_date(commits, repo_path, since_date):
    """
    Double-check commit timestamps and filter out commits older than since_date
    """
    if not commits:
        return []

    print(f"Double-checking {len(commits)} commits against date filter: {since_date}")
    cutoff_date = pd.to_datetime(since_date)

    filtered_commits = []
    excluded_count = 0

    for i, commit_sha in enumerate(commits):
        if i % 50 == 0:  # Progress update every 50 commits
            print(f"Checking commit {i + 1}/{len(commits)}: {commit_sha[:8]}")

        # Get the actual commit timestamp
        commit_timestamp = get_commit_timestamp(commit_sha, repo_path)

        if commit_timestamp is None:
            print(f"Warning: Could not get timestamp for commit {commit_sha[:8]}, excluding it")
            excluded_count += 1
            continue

        # Convert to timezone-naive datetime for comparison
        if commit_timestamp.tzinfo is not None:
            commit_timestamp = commit_timestamp.tz_localize(None)

        # Check if commit is from the cutoff date onwards
        if commit_timestamp >= cutoff_date:
            filtered_commits.append(commit_sha)
        else:
            excluded_count += 1
            print(f"Excluding commit {commit_sha[:8]} (date: {commit_timestamp.strftime('%Y-%m-%d')})")

    print(f"Timestamp verification complete:")
    print(f"  - Commits passed filter: {len(filtered_commits)}")
    print(f"  - Commits excluded: {excluded_count}")
    print(f"  - Final commit count: {len(filtered_commits)}")

    return filtered_commits


def get_commits_since_date(repo_path, since_date="2024-01-01", branch=None):
    """
    Get commits from a specific date onwards using git's built-in date filtering.
    Much more efficient than fetching all commits and filtering manually.

    Args:
        repo_path (str): Path to the local Git repository
        since_date (str): Date in format "YYYY-MM-DD" (default: "2024-01-01")
        branch (str): Branch name (default: auto-detect)

    Returns:
        list: List of commit SHAs from the date onwards (chronological order)
    """
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

        print(f"Fetching commits from {since_date} onwards on branch '{branch}'...")

        cmd = f"git rev-list --since='{since_date}' --reverse {branch}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"Error running git command: {result.stderr}")
            return []

        commits = result.stdout.strip().split('\n') if result.stdout.strip() else []
        print(f"Found {len(commits)} commits from {since_date} onwards")

        # Change back to original directory
        os.chdir(original_dir)
        return commits

    except Exception as e:
        print(f"Error fetching commits since date: {e}")
        return []


def get_commits_between_dates_efficient(repo_path, since_date, until_date, branch=None):
    """
    Get commits between two dates using git's built-in date filtering.

    Args:
        repo_path (str): Path to the local Git repository
        since_date (str): Start date in format "YYYY-MM-DD"
        until_date (str): End date in format "YYYY-MM-DD"
        branch (str): Branch name (default: auto-detect)

    Returns:
        list: List of commit SHAs between the dates (chronological order)
    """
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

        print(f"Fetching commits between {since_date} and {until_date} on branch '{branch}'...")

        # Use git's built-in date filtering (much more efficient)
        cmd = f"git rev-list --since='{since_date}' --until='{until_date}' --reverse {branch}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"Error running git command: {result.stderr}")
            return []

        commits = result.stdout.strip().split('\n') if result.stdout.strip() else []
        print(f"Found {len(commits)} commits between {since_date} and {until_date}")

        # Change back to original directory
        os.chdir(original_dir)
        return commits

    except Exception as e:
        print(f"Error fetching commits between dates: {e}")
        return []


def collect_commits_to_date(repo_path, target_date="2024-01-01", branch=None, max_commits=None):
    """
    Collect commits from a given date onwards from a repository

    Args:
        repo_path (str): Path to the local Git repository
        target_date (str): Target date in format "YYYY-MM-DD" (default: "2024-01-01")
        branch (str): Branch name (default: auto-detect)
        max_commits (int): Maximum number of commits to collect (default: None for unlimited)

    Returns:
        list: List of commit SHAs from the target date onwards
    """
    try:
        # Use the new efficient method
        commits = get_commits_since_date(repo_path, target_date, branch)

        # Apply max_commits limit if specified
        if max_commits is not None and len(commits) > max_commits:
            print(f"Limiting to first {max_commits} commits")
            commits = commits[:max_commits]

        return commits

    except Exception as e:
        print(f"Error collecting commits from date: {e}")
        return []


def save_commits_to_date(repo_path, target_date, output_file=None, branch=None, max_commits=10000):
    """
    Collect and save commits up to a given date from a repository

    Args:
        repo_path (str): Path to the local Git repository
        target_date (str): Target date in format "YYYY-MM-DD"
        output_file (str): Output file path (optional)
        branch (str): Branch name (default: auto-detect)
        max_commits (int): Maximum number of commits to collect (default: 10000)
    """
    commits = collect_commits_to_date(repo_path, target_date, branch, max_commits)

    if not commits:
        print(f"No commits found up to {target_date}")
        return

    if not output_file:
        repo_name = Path(repo_path).name
        output_file = f"{repo_name}_commits_to_{target_date}.txt"

    try:
        save_commits_to_file(commits, output_file)
        print(f"Saved {len(commits)} commits to {output_file}")
    except Exception as e:
        print(f"Error saving commits to file: {e}")


def collect_commits_between_dates(repo_path, start_date, end_date, branch=None, max_commits=None):
    """
    Collect commits between two dates from a repository

    Args:
        repo_path (str): Path to the local Git repository
        start_date (str): Start date in format "YYYY-MM-DD"
        end_date (str): End date in format "YYYY-MM-DD"
        branch (str): Branch name (default: auto-detect)
        max_commits (int): Maximum number of commits to collect (default: None for unlimited)

    Returns:
        list: List of commit SHAs between the dates
    """
    try:
        # Use the new efficient method
        commits = get_commits_between_dates_efficient(repo_path, start_date, end_date, branch)

        # Apply max_commits limit if specified
        if max_commits is not None and len(commits) > max_commits:
            print(f"Limiting to first {max_commits} commits")
            commits = commits[:max_commits]

        return commits

    except Exception as e:
        print(f"Error collecting commits between dates: {e}")
        return []


def process_single_commit_with_refactoringminer(repo_path: str, commit_sha: str, output_file: str,
                                                timeout_minutes: int = 30) -> tuple[bool, dict]:
    """Process a single commit using RefactoringMiner with -c flag"""
    try:
        # Create output directory if it doesn't exist
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"Processing single commit {commit_sha[:7]} with RefactoringMiner...")

        # Calculate timeout in seconds
        timeout_seconds = timeout_minutes * 60

        # Run RefactoringMiner on single commit with -c flag
        cmd = f"/Users/moul7361/Desktop/AI-Agents/tool/RefactoringMiner/build/distributions/RefactoringMiner-3.0.11/bin/RefactoringMiner -c {repo_path} {commit_sha} -json {output_file}"
        print(f"Running command: {cmd}")
        print(f"Timeout: {timeout_minutes} minutes")

        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout_seconds)

        if result.returncode != 0:
            print(f"Error processing commit {commit_sha[:7]}: {result.stderr}")
            return False, {}

        print(f"Successfully processed commit {commit_sha[:7]}")
        print(f"Results saved to: {output_file}")

        # Read and return the output file content as JSON
        try:
            with open(output_file, 'r') as f:
                output_content = json.load(f)
            return True, output_content
        except Exception as e:
            print(f"Warning: Could not read or parse JSON output file {output_file}: {e}")
            return True, {}

    except subprocess.TimeoutExpired:
        print(f"Timeout: Processing commit {commit_sha[:7]} took longer than {timeout_minutes} minutes")
        return False, {}
    except Exception as e:
        print(f"Error processing commit {commit_sha[:7]}: {e}")
        return False, {}


def main():
    parser = argparse.ArgumentParser(description='Collect commit SHAs and process with RefactoringMiner')
    parser.add_argument('--repo_path', help='Path to the local Git repository')
    parser.add_argument('--branch', help='Branch to collect commits from (default: auto-detect)')
    parser.add_argument('--output', default='commits.txt',
                        help='Output file to save commit SHAs (default: commits.txt)')
    parser.add_argument('--refactoring-output', default='refactoring_results',
                        help='Directory to save RefactoringMiner results (default: refactoring_results)')
    parser.add_argument('--threads', type=int, default=10,
                        help='Number of threads for parallel processing (default: 10)')
    parser.add_argument('--max-commits', type=int, default=20000,
                        help='Maximum number of latest commits to process (default: 20000)')
    parser.add_argument('--max-batch-size', type=int, default=500,
                        help='Maximum number of commits per batch (default: 500)')

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
        print("=== Starting Commit Collection and RefactoringMiner Processing ===")

        # Get commits
        commits = get_commits(str(repo_path), args.branch, args.max_commits)

        if commits:
            # Save commits to file
            save_commits_to_file(commits, args.output)

            # Process commits with RefactoringMiner
            actual_batch_count, successful_batches, failed_batches = process_commits_with_refactoringminer(
                str(repo_path),
                commits,
                args.refactoring_output,
                args.threads,
                args.max_batch_size
            )

            print("\n=== All Processing Complete! ===")
            print("Script finished successfully. You can now use the terminal.")
        else:
            print("No commits found to process.")

    except Exception as e:
        print(f"Error processing repository: {e}")
    except KeyboardInterrupt:
        print("\nProcessing interrupted by user.")
    finally:
        print("Exiting script...")


if __name__ == "__main__":
    main()