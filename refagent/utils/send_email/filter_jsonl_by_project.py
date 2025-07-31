#!/usr/bin/env python3
"""
Script to filter JSONL file by project field and save to separate files.

Usage:
    python filter_jsonl_by_project.py <input_file.jsonl>
    
This script will:
1. Read each line from the input JSONL file
2. Parse the JSON and extract the "project" field
3. Group records by project
4. Save each project's records to temp_{project}.jsonl
"""

import json
import os
import sys
from collections import defaultdict
from pathlib import Path


def filter_jsonl_by_project(input_file):
    """
    Filter JSONL file by project field and save to separate files.
    
    Args:
        input_file (str): Path to input JSONL file
    """
    if not os.path.exists(input_file):
        print(f"Error: Input file '{input_file}' does not exist")
        return
    
    # Dictionary to store records grouped by project
    projects_data = defaultdict(list)
    
    print(f"Reading from {input_file}...")
    
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            line_count = 0
            for line in f:
                line = line.strip()
                if not line:  # Skip empty lines
                    continue
                
                try:
                    # Parse JSON from the line
                    record = json.loads(line)
                    line_count += 1
                    
                    # Extract project field
                    if 'project' in record:
                        project = record['project']
                        projects_data[project].append(record)
                    else:
                        print(f"⚠ Warning: Line {line_count} missing 'project' field")
                        print(f"   Line content: {line[:100]}{'...' if len(line) > 100 else ''}")
                        
                except json.JSONDecodeError as e:
                    print(f"⚠ JSON parsing error on line {line_count}: {e}")
                    print(f"   Problematic line: {line[:100]}{'...' if len(line) > 100 else ''}")
                    continue
        
        print(f"Processed {line_count} records")
        print(f"Found {len(projects_data)} unique projects: {list(projects_data.keys())}")
        
    except Exception as e:
        print(f"Error reading file: {e}")
        return
    
    # Save each project's data to separate files
    # Create projects directory if it doesn't exist
    os.makedirs("projects", exist_ok=True)
    
    created_files = []  # List to store created file names
    
    for project, records in projects_data.items():
        output_file = f"projects/temp_{project}.jsonl"
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                for record in records:
                    f.write(json.dumps(record, ensure_ascii=False) + '\n')
            
            created_files.append(output_file)
            print(f"Saved {len(records)} records for project '{project}' to {output_file}")
            
        except Exception as e:
            print(f"Error writing to {output_file}: {e}")
    
    # Save list of created files to a text file
    if created_files:
        file_list_path = "projects/created_files.txt"
        try:
            with open(file_list_path, 'w', encoding='utf-8') as f:
                for file_path in created_files:
                    f.write(file_path + '\n')
            print(f"\nSaved list of {len(created_files)} created files to {file_list_path}")
        except Exception as e:
            print(f"Error writing file list to {file_list_path}: {e}")


def main():
    """Main function to handle command line arguments."""
    if len(sys.argv) != 2:
        print("Usage: python filter_jsonl_by_project.py <input_file.jsonl>")
        print("\nExample:")
        print("  python filter_jsonl_by_project.py temp_eo.jsonl")
        sys.exit(1)
    
    input_file = sys.argv[1]
    
    # Validate file extension
    if not input_file.endswith('.jsonl'):
        print("Warning: Input file should have .jsonl extension")
    
    filter_jsonl_by_project(input_file)


if __name__ == "__main__":
    main() 