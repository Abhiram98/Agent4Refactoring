#!/usr/bin/env python3
"""
Script to analyze JSON files in a directory and show the length of each file.

Usage:
    python temp.py <directory_path>

This script will:
1. Scan the specified directory for JSON files
2. Read each JSON file and count the number of records
3. Display the filename and record count for each file
"""

import json
import sys
import os
from pathlib import Path
from glob import glob


def analyze_json_files(directory_path):
    """
    Analyze JSON files in the specified directory and show their lengths.
    
    Args:
        directory_path (str): Path to directory containing JSON files
    """
    if not os.path.exists(directory_path):
        print(f"Error: Directory '{directory_path}' does not exist")
        return
    
    if not os.path.isdir(directory_path):
        print(f"Error: '{directory_path}' is not a directory")
        return
    
    # Find all JSON files in the directory
    json_pattern = os.path.join(directory_path, "*.json")
    json_files = glob(json_pattern)
    
    if not json_files:
        print(f"No JSON files found in '{directory_path}'")
        return
    
    print(f"Found {len(json_files)} JSON file(s) in '{directory_path}':")
    print("-" * 60)
    
    total_records = 0
    
    for json_file in sorted(json_files):
        filename = os.path.basename(json_file)
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # Handle different data structures
                if isinstance(data, list):
                    record_count = len(data)
                elif isinstance(data, dict):
                    record_count = 1
                else:
                    record_count = 0
                
                print(f"{filename:<30} | {record_count:>8} records")
                total_records += record_count
                
        except json.JSONDecodeError as e:
            print(f"{filename:<30} | ERROR: Invalid JSON - {e}")
        except Exception as e:
            print(f"{filename:<30} | ERROR: {e}")
    
    print("-" * 60)
    print(f"Total records across all files: {total_records}")


def main():
    """Main function to handle command line arguments."""
    if len(sys.argv) != 2:
        print("Usage: python temp.py <directory_path>")
        print("\nExample:")
        print("  python temp.py ./data/ref_miner/rename")
        print("  python temp.py /path/to/json/files")
        sys.exit(1)
    
    directory_path = sys.argv[1]
    analyze_json_files(directory_path)


if __name__ == "__main__":
    main()
