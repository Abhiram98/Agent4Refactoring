#!/usr/bin/env python3
import json
import subprocess
import os
import sys
import argparse
from pathlib import Path

def run_command(command, cwd=None):
    """Run a shell command and return the result."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        print(f"Error running command '{command}': {e}")
        return -1, "", str(e)

def checkout_commit(repo_path, commit_hash):
    """Checkout a specific commit in the repository."""
    print(f"Checking out commit {commit_hash}...")
    
    # Stash any local changes first
    run_command("git stash", cwd=repo_path)
    
    # Now checkout the commit
    returncode, stdout, stderr = run_command(f"git checkout {commit_hash}", cwd=repo_path)
    
    if returncode != 0:
        print(f"Failed to checkout commit {commit_hash}")
        print(f"Error: {stderr}")
        return False
    
    return True

def count_compile_errors(repo_path):
    """Run maven compile and count Java compilation errors."""
    print("Running mvn clean compile...")
    
    # Run mvn clean compile
    returncode, stdout, stderr = run_command("mvn clean compile > compile.log 2>&1", cwd=repo_path)
    
    # Count compile errors using the new command
    print("Counting compilation errors...")
    returncode, stdout, stderr = run_command("grep -Eo '\\[ERROR\\] [^ ]+\\.java:\\[[0-9]+,[0-9]+\\]' compile.log | sed 's/^\\[ERROR\\] //' | sort -u | wc -l", cwd=repo_path)
    
    if returncode != 0:
        print(f"Failed to count errors: {stderr}")
        return 0
    
    try:
        error_count = int(stdout.strip())
        return error_count
    except ValueError:
        print(f"Could not parse error count from: {stdout}")
        return 0

def process_json_file(json_file_path, repo_path):
    """Process the JSON file and check compile errors for each commit."""
    
    # Load the JSON file
    with open(json_file_path, 'r') as f:
        data = json.load(f)
    
    results = []
    
    # Get current directory to return to later
    original_cwd = os.getcwd()
    
    try:
        # Process each entry
        for i, entry in enumerate(data):
            print(f"\n--- Processing entry {i+1}/{len(data)} (ID: {entry['id']}) ---")
            
            # Skip if detected_refactorings is empty
            if len(entry.get('detected_refactorings', [])) == 0:
                print(f"Skipping entry {entry['id']} - no detected refactorings")
                continue
            
            commit_hash = entry['new_commit_hash']
            
            # Checkout the commit
            if not checkout_commit(repo_path, commit_hash):
                print(f"Failed to checkout commit {commit_hash}, skipping...")
                continue
            
            # Count compile errors
            error_count = count_compile_errors(repo_path)
            
            # Store result
            result = {
                'id': entry['id'],
                'new_commit_hash': commit_hash,
                'detected_refactorings_count': len(entry.get('detected_refactorings', [])),
                'compile_errors': error_count
            }
            
            results.append(result)
            
            print(f"Entry {entry['id']}: {error_count} compile errors")
    
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    
    finally:
        # Return to original directory
        os.chdir(original_cwd)
    
    return results

def save_results(results, output_file):
    """Save the results to a JSON file."""
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {output_file}")

def main():
    parser = argparse.ArgumentParser(description='Check compilation errors for commits in refactoring results')
    parser.add_argument('json_file', help='Path to the JSON file with refactoring results')
    parser.add_argument('repo_path', help='Path to the repository')
    parser.add_argument('--output', '-o', default='compile_errors_results.json', help='Output file name (default: compile_errors_results.json)')
    
    args = parser.parse_args()
    
    # Validate inputs
    if not os.path.exists(args.json_file):
        print(f"Error: JSON file '{args.json_file}' not found")
        sys.exit(1)
    
    if not os.path.exists(args.repo_path):
        print(f"Error: Repository path '{args.repo_path}' not found")
        sys.exit(1)
    
    if not os.path.exists(os.path.join(args.repo_path, '.git')):
        print(f"Error: '{args.repo_path}' is not a git repository")
        sys.exit(1)
    
    if not os.path.exists(os.path.join(args.repo_path, 'pom.xml')):
        print(f"Error: pom.xml not found in '{args.repo_path}'")
        sys.exit(1)
    
    print(f"Processing JSON file: {args.json_file}")
    print(f"Repository path: {args.repo_path}")
    print(f"Output file: {args.output}")
    
    # Process the JSON file
    results = process_json_file(args.json_file, args.repo_path)
    
    # Save results
    if results:
        save_results(results, args.output)
        print(f"\nProcessed {len(results)} entries successfully")
    else:
        print("No results to save")

if __name__ == "__main__":
    main()