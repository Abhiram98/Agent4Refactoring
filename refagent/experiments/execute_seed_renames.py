import json
from pathlib import Path
import pandas as pd

import refagent
import refagent.benchmark.load as benchmark_load
import refagent.utils.project_manager as pm
import refagent.utils.intellij_server as ij
import refagent.benchmark.creation.scrape_renas_dataset as scrape_rename
import refagent.refactoring_types.refactorings as refactorings


def main():
    print("creating seed renames for renas dataset")

    with open(refagent.data_folder.joinpath('renas/renas_oracle.json')) as f:
        data = json.load(f)
    rename_data = benchmark_load.load_benchmark(data, bench_type=benchmark_load.RenameItem)
    ij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    seed_hashes = {}

    df = pd.read_csv(refagent.data_folder.joinpath('renas/manualValidation.csv'))
    df_filtered = df[(df['coRename'] != -1) & (df['conceptRename?'] == 'TRUE')]
    groups = list(df_filtered.groupby(['commit', 'coRename']))
    co_renames = [i for i in groups if len(i[1][i[1]['conceptRename?'] == 'TRUE']) >= 1]

    for r in rename_data:
        print(f"Creating seed example for {r.ref_id}")
        if r.seed_hash is not None:
            print(f"Seed computation was completed for {r.ref_id}")
            continue

        project = pm.EvalProject(r.project_name)
        ij_server.open_project(project_path=project.get_project_path())

        ij_server.reset_project_reload_counters()
        project.checkout(r.v1_hash, force=True)
        ij_server.reload_project()
        ij_server.open_file(Path(r.starting_file))


        co_rename_df = \
        [i[1] for i in co_renames if i[0][0] == r.v2_hash and i[0][1] == r.corename_id][0]
        all_concepts = sorted(co_rename_df[['oldName', 'newName', 'type', 'file', 'line']].to_dict(orient='records'),
                         key=scrape_rename.name_sort_key)
        concept = all_concepts[0]
        # for concept in all_concepts:
        # seed_rename = scrape_rename.RenameRecommendation.from_renas_oracle(concept)
        possible_examples = [i for i in r.refactoring_changes if isinstance(i, refactorings.Rename)
                          and i.old_name == concept['oldName']
                          and i.new_name == concept['newName']
                          and i.start_line == concept['line']
                          and concept['type'].lower() in i.type.lower()
                          and i.leftSideLocations[0].filePath == concept['file']
                          ]
            # if len(possible_examples) == 1:
            #     break
        if len(possible_examples) != 1:
            continue
        r.seed_example = possible_examples[0]


        seed_rename_json = {"old_name": concept['oldName'],
                       "new_name": concept['newName'],
                       "line_num": concept['line'],
                       "code_element_type": concept['type'].lower()}
        tool_call_status = ij_server.call_tool('rename', **seed_rename_json)
        if tool_call_status != 'success':
            # tool_call_status = ij_server.call_tool('rename', old_name=concept['oldName'],
            #                                        new_name=concept['newName'])
            print("too call failed.")
            continue
        assert tool_call_status == 'success'
        changed_files = project.get_changed_files()
        project.safe_add(changed_files)
        new_hash = project.git_repo.index.commit(f"seed rename for {r.ref_id}")
        seed_hashes[r.ref_id] = str(new_hash)
        r.seed_hash = str(new_hash)

        with open(refagent.data_folder.joinpath('renas/renas_oracle.json'), 'w') as f:
            final_data = [i.to_json() for i in rename_data]
            json.dump(final_data, f, indent=4)
if __name__ == '__main__':
    main()