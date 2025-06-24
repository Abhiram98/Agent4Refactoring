import json
import csv
import os
import sys
import re

def get_project_root():
    current_file = os.path.abspath(__file__)
    project_root = os.path.dirname(current_file)
    return project_root

def convert_json_to_csv(json_file_path, csv_file_path):
    
    # Read JSON data
    with open(json_file_path, 'r') as f:
        data = json.load(f)
    
    if not data:
        print("No data found in JSON file")
        return
    
    # Get all available columns from first record
    first_record = data[0] if isinstance(data, list) else data
    all_columns = list(first_record.keys())
    
    # Use only the specified columns
    columns_to_use = ['v2_hash', 'type', 'line_number', 'file_path', 'old_name', 'new_name']
    
    print(f"Available columns: {all_columns}")
    print(f"Using columns: {columns_to_use}")
    
    # Convert to list if single object
    if isinstance(data, dict):
        data = [data]
    
    # Write CSV
    with open(csv_file_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=columns_to_use)
        writer.writeheader()
        
        for entry in data:
            print(f'id: {entry["id"]}')
            for refactoring_change in entry['refactoring_changes']:
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

                row = {}
                row['old_name'] = old_name
                row['new_name'] = new_name
                row['v2_hash'] = entry['v2_hash']
                row['type'] = refactoring_change['type']
                row['line_number'] = refactoring_change['leftSideLocations'][0]['startLine']
                row['file_path'] = refactoring_change['leftSideLocations'][0]['filePath']
                writer.writerow(row)
    
    print(f"Successfully converted {len(data)} records to {csv_file_path}")

def main():
    # Get project root directory
    project_root = get_project_root()
    project_root = os.path.dirname(os.path.dirname(project_root))  # Go up two levels to reach project root
    
    # Default paths
    json_file_path = os.path.join(project_root, "data", "ref_miner", "rename", "flink-clean.json")
    csv_file_path = os.path.join(project_root, "data", "ref_miner", "rename", "flink-clean.csv")
    
    # Check if JSON file exists
    if not os.path.exists(json_file_path):
        print(f"Error: {json_file_path} not found")
        return
    
    print(f"Converting {json_file_path} to {csv_file_path}...")
    convert_json_to_csv(json_file_path, csv_file_path)

if __name__ == "__main__":
    main() 