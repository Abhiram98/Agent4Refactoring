import json
import csv
import os
import sys
import re


def get_project_root():
    current_file = os.path.abspath(__file__)
    project_root = os.path.dirname(current_file)
    return project_root


def convert_json_to_csv(json_file_path, save_file_path):

    # Read JSON data
    with open(json_file_path, "r") as f:
        data = json.load(f)

    if not data:
        print("No data found in JSON file")
        return

    # List to store all split entries
    split_data = []

    for entry in data:
        index = 1
        co_rename = {}
        print(f'id: {entry["id"]}')

        for refactoring_change in entry["refactoring_changes"]:
            old_name = ""
            new_name = ""

            if refactoring_change["type"] == "Rename Class":
                match = re.search(
                    r"Rename Class .*\.([A-Za-z0-9_]+) renamed to .*\.([A-Za-z0-9_]+)",
                    refactoring_change["description"],
                )
                if match:
                    old_name = match.group(1)
                    new_name = match.group(2)

            elif refactoring_change["type"] == "Rename Method":
                match = re.search(
                    r"Rename Method .*? ([A-Za-z0-9_]+)\(.*?\)\s*:\s*.*? renamed to .*? ([A-Za-z0-9_]+)\(",
                    refactoring_change["description"],
                )
                if match:
                    old_name = match.group(1)
                    new_name = match.group(2)

            elif refactoring_change["type"] == "Rename Variable":
                match = re.search(
                    r"Rename Variable ([A-Za-z0-9_]+) ?: .*? to ([A-Za-z0-9_]+) ?: .*?",
                    refactoring_change["description"],
                )
                if match:
                    old_name = match.group(1)
                    new_name = match.group(2)
            elif refactoring_change["type"] == "Rename Attribute":
                match = re.search(
                    r"Rename Attribute ([A-Za-z0-9_]+) ?: .*? to ([A-Za-z0-9_]+) ?: .*? in class",
                    refactoring_change["description"],
                )
                if match:
                    old_name = match.group(1)
                    new_name = match.group(2)
            elif refactoring_change["type"] == "Rename Parameter":
                match = re.search(
                    r"Rename Parameter ([A-Za-z0-9_]+) ?: .*? to ([A-Za-z0-9_]+) ?: .*? in method",
                    refactoring_change["description"],
                )
                if match:
                    old_name = match.group(1)
                    new_name = match.group(2)

            if old_name and new_name:
                key = f"{old_name} -> {new_name}"
                if key not in co_rename:
                    co_rename[key] = []
                co_rename[key].append(refactoring_change)

        for key, value in co_rename.items():
            temp = entry.copy()
            temp["refactoring_changes"] = value
            temp["starting_file"] = value[0]["leftSideLocations"][0]["filePath"]
            temp["hints"] = [key]
            temp["id"] = f'{entry["id"]}-{index}'
            index += 1
            # print(temp)
            # Add temp to the split_data list
            split_data.append(temp)

    # Save all split data to the file
    with open(save_file_path, "w") as f:
        json.dump(split_data, f, indent=2)

    print(
        f"Successfully converted {len(data)} records to {len(split_data)} split records and saved to {save_file_path}"
    )


def main():
    # Get project root directory
    project_root = get_project_root()
    project_root = os.path.dirname(
        os.path.dirname(project_root)
    )  # Go up two levels to reach project root

    # Default paths
    json_file_path = os.path.join(
        project_root, "data", "ref_miner", "rename", "flink-clean.json"
    )
    save_file_path = os.path.join(
        project_root, "data", "ref_miner", "rename", "flink-clean-split.json"
    )

    # Check if JSON file exists
    if not os.path.exists(json_file_path):
        print(f"Error: {json_file_path} not found")
        return

    print(f"Converting {json_file_path} to {save_file_path}...")
    convert_json_to_csv(json_file_path, save_file_path)


if __name__ == "__main__":
    main()
