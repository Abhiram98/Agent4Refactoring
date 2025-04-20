# PA Tool Walkthrough

This directory contains tools for analyzing pure rename commits in Git repositories. The tools help identify and analyze commits that primarily involve variable renaming operations.

## Requirements

Install the required packages using:
```bash
pip install -r requirements.txt
```

## Environment Variables

For `analyze_pure_rename_commits_llm.py`, you need to set up the following environment variables:
- `GRAZIE_API_KEY`: Your Grazie API key for LLM access

## Workflow

1. First, use `collect_commits.py` to gather commit data and run RefactoringMiner
2. Then, use `extract_rename_commits_only.py` to extract all rename-related refactorings
3. Next, use `filter_pure_rename_variables.py` to identify pure rename commits
4. Finally, use `analyze_pure_rename_commits_llm.py` to get detailed analysis of the rename patterns

## Files Overview

### 1. collect_commits.py
This script collects commit information from a Git repository and runs RefactoringMiner on the commits. It uses parallel processing to efficiently gather commit data.

**Usage:**
```bash
python3 collect_commits.py --repo_path /path/to/repo
```

**Arguments:**
- `--repo_path`: Path to the Git repository (required)
- `--branch`: Branch to collect commits from (default: auto-detect)
- `--output`: Output file to save commit SHAs (default: commits.txt)
- `--refactoring-output`: Directory to save RefactoringMiner results (default: refactoring_results)
- `--threads`: Number of threads for parallel processing (default: number of CPU cores)

### 2. extract_rename_commits_only.py
This script processes the RefactoringMiner results to extract all rename-related refactorings (Class, Method, Variable, Parameter, Attribute, Package). It generates detailed CSV files for each type of rename operation.

**Usage:**
```bash
python3 extract_rename_commits_only.py
```

**Input/Output:**
- Reads from: `./refactoring_results/` (created by collect_commits.py)
- Outputs to: `./rename_analysis_results/`
  - `rename_refactorings_summary.csv`: All rename refactorings
  - Individual CSV files for each rename type (e.g., `rename_class_details.csv`, `rename_method_details.csv`, etc.)

### 3. filter_pure_rename_variables.py
This script filters the rename variable refactorings to identify those that are "pure" renames (only the name changes, not the type or structure).

**Usage:**
```bash
python3 filter_pure_rename_variables.py
```


### 4. analyze_pure_rename_commits_llm.py
This script uses LLM (Language Model) to analyze the pure rename commits in detail. It provides insights into the renaming patterns and their impact.

**Usage:**
```bash
python3 analyze_pure_rename_commits_llm.py
```