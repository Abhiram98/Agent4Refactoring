from typing_extensions import Optional

import refagent
import refagent.benchmark.load as bm_load
import refagent.utils.project_manager as pm
import refagent.utils.refminer_utils as rminer
import refagent.refactoring_types.refactorings as refactoring_types


import pandas as pd
import json
from typing import List
from pydantic import BaseModel


class RenameRecommendation(BaseModel):
    oldName: str
    # new_name: str
    similarity: Optional[float] = None
    relationship: Optional[float] = None
    type: str
    file: str
    line: int

    @staticmethod
    def from_renas_rec(renas_rec: dict):
        type = renas_rec['typeOfIdentifier'].split('Name')[0]
        if type=='Field':
            type = 'Attribute'
        return RenameRecommendation(
            oldName=renas_rec['oldname'] if 'oldname' in renas_rec else renas_rec['name'],
            similarity=renas_rec['similarity'] if 'similarity' in renas_rec else None,
            relationship=renas_rec['relationship'] if 'relationship' in renas_rec else None,
            type=type,
            file=renas_rec['files'],
            line=renas_rec['line']
        )

    @staticmethod
    def from_renas_oracle(renas_oracle: dict):
        # 'oldName', 'newName', 'type', 'file', 'line'
        return RenameRecommendation(
            oldName=renas_oracle['oldName'],
            # similarity=renas_oracle['similarity'],
            # relationship=renas_oracle['relationship'],
            type=renas_oracle['type'],
            file=renas_oracle['file'],
            line=renas_oracle['line']
        )

    def __eq__(self, other):
        if isinstance(other, RenameRecommendation):
            return (self.oldName == other.oldName
                    and self.type == other.type
                    and self.file == other.file
                    and self.line == other.line)
        return False

    def __str__(self):
        return f"{self.oldName} on line {self.line} in {self.file}"

    def __hash__(self):
        return hash((self.oldName, self.type, self.file, self.line))


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
        if (i['oldName'] == element['name'] and i['line']==element['line'] and i['file']==element['files']
                and i['type']+'Name'==element['typeOfIdentifier']):
            return True

    return False


