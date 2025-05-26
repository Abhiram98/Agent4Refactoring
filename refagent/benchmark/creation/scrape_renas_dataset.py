import refagent
import refagent.benchmark.load as bm_load
import refagent.utils.project_manager as pm
import refagent.utils.refminer_utils as rminer
import refagent.refactoring_types.refactorings as refactoring_types

import pandas as pd
import json
from typing import List


def name_sort_key(element):
    if element['type']=='Class':
        return 1000 + len(element['oldName'])
    elif element['type']=='Attribute':
        return 2000 + len(element['oldName'])
    else:
        return 3000

def curate_dataset():

    project_name = "argouml"
    with open(f"/Users/abhiram/Downloads/icsme2024-renas-dataset/projects/{project_name}/recommend.json") as f:
        renas_json = json.load(f)
        oracle_commits = list(renas_json.keys())

    df = pd.read_csv(refagent.data_folder.joinpath(f'renas/{project_name}_manualValidation.csv'))
    df_filtered = df[(df['coRename'] != -1) & (df['conceptRename?'] == 'TRUE')]
    groups = list(df_filtered.groupby(['commit', 'coRename']))
    co_renames = [i for i in groups if len(i[1][i[1]['conceptRename?'] == 'TRUE'])
                  and i[0][0] in oracle_commits
                  ]



    project = pm.EvalProject(project_name)
    print(f"{len(co_renames)=}")

    starting_id = 900

    processed_dataset = []

    for i, co_rename in enumerate(co_renames):
        print()
        print("---")
        print(f"processing {i}/{len(co_renames)}")
        v2_hash = co_rename[0][0]
        commit = project.git_repo.commit(v2_hash)

        co_rename_df = co_rename[1]
        co_rename_id = co_rename[0][1]


        old_names = co_rename_df['oldName'].tolist()
        # old_names_lower = [i.lower() for i in old_names]
        new_names = co_rename_df['newName'].tolist()
        name_map = dict(zip(old_names, new_names))
        validated_renames = [f"{old} -> {new}" for old, new in zip(old_names, new_names)]

        concept = sorted(co_rename_df[['oldName', 'newName', 'type', 'file']].to_dict(orient='records'), key=name_sort_key)
        old_concept = concept[0]['oldName']
        new_concept = concept[0]['newName']
        starting_file = concept[0]['file']


        refactoring_changes = rminer.default_runner.run(project.get_project_path(), v2_hash)
        filtered_refactorings: List[refactoring_types.Rename] = [i for i in refactoring_changes if isinstance(i, refactoring_types.Rename)]
        move_and_renames = [i for i in refactoring_changes if i.type=='Move and Rename Class'
                            and any(old_name in i.description and new_name in i.description for old_name, new_name in name_map.items())]
        filtered_refactorings = ([i for i in filtered_refactorings if
                                  any([old_name in i.old_name and new_name in i.new_name for old_name, new_name in name_map.items()])]
                                 + move_and_renames)
        print(f"{len(filtered_refactorings)=}")
        print(f"{len(old_names)=}")
        print(f"matched refactorings? {len(filtered_refactorings) >= len(old_names)}")
        if len(filtered_refactorings) != len(old_names):
            print("something wrong. each one from the old names should be a refactoring change")


        item = bm_load.RenameItem(
            project_name=project_name,
            ref_id=starting_id + i,
            v1_hash=project.git_repo.commit(v2_hash).parents[0].hexsha,
            v2_hash=v2_hash,
            orig_commit_message=commit.message,
            improved_commit_message=f"Rename the {concept[0]['type']} {old_concept} -> {new_concept}. "
                           f"Rename all related entities like variables, fields, methods, and classes.",
            change_summary=f"Rename the concept {old_concept} -> {new_concept}. "
                           f"Rename all related entities like variables, fields, methods, and classes.",
            hints=validated_renames,
            starting_file=starting_file,
            refactoring_changes=filtered_refactorings,
            diffs=[],
            pull_request=None,
            corename_id=co_rename_id
        )
        processed_dataset.append(item.to_json())

        with open(refagent.data_folder.joinpath(f'renas/{project_name}.json'), "w") as f:
            json.dump(processed_dataset, f, indent=4)


