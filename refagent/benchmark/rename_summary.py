import argparse
import json
import sys

import refagent.benchmark.load as bm_load
from collections import defaultdict

if __name__ == "__main__":
    file_path = str(sys.argv[1])
    id = int(sys.argv[2])
    with open(file_path, "r") as f:
        json_ = json.load(f)
    rename_bench = bm_load.load_benchmark(json_, bench_type=bm_load.RenameItem)

    file_groups = defaultdict(list)
    for i in rename_bench:
        if i.ref_id == id:
            print("startingfile=", i.starting_file)
            for i in i.refactoring_changes:
                file_groups[i.leftSideLocations[0].filePath].append(i)

    for file_name in file_groups:
        print(file_name)
        for rename in file_groups[file_name]:
            print(rename.description, rename.leftSideLocations[0].startLine)
        print("----")

    print("all files renamed:")
    for file_name in file_groups:
        print(f"file: {file_name}")
