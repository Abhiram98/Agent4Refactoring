import json
from pathlib import Path
from time import sleep
from typing import List
import re


import refagent
import refagent.benchmark.load as benchmark_load
import refagent.utils.project_manager as pm
import refagent.utils.intellij_server as ij
import refagent.utils.refminer_utils as refminer_utils
from refagent.refactoring_types.refactorings import RefminerOut


def parse_name(refactoring_change):
    old_name = ''
    new_name = ''

    if refactoring_change.type == 'Rename Class':
        match = re.search(r"Rename Class .*\.([A-Za-z0-9_]+) renamed to .*\.([A-Za-z0-9_]+)",
                          refactoring_change.description)
        if match:
            old_name = match.group(1)
            new_name = match.group(2)

    elif refactoring_change.type == 'Rename Method':
        match = re.search(r"Rename Method .*? ([A-Za-z0-9_]+)\(.*?\)\s*:\s*.*? renamed to .*? ([A-Za-z0-9_]+)\(",
                          refactoring_change.description)
        if match:
            old_name = match.group(1)
            new_name = match.group(2)

    elif refactoring_change.type == 'Rename Variable':
        match = re.search(r"Rename Variable ([A-Za-z0-9_]+) ?: .*? to ([A-Za-z0-9_]+) ?: .*?",
                          refactoring_change.description)
        if match:
            old_name = match.group(1)
            new_name = match.group(2)
    elif refactoring_change.type == 'Rename Attribute':
        match = re.search(r"Rename Attribute ([A-Za-z0-9_]+) ?: .*? to ([A-Za-z0-9_]+) ?: .*? in class",
                          refactoring_change.description)
        if match:
            old_name = match.group(1)
            new_name = match.group(2)
    elif refactoring_change.type == 'Rename Parameter':
        match = re.search(r"Rename Parameter ([A-Za-z0-9_]+) ?: .*? to ([A-Za-z0-9_]+) ?: .*? in method",
                          refactoring_change.description)
        if match:
            old_name = match.group(1)
            new_name = match.group(2)

    return old_name, new_name

def main(input_file_path, output_file_path):
    print("creating seed renames")

    with open(refagent.data_folder.joinpath(input_file_path)) as f:
        data = json.load(f)
    rename_data = benchmark_load.load_benchmark(data, bench_type=benchmark_load.RenameItem)
    ij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    seed_hashes = {}

    for r in rename_data:
        print(f"Creating seed example for {r.ref_id}")
        if r.seed_hash is not None:
            print(f"Seed computation was completed for {r.ref_id}")
            continue

        project = pm.EvalProject(r.project_name)
        r.corename_id = 0


        ij_server.open_project(project_path=project.get_project_path())

        ij_server.reset_project_reload_counters()
        project.checkout(r.v1_hash, force=True)
        print(f"checkout success for {r.ref_id} hash {r.v1_hash}")
        ij_server.reload_project()
        print(f"reload success")

        candidate = find_seed_candidate(r.refactoring_changes)
        old_name, new_name = parse_name(candidate)

        seed_rename_json = {"old_name": old_name.strip(' '),
                            "new_name": new_name.strip(' '),
                            "line_num": candidate.leftSideLocations[0].startLine,
                            "code_element_type": candidate.type.lower()}


        ij_server.open_file(Path(candidate.leftSideLocations[0].filePath))

        print(f"seed rename json: {seed_rename_json}")

        tool_call_status = ij_server.call_tool('rename', **seed_rename_json)

        if tool_call_status != 'success':
            print("too call failed.")
            continue
        else:
            print("Tool call succeeded")
            r.seed_example = candidate
            if candidate.type == 'Rename Class':
                r.starting_file = candidate.rightSideLocations[0].filePath
        # assert tool_call_status == 'success'
        commit_and_write(project, r, rename_data, seed_hashes, output_file_path)
        sleep(5)



def find_seed_candidate(refactoring_changes: List[RefminerOut]) -> RefminerOut | None:
    priority = {
        "Rename Class": 1,
        "Rename Attribute": 2,
        "Rename Method": 3,
        "Rename Parameter": 4,
        "Rename Variable": 5,
    }

    def compute_priority(r: RefminerOut) -> tuple[int, int]:
        # first gives priority by type
        type_priority = priority.get(r.type, float("inf"))

        # then again deprioritize by test
        is_test = 1 if "test" in r.leftSideLocations[0].filePath.lower() else 0

        print(f"file: {r.leftSideLocations[0].filePath}, type: {r.type}, is_test: {is_test}")
        return (is_test, type_priority)

    return min(refactoring_changes, key=compute_priority, default=None)



def commit_and_write(project, r, rename_data, seed_hashes, output_file_path):
    changed_files = project.get_changed_files()
    project.safe_add(changed_files)
    new_hash = project.git_repo.index.commit(f"seed rename for {r.ref_id}")
    seed_hashes[r.ref_id] = str(new_hash)
    r.seed_hash = str(new_hash)
    with open(refagent.data_folder.joinpath(output_file_path), 'w') as f:
        final_data = [i.to_json() for i in rename_data]
        json.dump(final_data, f, indent=4)


if __name__ == '__main__':
    input_file = 'ref_miner/test/one.json'
    output_file = 'ref_miner/test/one-2.json'
    main(input_file, output_file)