def update_intent():
    df = pd.read_csv(refagent.data_folder.joinpath('renas/ratpack_manualValidation.csv'))
    df_filtered = df[(df['coRename'] != -1) & (df['conceptRename?'] == 'TRUE')]
    groups = list(df_filtered.groupby(['commit', 'coRename']))
    co_renames = [i for i in groups if len(i[1][i[1]['conceptRename?'] == 'TRUE']) >= 2]

    with open(refagent.data_folder.joinpath('renas/ratpack.json')) as f:
        ratpack_data = json.load(f)

    for i, co_rename in enumerate(co_renames):
        commit = co_rename[0][0]
        co_rename_id = co_rename[0][1]

        matching_entry = [i for i in ratpack_data if i['v2_hash'] == commit and i['corename_id'] == co_rename_id]
        assert len(matching_entry) == 1
        matching_entry = matching_entry[0]

        co_rename_df = co_rename[1]
        concept = sorted(co_rename_df[['oldName', 'newName', 'type', 'file', 'line']].to_dict(orient='records'),
                         key=name_sort_key)

        matching_entry['improved_commit_message'] = f"Rename {concept[0]['type']} {concept[0]['oldName']} -> {concept[0]['newName']} on line {concept[0]['line']}."

    with open(refagent.data_folder.joinpath('renas/ratpack.json'), "w") as f:
        json.dump(ratpack_data, f, indent=4)

def has_match(oracle, element):
    for i in oracle:
        if i['oldName'] == element['name'] and i['line']==element['line'] and i['file']==element['files']:
            return True

    return False


def compute_renas_recall():
    df = pd.read_csv(refagent.data_folder.joinpath('renas/ratpack_manualValidation.csv'))
    df_filtered = df[(df['coRename'] != -1) & (df['conceptRename?'] == 'TRUE')]
    groups = list(df_filtered.groupby(['commit', 'coRename']))
    co_renames = [i for i in groups if len(i[1][i[1]['conceptRename?'] == 'TRUE']) >= 2]

    with open(refagent.data_folder.joinpath('renas/ratpack.json')) as f:
        ratpack_data = json.load(f)

    with open("/Users/abhiram/Downloads/icsme2024-renas-dataset/projects/ratpack/recommend.json") as f:
        renas_json = json.load(f)

    renas_recs = []

    for i, co_rename in enumerate(co_renames):
        commit = co_rename[0][0]
        co_rename_id = co_rename[0][1]

        matching_entry = [i for i in ratpack_data if i['v2_hash'] == commit and i['corename_id'] == co_rename_id]
        assert len(matching_entry) == 1
        matching_entry = matching_entry[0]



        co_rename_df = co_rename[1]
        concept = sorted(co_rename_df[['oldName', 'newName', 'type', 'file', 'line']].to_dict(orient='records'),
                         key=name_sort_key)
        old_names = co_rename_df['oldName'].tolist()
        oracle = co_rename_df.to_dict(orient='records')

        goldset = renas_json[commit]['goldset']
        goldset_index = [i['oldname'] == concept[0]['oldName'] for i in goldset].index(True)
        assert goldset_index!=-1
        renas_recommendations = renas_json[commit]['renas'][str(goldset_index)]

        # 0.53 ≦ “similarity” *0.5 + (1 / “relationship”)
        renas_recommendations = [i for i in renas_recommendations if i['similarity'] * 0.5 + (1 / i['relationship']) >= 0.53]
        matching_oracle = [i for i in renas_recommendations if has_match(oracle, i)
                           # i['name'] in old_names
                           ]

        renas_recs.append({
            "id": matching_entry["id"],
            "renas_recommendations_count": len(renas_recommendations),
            "renas_recommendations": renas_recommendations,
            "true_positives": matching_oracle,
            "precision": len(matching_oracle) / len(renas_recommendations) if len(renas_recommendations) > 0 else 0,
            "recall": len(matching_oracle) / len(old_names) if len(old_names) > 0 else 0,
        })

    with open(refagent.data_folder.joinpath('renas/ratpack_renas_recommendations.json'), "w") as f:
        json.dump(renas_recs, f, indent=4)

if __name__ == '__main__':
    # compute_renas_recall()
    curate_dataset()