def compute_renas_recall():
    project_name = "argouml"

    with open(f"/Users/abhiram/Downloads/icsme2024-renas-dataset/projects/{project_name}/recommend.json") as f:
        renas_json = json.load(f)
    oracle_commits = list(renas_json.keys())

    co_renames = get_renas_corenames(oracle_commits, project_name)

    with open(refagent.data_folder.joinpath(f'renas/{project_name}.json')) as f:
        ratpack_data = json.load(f)

    ratpack_data = bm_load.load_benchmark(ratpack_data, bench_type=bm_load.RenameItem)


    renas_recs = []

    with open(refagent.data_folder.joinpath(f'results/rename-baseline-May-21/report-post-replication.json')) as f:
        agent_data = json.load(f)


    overlap_count = 0
    unique_agent_count = 0
    unique_renas_count = 0
    for i, co_rename in enumerate(co_renames):
        commit = co_rename[0][0]
        co_rename_id = co_rename[0][1]

        matching_entry = [i for i in ratpack_data if i.v2_hash == commit and i.corename_id == co_rename_id]
        assert len(matching_entry) == 1
        matching_entry = matching_entry[0]

        # agent_refs = [i['agent_refactorings'] for i in agent_data if i['id']==matching_entry.ref_id]
        # if len(agent_refs)==0:
        #     continue
        # assert len(agent_refs) == 1
        # agent_refs = agent_refs[0]
        # agent_refs = refactoring_types.RefminerOut.load_from_json(agent_refs)
        # agent_refs = [{"oldName": i.old_name,
        #                "line": i.leftSideLocations[0].startLine,
        #                "file": i.leftSideLocations[0].filePath,
        #                "type": i.type.split('Rename ')[1]
        #                } for i in agent_refs]



        co_rename_df = co_rename[1]
        concept = sorted(co_rename_df[['oldName', 'newName', 'type', 'file', 'line']].to_dict(orient='records'),
                         key=name_sort_key)
        old_names = co_rename_df['oldName'].tolist()
        oracle = co_rename_df.to_dict(orient='records')
        # starting_example = concept[0]
        for starting_example in concept:
            starting_example['oldName'] = starting_example['oldName'].split(' ')[-1]
            goldset = renas_json[commit]['goldset']
            goldset_index = [i['oldname'] == starting_example['oldName']
                             and i['files'] == starting_example['file'] and i['line'] == starting_example['line']
                             for i in goldset].index(True)
            assert goldset_index!=-1
            renas_recommendations = renas_json[commit]['renas'][str(goldset_index)]

            # 0.53 ≦ “similarity” *0.5 + (1 / “relationship”)
            renas_recommendations = [i for i in renas_recommendations if i['similarity'] * 0.5 + (1 / i['relationship']) >= 0.53]
            for i in renas_recommendations:
                if 'Field' in i['typeOfIdentifier']:
                    i['typeOfIdentifier'] = i['typeOfIdentifier'].replace('Field', 'Attribute')

            matching_oracle = []
            for oracle_entry in oracle:
                for i in renas_recommendations:
                    if has_match([oracle_entry], i):
                        matching_oracle.append(oracle_entry)
                        break
            # matching_oracle = [i for i in renas_recommendations if has_match(oracle, i)
            #                    # and not (i['line']==starting_example['line'] and i['files']==starting_example['file'] and i['name'] == starting_example['oldName'])
            #                    # i['name'] in old_names
            #                    ]
            #
            # agent_refs = [i for i in agent_refs if not (i['oldName']==starting_example['oldName']
            #                                                           and i['line']==starting_example['line']
            #                                                           and i['file']==starting_example['file']
            #                                                           and i['type']==starting_example['type'])]
            # overlap_with_agent = [i for i in renas_recommendations if has_match(agent_refs, i)]
            # # unique_agent_recs = [i for i in renas_recommendations if not has_match(agent_refs, i)]
            # # unique_agent_recs = [i for i in unique_agent_recs if not (i['oldName']==starting_example['oldName']
            # #                                                           and i['line']==starting_example['line']
            # #                                                           and i['file']==starting_example['file']
            # #                                                           and i['type']==starting_example['type'])]
            #
            # assert len(overlap_with_agent) <= len(renas_recommendations)
            # assert len(overlap_with_agent) <= len(agent_refs)
            # overlap_count += len(overlap_with_agent)
            # unique_agent_ = len(agent_refs) - len(overlap_with_agent)
            # unique_agent_count += unique_agent_
            # unique_renas_ = len(renas_recommendations) - len(overlap_with_agent)
            # unique_renas_count += unique_renas_
            precision = len(matching_oracle) / len(renas_recommendations) if len(renas_recommendations) > 0 else 0
            recall = len(matching_oracle) / (len(old_names)-1) if (len(old_names)-1) > 0 else 0
            recall = min(recall, 1)
            assert precision <=1
            assert recall <=1
            renas_recs.append({
                "id": matching_entry.ref_id,
                "oracle_count": len(oracle),
                "renas_raw_recommendations_str": str([str((i['name'], i['line'], i['files'])) for i in renas_recommendations]),
                "renas_recommendations_count": len(renas_recommendations),
                "renas_recommendations": renas_recommendations,
                "true_positives": matching_oracle,
                "precision": precision,
                "recall": recall,
                # "overlap_with_agent": overlap_with_agent,
                # "unique_agent_recs": unique_agent_recs,
                # "unique_agent_count": unique_agent_,
                # "unique_renas_count": unique_renas_,
            })

        print(f"{overlap_count=}")
        print(f"{unique_agent_count=}")
        print(f"{unique_renas_count=}")
        print("-----")

    with open(refagent.data_folder.joinpath(f'renas/{project_name}_renas_recommendations.json'), "w") as f:
        json.dump(renas_recs, f, indent=4)


