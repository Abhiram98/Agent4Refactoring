import os
import json

# Root directory containing project folders
BASE_DIR = "analysis_result"

# File to look for in each project directory
TARGET_FILE = "comprehensive_analysis_repository.json"

# Keys to extract from each file
STATS_KEYS = [
    "total_analyzed_commit",
    "total_rename_commit",
    "total_renames",
    "total_co_rename_commit",
    "co_rename_precentage"
]

# Container for per-project and total results
all_results = {}
totals = {
    "total_analyzed_commit": 0,
    "total_rename_commit": 0,
    "total_renames": 0,
    "total_co_rename_commit": 0,
    "co_rename_precentage_sum": 0.0,
    "co_rename_precentage_count": 0,
    "projects_analyzed": 0
}

# Walk through each directory under BASE_DIR
for project_name in os.listdir(BASE_DIR):
    project_path = os.path.join(BASE_DIR, project_name)
    if os.path.isdir(project_path):
        json_path = os.path.join(project_path, TARGET_FILE)
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r') as f:
                    data = json.load(f)
                    stats = data.get("dataset_statistics", {})

                    project_stats = {}
                    for key in STATS_KEYS:
                        value = stats.get(key, 0)
                        project_stats[key] = value
                        if key != "co_rename_precentage":
                            totals[key] += value
                        else:
                            if isinstance(value, (int, float)):
                                totals["co_rename_precentage_sum"] += value
                                totals["co_rename_precentage_count"] += 1

                    all_results[project_name] = project_stats
                    totals["projects_analyzed"] += 1

            except Exception as e:
                print(f"Error reading {json_path}: {e}")

# Compute average co_rename_precentage
if totals["co_rename_precentage_count"] > 0:
    totals["co_rename_precentage"] = round(
        totals["co_rename_precentage_sum"] / totals["co_rename_precentage_count"], 2)
else:
    totals["co_rename_precentage"] = 0.0

# Clean up intermediate keys
del totals["co_rename_precentage_sum"]
del totals["co_rename_precentage_count"]

# Final output
output = {
    "project_results": all_results,
    "totals": totals
}

# Save the result to a JSON file
with open("rename_stats_summary.json", "w") as out_file:
    json.dump(output, out_file, indent=2)

print("✅ Aggregation complete. Output saved to rename_stats_summary.json.")
