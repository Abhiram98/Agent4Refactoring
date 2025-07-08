import json
import csv
import os
import sys
import re
import pandas as pd


def get_project_root():
    current_file = os.path.abspath(__file__)
    project_root = os.path.dirname(current_file)
    return project_root


def split_data(json_file_path, save_file_path, csv_file_path):

    data_list = []
    # Read JSON data
    with open(json_file_path, 'r') as f:
        data = json.load(f)

    # Read CSV data using pandas for easy column access
    try:
        df = pd.read_csv(csv_file_path)
    except FileNotFoundError:
        print(f"Warning: CSV file {csv_file_path} not found. Continuing without CSV data.")
        df = None
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        df = None

    if not data:
        print("No data found in JSON file")
        return

    for entry in data:
        co_rename = {}
        print(f'id: {entry["id"]}')
        num_of_sub_datapoint = 1
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
            
            if old_name and new_name:
                print(f'old_name: {old_name}, new_name: {new_name}')
                key = f'{old_name} -> {new_name}'
                if key not in co_rename:
                    co_rename[key] = []
                co_rename[key].append(refactoring_change)
        
        v2_hash = entry['v2_hash']
        if df is not None:
            matching_rows = df[df['commit'] == v2_hash]
            if not matching_rows.empty:
                grouped = matching_rows.groupby('coRename')
                for co_rename_value, group_df in grouped:
                    if co_rename_value == -1:
                        continue
                    unique_pair = set()
                    for index, row in group_df.iterrows():
                        print(f'row["old_name"]: {row["old_name"]}, row["new_name"]: {row["new_name"]}')
                        unique_pair.add(f'{str(row["old_name"]).split(" ")[0]} -> {str(row["new_name"]).split(" ")[0]}')
                    temp = entry.copy()
                    temp['hints'] = []
                    temp['refactoring_changes'] = []
                    temp['id'] = entry['id'] * 10 + num_of_sub_datapoint
                    num_of_sub_datapoint = num_of_sub_datapoint + 1
                    for data in unique_pair:
                        first = 0
                        if first == 0:
                            temp['starting_file'] = co_rename[data][0]['leftSideLocations'][0]['filePath']
                            first = 1
                        for refactoring_change in co_rename[data]:
                            temp['refactoring_changes'].append(refactoring_change)
                        temp['hints'].append(data)
                    data_list.append(temp)
    with open(save_file_path, 'w') as f:
        json.dump(data_list, f, indent=4)


def main():
    # Get project root directory
    project_root = get_project_root()
    project_root = os.path.dirname(os.path.dirname(project_root))  # Go up two levels to reach project root

    # Default paths
    csv_file_path = os.path.join(project_root, 'data', "ref_miner", "rename", "split-data3.csv")
    json_file_path = os.path.join(project_root, "data", "ref_miner", "rename", "flink-clean.json")
    save_file_path = os.path.join(project_root, "data", "ref_miner", "rename", "flink-clean-split-manual3.json")

    # Check if JSON file exists
    if not os.path.exists(json_file_path):
        print(f"Error: {json_file_path} not found")
        return

    print(f"Converting {json_file_path} to {save_file_path}...")
    split_data(json_file_path, save_file_path, csv_file_path)

    # with open(save_file_path, 'r') as f:
    #     data_list = json.load(f)
    # print(len(data_list))


if __name__ == "__main__":
    main()