def compute_overlap():
    project_name = "ratpack"

    with open(f"/Users/abhiram/Downloads/icsme2024-renas-dataset/projects/{project_name}/recommend.json") as f:
        renas_json = json.load(f)
    oracle_commits = list(renas_json.keys())

    co_renames = get_renas_corenames(oracle_commits, project_name)

    with open(refagent.data_folder.joinpath(f'renas/{project_name}.json')) as f:
        ratpack_data = json.load(f)

    ratpack_data = bm_load.load_benchmark(ratpack_data, bench_type=bm_load.RenameItem)

    renas_recs = []

    with open(refagent.data_folder.joinpath(f'results/rename-baseline-May-21/report-post-replication.json')) as f:
        agent_data = json.load(f)

    overlap_count = 0
    unique_agent_count = 0
    unique_renas_count = 0


    agent_only = []
    renas_only = []
    oracle_only = []
    agent_and_renas_only = []
    agent_and_oracle_only = []
    renas_and_oracle_only = []
    agent_and_renas_and_oracle_only = []


    for i, co_rename in enumerate(co_renames):
        commit = co_rename[0][0]
        co_rename_id = co_rename[0][1]

        matching_entry = [i for i in ratpack_data if i.v2_hash == commit and i.corename_id == co_rename_id]
        assert len(matching_entry) == 1
        matching_entry = matching_entry[0]

        agent_refs = [i['agent_refactorings'] for i in agent_data if i['id']==matching_entry.ref_id]
        if len(agent_refs)==0:
            continue
        assert len(agent_refs) == 1
        agent_refs = agent_refs[0]
        agent_refs = refactoring_types.RefminerOut.load_from_json(agent_refs)
        agent_refs = [RenameRecommendation(oldName=i.old_name,
                                            line=i.leftSideLocations[0].startLine,
                                            file=i.leftSideLocations[0].filePath,
                                            type=i.type.split('Rename ')[1]
                                           ) for i in agent_refs]



        co_rename_df = co_rename[1]
        concept = sorted(co_rename_df[['oldName', 'newName', 'type', 'file', 'line']].to_dict(orient='records'),
                         key=name_sort_key)
        concept = [RenameRecommendation.from_renas_oracle(i) for i in concept]
        old_names = co_rename_df['oldName'].tolist()
        oracle = [RenameRecommendation.from_renas_oracle(i) for i in co_rename_df.to_dict(orient='records')]
        starting_example = concept[0]
        oracle = [i for i in oracle if i!=starting_example]
        # for starting_example in concept:
        starting_example.oldName = starting_example.oldName.split(' ')[-1]
        goldset = [RenameRecommendation.from_renas_rec(i) for i in renas_json[commit]['goldset']]
        goldset_index = [i == starting_example
                         for i in goldset].index(True)
        assert goldset_index!=-1
        renas_recommendations = [RenameRecommendation.from_renas_rec(i) for
                                 i in renas_json[commit]['renas'][str(goldset_index)]]

        # 0.53 ≦ “similarity” *0.5 + (1 / “relationship”)
        renas_recommendations = [i for i in renas_recommendations if i.similarity * 0.5 + (1 / i.relationship) >= 0.53]
        for i in renas_recommendations:
            if 'Field' in i.type:
                i.type = i.type.replace('Field', 'Attribute')

        matching_oracle = []
        for oracle_entry in oracle:
            for i in renas_recommendations:
                if oracle_entry == i:
                    matching_oracle.append(oracle_entry)
                    break
        # matching_oracle = [i for i in renas_recommendations if has_match(oracle, i)
        #                    # and not (i['line']==starting_example['line'] and i['files']==starting_example['file'] and i['name'] == starting_example['oldName'])
        #                    # i['name'] in old_names
        #                    ]

        agent_refs = [i for i in agent_refs if i!=starting_example]
        overlap_with_agent = [i for i in renas_recommendations if i in agent_refs]
        unique_renas_recs = [i for i in renas_recommendations if i not in agent_refs]
        # unique_agent_recs = [i for i in unique_agent_recs if i!=starting_example]
        unique_agent_recs = [i for i in agent_refs if i not in renas_recommendations]
        true_positive_uniqe_agent_recs = [i for i in unique_agent_recs if i in oracle]
        agent_matches = [i for i in agent_refs if i in oracle]


        agent_set = set(agent_refs)
        renas_set = set(renas_recommendations)
        oracle_set = set(oracle)
        agent_and_renas_and_oracle_only += list(agent_set.intersection(renas_set).intersection(oracle_set))
        agent_and_renas_only += list(agent_set.intersection(renas_set).difference(oracle_set))
        agent_and_oracle_only += list(agent_set.difference(renas_set).intersection(oracle_set))
        renas_and_oracle_only += list(renas_set.difference(agent_set).intersection(oracle_set))
        agent_only += list(agent_set.difference(renas_set).difference(oracle_set))
        renas_only += list(renas_set.difference(agent_set).difference(oracle_set))
        oracle_only += list(oracle_set.difference(agent_set).difference(renas_set))


        assert len(overlap_with_agent) <= len(renas_recommendations)
        assert len(overlap_with_agent) <= len(agent_refs)
        overlap_count += len(overlap_with_agent)
        unique_agent_ = len(agent_refs) - len(overlap_with_agent)
        unique_agent_count += unique_agent_
        unique_renas_ = len(renas_recommendations) - len(overlap_with_agent)
        unique_renas_count += unique_renas_
        precision = len(matching_oracle) / len(renas_recommendations) if len(renas_recommendations) > 0 else 0
        recall = len(matching_oracle) / (len(old_names)-1) if (len(old_names)-1) > 0 else 0
        recall = min(recall, 1)
        assert precision <=1
        assert recall <=1
        renas_recs.append({
            "id": matching_entry.ref_id,
            "oracle_count": len(oracle),
            "precision": precision,
            "recall": recall,
            "agent_precision": len(agent_matches) / len(agent_refs) if len(agent_refs) > 0 else 0,
            "agent_recall": len(agent_matches) / (len(old_names) - 1) if (len(old_names) - 1) > 0 else 0,
            "unique_agent_count": unique_agent_,
            "unique_renas_count": unique_renas_,
            "agent_unique_precision": len(true_positive_uniqe_agent_recs) / len(unique_agent_recs) if len(unique_agent_recs) > 0 else 0,
            "renas_raw_recommendations_str": str("\n".join([str(i) for i in renas_recommendations])),
            "renas_recommendations_count": len(renas_recommendations),
            "true_positives": [i.model_dump() for i in matching_oracle],
            "true_positives_count": len(matching_oracle),
            "renas_recommendations": [i.model_dump() for i in renas_recommendations],
            "overlap_with_agent": [i.model_dump() for i in overlap_with_agent],
            "unique_agent_recs": [i.model_dump() for i in unique_agent_recs]
        })

        print(f"{overlap_count=}")
        print(f"{unique_agent_count=}")
        print(f"{unique_renas_count=}")
        print("-----")

    with open(refagent.data_folder.joinpath(f'renas/{project_name}_renas_overlap.json'), "w") as f:
        json.dump(renas_recs, f, indent=4)

    pd.DataFrame(renas_recs).to_csv(refagent.data_folder.joinpath(f'renas/{project_name}_renas_overlap.csv'))
    print(f"{len(agent_only)=}")
    print(f"{len(renas_only)=}")
    print(f"{len(oracle_only)=}")
    print(f"{len(agent_and_renas_only)=}")
    print(f"{len(agent_and_oracle_only)=}")
    print(f"{len(renas_and_oracle_only)=}")
    print(f"{len(agent_and_renas_and_oracle_only)=}")
    # print(f"{len(agent_only) + len(renas_only) + len(oracle_only) + len(agent_and_renas_only) + len(agent_and_oracle_only) + len(renas_and_oracle_only) + len(agent_and_renas_and_oracle_only)=}")
    # print(f"{len(agent_only) + len(renas_only) + len(oracle_only) + len(agent_and_renas_only) + len(agent_and_oracle_only) + len(renas_and_oracle_only)=}")

    draw_venn_diagram(agent_and_oracle_only, agent_and_renas_and_oracle_only, agent_and_renas_only, agent_only,
                      oracle_only, renas_and_oracle_only, renas_only)


