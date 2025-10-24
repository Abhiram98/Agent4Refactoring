import json
import csv
import os
import sys
import re
from pathlib import Path


def get_project_root():
    current_file = os.path.abspath(__file__)
    project_root = os.path.dirname(current_file)
    return project_root


def convert_json_to_csv(json_file_path, csv_file_path, project_name):

    # Read JSON data
    with open(json_file_path, "r") as f:
        data = json.load(f)

    if not data:
        print("No data found in JSON file")
        return

    output_path = Path(csv_file_path)
    try:
        output_path.mkdir(parents=True, exist_ok=True)
        csv_file_path = output_path / f"{project_name}.csv"
        print(f"Output directory: {output_path.absolute()}")
    except Exception as e:
        print(f"Error creating output directory '{csv_file_path}': {e}")
        return

    # Get all available columns from first record
    first_record = data[0] if isinstance(data, list) else data
    all_columns = list(first_record.keys())

    # Use only the specified columns
    # columns_to_use = ['commit', 'type', 'line_number', 'file_path', 'old_name', 'new_name']
    columns_to_use = [
        "commit",
        "old_name",
        "new_name",
        "type",
        "coRename",
        "line_number",
        "file_path",
    ]

    print(f"Available columns: {all_columns}")
    print(f"Using columns: {columns_to_use}")

    # Convert to list if single object
    if isinstance(data, dict):
        data = [data]

    # Write CSV
    with open(csv_file_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=columns_to_use)
        writer.writeheader()

        for entry in data:
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

                row = {}
                row["old_name"] = old_name
                row["new_name"] = new_name
                row["commit"] = entry["v2_hash"]
                row["type"] = refactoring_change["type"]
                row["line_number"] = refactoring_change["leftSideLocations"][0][
                    "startLine"
                ]
                row["file_path"] = refactoring_change["leftSideLocations"][0][
                    "filePath"
                ]
                writer.writerow(row)

    print(f"Successfully converted {len(data)} records to {csv_file_path}")


def main():

    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print("Usage: python json_to_csv.py <input_file.jsonl> [output_directory]")
        print("\nExample:")
        print("  python json_to_csv.py temp_eo.jsonl")
        print("  python json_to_csv.py temp_eo.jsonl ./output")
        sys.exit(1)

    input_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) == 3 else "."

    # Get project root directory
    project_root = get_project_root()
    project_root = os.path.dirname(
        os.path.dirname(project_root)
    )  # Go up two levels to reach project root

    # # Default paths
    # json_file_path = os.path.join(project_root, "data", "ref_miner", "rename", "flink-clean.json")
    # csv_file_path = os.path.join(project_root, "data", "ref_miner", "rename", "flink-clean.csv")

    # Check if JSON file exists
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found")
        return

    project_name = input_file.split("/")[-1].split(".")[0]

    print(f"Converting {input_file} to {output_dir}...")
    convert_json_to_csv(input_file, output_dir, project_name)


if __name__ == "__main__":
    main()
