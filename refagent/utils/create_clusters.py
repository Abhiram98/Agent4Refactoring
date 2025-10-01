from tenacity import sleep

import refagent
import refagent.benchmark.load as benchmark_load
import refagent.utils.project_manager as pm
import refagent.utils.intellij_server as ij
import refagent.utils.refminer_utils as refminer

import json
import re
from pathlib import Path

def main(input_file_path, output_file_path):
    rename_data, ij_server = load_benchmark(input_file_path)

    processed_benchdata = []
    for entry in rename_data:
        project = pm.EvalProject(entry.project_name)
        json_entry = entry.to_json()
        json_entry['clusters'] = []

        ij_server.open_project(project_path=project.get_project_path())
        project.checkout(entry.v1_hash, force=True)
        print(f"checkout success for {entry.ref_id} hash {entry.v1_hash}")

        ij_server.reload_project()
        print(f"reload success")

        visited = []
        for refactoring_change in entry.refactoring_changes:
            if (refactoring_change.type == "Rename Method" or refactoring_change.type == "Rename Parameter") and  is_visited(visited, refactoring_change)  == False:
                sleep(2)
                ij_server.open_file(rel_file_path=Path(refactoring_change.leftSideLocations[0].filePath))
                print(f"[File opened] : {refactoring_change.leftSideLocations[0].filePath}")
                old_name, new_name = parse_name(refactoring_change)
                rename_json = rename_json_builder(old_name, new_name, refactoring_change.leftSideLocations[0].startLine, refactoring_change.type)
                response = invoke_tool(ij_server, rename_json)
                if response != 'success':
                    print(f"[Tool Message] : Tool call failed. {refactoring_change.type} {old_name} -> {new_name}, line_num: {refactoring_change.leftSideLocations[0].startLine}")
                    continue
                else:
                    print(f"[Tool Message] : Tool call {response}")
                    commit_hash = commit_changes(project, refactoring_change.leftSideLocations[0].filePath, refactoring_change.type, old_name, new_name)
                    refactorings = run_and_parse_refminer_output(project, commit_hash)
                    if len(refactorings) == 0:
                        print(f"[Refactoring Info]: RefMiner put no output, saving file failed.")
                    elif len(refactorings) == 1:
                        print(f"[Refactoring Info]: {old_name} -> {new_name} at {refactoring_change.leftSideLocations[0].startLine} was not a base method")
                    else:
                        print(
                            f"[Refactoring Info]: {old_name} -> {new_name} at {refactoring_change.leftSideLocations[0].startLine} was a base method, here are the changes {refactorings}")
                        visited.extend(refactorings)
                        json_entry['clusters'].append([r.model_dump() for r in refactorings])

        json_entry =  load_spared_refactorings(entry.refactoring_changes, visited, json_entry)
        processed_benchdata.append(json_entry)
        save_result(processed_benchdata, output_file_path)


def load_spared_refactorings(refactoring_changes, visited, json_entry):

    for refactoring_change in refactoring_changes:
        matched = False
        for entry in visited:
            if refactoring_change == entry:
                matched = True
        if not matched:
            json_entry['clusters'].append([refactoring_change.model_dump()])
    return json_entry



def save_result(benchdata, output_file_path):
    with open(output_file_path, 'w') as outfile:
        json.dump(benchdata, outfile)

def is_visited(visited, refactoring_change):
    for entry in visited:
        print(f"[Visited] Entry: {entry}")
        if entry == refactoring_change:
            return True
    return False

def load_benchmark(filepath):
    with open(refagent.data_folder.joinpath(filepath)) as f:
        data = json.load(f)
    rename_data = benchmark_load.load_benchmark(data, bench_type=benchmark_load.RenameItem)
    ij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)

    return rename_data, ij_server

def invoke_tool(ij_server, rename_json):
    tool_call_status = ij_server.call_tool('rename', **rename_json)
    # sleep(10)
    return tool_call_status

def rename_json_builder(old_name, new_name, line_num, code_element_type):
    return {"old_name": old_name,
                       "new_name": new_name,
                       "line_num": line_num,
                       "code_element_type": code_element_type.lower()}

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

def commit_changes(project, file_path, rename_type, old_name, new_name):
    commit_message = f"{rename_type}: {old_name} to {new_name} in {file_path}"
    sleep(2)
    project.add_files(list(project.get_changed_files()))
    # project.safe_add([file_path])
    commit_hash = project.git_repo.index.commit(commit_message)
    print(f"[Commit Info]: Tried adding files: {file_path}, {str(commit_hash)}")
    return str(commit_hash)

def run_and_parse_refminer_output(project, commit_hash):
    refactorings = refminer.default_runner.run(project.get_project_path(), commit_hash)
    refactorings = [i for i in refactorings if i.type.split()[0] == 'Rename']
    return refactorings

if __name__ == "__main__":
    input_file_path = 'ref_miner/test/mekhq.json'
    output_file_path = 'ref_miner/test/mekhq-clustered.json'
    main(input_file_path, output_file_path)