def draw_venn_diagram(agent_and_oracle_only, agent_and_renas_and_oracle_only, agent_and_renas_only, agent_only,
                      oracle_only, renas_and_oracle_only, renas_only):
    import matplotlib.pyplot as plt
    from matplotlib_venn import venn3
    # Compute sets
    # Prepare the subset sizes in order:
    # (A only, B only, A&B, C only, A&C, B&C, A&B&C)
    venn_counts = (
        len(agent_only),  # 100: Agent only
        len(renas_only),  # 010: Renas only
        len(agent_and_renas_only),  # 110: Agent ∩ Renas only
        len(oracle_only),  # 001: Oracle only
        len(agent_and_oracle_only),  # 101: Agent ∩ Oracle only
        len(renas_and_oracle_only),  # 011: Renas ∩ Oracle only
        len(agent_and_renas_and_oracle_only),  # 111: Agent ∩ Renas ∩ Oracle
    )
    # Create the Venn diagram
    venn3(subsets=venn_counts, set_labels=("Agent", "Renas", "Oracle"))
    plt.title("Agent vs Renas vs Oracle Venn Diagram")
    plt.show()


def get_renas_corenames(oracle_commits, project_name):
    df = pd.read_csv(refagent.data_folder.joinpath(f'renas/{project_name}_manualValidation.csv'))
    df_filtered = df[(df['coRename'] != -1) & (df['conceptRename?'] == 'TRUE')]
    groups = list(df_filtered.groupby(['commit', 'coRename']))
    co_renames = [i for i in groups if len(i[1][i[1]['conceptRename?'] == 'TRUE']) >= 2]
    co_renames = [i for i in groups if len(i[1][i[1]['conceptRename?'] == 'TRUE'])
                  and i[0][0] in oracle_commits
                  ]
    return co_renames


if __name__ == '__main__':
    # compute_renas_recall()
    # curate_dataset()
    compute_overlap()


