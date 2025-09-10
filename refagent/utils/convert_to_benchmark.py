#!/usr/bin/env python3
"""
Script to filter JSONL file by project field and save to separate files.

Usage:
    python filter_jsonl_by_project.py <input_file.jsonl> [output_directory]

This script will:
1. Read each line from the input JSONL file
2. Parse the JSON and extract the "project" field
3. Group records by project
4. Save each project's records to {output_directory}/{project}.jsonl
"""

import json
import sys
import os
from collections import defaultdict
from pathlib import Path


RENAME_TYPES = {
    'Rename Class',
    'Rename Method',
    'Rename Variable',
    'Rename Parameter',
    'Rename Attribute',
    'Rename Package'
}


def process_jsonl(input_file, output_dir=".", project="temp"):

    if not os.path.exists(input_file):
        print(f"Error: Input file '{input_file}' does not exist")
        return

    # Create output directory if it doesn't exist
    output_path = Path(output_dir)
    try:
        output_path.mkdir(parents=True, exist_ok=True)
        print(f"Output directory: {output_path.absolute()}")
    except Exception as e:
        print(f"Error creating output directory '{output_dir}': {e}")
        return

    res = []
    line_count = 0

    print(f"Reading from {input_file}...")

    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:  # Skip empty lines
                    continue

                try:
                    # Parse JSON from the line
                    record = json.loads(line)

                    renames = []
                    for refactoring_changes in record['refactoring_changes']:
                        if refactoring_changes['type'] in RENAME_TYPES:
                            renames.append(refactoring_changes)

                    if len(renames) > 5:
                        record['refactoring_changes'] = renames
                        res.append(record)
                    line_count += 1

                except json.JSONDecodeError as e:
                    print(f"Error parsing JSON on line {line_count}: {e}")
                    continue

        print(f"Found {len(res)} renames over 5 records form {line_count} records")

    except Exception as e:
        print(f"Error reading file: {e}")
        return

    output_file = output_path / f"{project}.json"
    try:
        if len(res) > 0:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(res, f, indent=4)
        else:
            print("Not saved because there are no renames over 5 records")
    except Exception as e:
        print(f"Error writing file: {e}")



def main():
    """Main function to handle command line arguments."""
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print("Usage: python convert_to_benchmark.py <input_file.jsonl> [output_directory]")
        print("\nExample:")
        print("  python convert_to_benchmark.py temp_eo.jsonl")
        print("  python convert_to_benchmark.py temp_eo.jsonl ./output")
        sys.exit(1)

    input_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) == 3 else "."

    project_name = input_file.split('/')[-1].split('.')[0]

    # Validate file extension
    if not input_file.endswith('.jsonl'):
        print("Warning: Input file should have .jsonl extension")

    process_jsonl(input_file, output_dir, project_name)


if __name__ == "__main__":
    main()