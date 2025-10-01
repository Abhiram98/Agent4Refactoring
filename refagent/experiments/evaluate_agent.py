import argparse
import json

import refagent
import refagent.benchmark.load as bm_load
import refagent.utils.project_manager as pm
import refagent.utils.refminer_utils as rminer
import refagent.refactoring_types.refactorings as refactoring_types
import pandas as pd
from typing import List
from pathlib import Path

import refagent.benchmark.creation.scrape_renas_dataset as scrape_rename


def find_similar(change, diffs):
    pass


def compute_recall(bench_point: bm_load.BenchmarkItem, diffs: list[pm.MyDiff]):
    oracle_changes = bench_point.diffs
    total_changes_by_developer = len(bench_point.diffs)
    recall_points = 0
    for change in oracle_changes:
        similar_change, similarity_score = find_similar(change, diffs)
        recall_points += similarity_score

    return recall_points / total_changes_by_developer


def main():
    parser = argparse.ArgumentParser(description='Evaluate the performance of an agent, given it\'s output file.')
    parser.add_argument('agent_outfile_path', type=str, help='Path to Agent\'s output file')
    parser.add_argument('--benchmark_file_path', type=str, help='Path to benchmark file', default=str(refagent.benchmark_full_file))
    parser.add_argument("--without-seed",
                        help='If passed, do not use the seed while computing recall and precision',
                        action='store_true')
    args = parser.parse_args()

    print(f'File Path: {args.agent_outfile_path}')
    with open(args.agent_outfile_path) as f:
        agent_results = json.load(f)

    name = Path(args.agent_outfile_path).name.replace(".json", "")
    report_file_path = Path(args.agent_outfile_path).parent.joinpath(f"report-{name}.json")
    report = []

    overall_recall = 0
    total_oracle = 0
    overall_precision = 0
    print(f'{args.without_seed} and type {type(args.without_seed)}')
    IGNORE_SEED = args.without_seed

    with open(args.benchmark_file_path) as f:
        benchmark_json = json.load(f)
    benchmark: List[bm_load.RenameItem] = bm_load.load_benchmark(benchmark_json, bench_type=bm_load.RenameItem)

    for result in agent_results:
        # if result['id'] != 2281:
        #     continue
        bench_points = [i for i in benchmark if i.ref_id==result['id']]
        # assert len(bench_points) == 1
        bench_point = bench_points[0]

        id = result['id']

        assert id == bench_point.ref_id
        commit = result['response']['commit_hash']
        project = pm.EvalProject(bench_point.project_name)
        refactorings = rminer.default_runner.run(project.get_project_path(), commit)
        refactorings = [i for i in refactorings if i.type.split()[0] == 'Rename']

        # len = len(refactorings)
        # index = 0
        #
        # res = []
        # for i in range(len(refactorings)):
        #     if refactorings[i] == refactorings[i+1]:
        #         continue
        #     res.append(refactorings[i])
        #     res.append(refactorings[i+1])

        # refactorings = res
        oracle_refactorings = bench_point.refactoring_changes
        if len(oracle_refactorings) == 0:
            continue

        if len(refactorings) == 0:
            compute_from_trajectory(id, oracle_refactorings, report, result)
            continue

        if IGNORE_SEED:
            print("ignoring seed")
            seed_example = bench_point.seed_example
            assert seed_example is not None
            oracle_refactorings = [i for i in bench_point.refactoring_changes if i!=seed_example]
            refactorings = [i for i in refactorings if i!=seed_example]
        if len(oracle_refactorings) == 0:
            continue

        recall = 0
        total_oracle += 1
        true_positives = []
        false_negatives = []
        for oracle in oracle_refactorings:
            status = "false negative"
            for i in refactorings:
                # if i in true_positives:
                #     continue

                if oracle == i:
                    # if i not in true_positives:
                    true_positives.append(i)
                    if status == "false negative":
                        recall += 1
                    status = "true positive"
            if status == "false negative":
                false_negatives.append(oracle)



        print(f"captured {recall}/{len(oracle_refactorings)} in bench point {bench_point.ref_id}")
        print(f"recall={recall/len(oracle_refactorings)}")
        if len(oracle_refactorings) > 0:
            overall_recall += recall/len(oracle_refactorings)

        false_positives = [i for i in refactorings if i not in true_positives]

        precision = len(true_positives) / len(refactorings) if len(refactorings) > 0 else 0
        overall_precision += precision

        review_count = result['response'].get('human_review_count')
        accepted_count = result['response'].get('human_accepted_count')
        rejected_count = result['response'].get('human_rejected_count')

        if IGNORE_SEED and review_count is not None:
            review_count -= 1
        if IGNORE_SEED and accepted_count is not None:
            accepted_count -= 1

        if accepted_count is not None and rejected_count is not None:
            try:
                accepted_rate = accepted_count/ (accepted_count + rejected_count)
            except ZeroDivisionError:
                accepted_rate = 0
        else:
            accepted_rate = None

        operated_files_count = result['response']['replication_inspection_data'].get('operated_files_count')
        inspected_files_count = result['response']['replication_inspection_data'].get('inspected_files_count')

        print(f"avg recall = {overall_recall / total_oracle}")
        print(f"avg precision = {overall_precision / total_oracle}")
        print(f"{precision=}")
        print(f"{len(oracle_refactorings)=}")
        print(f"{len(refactorings)=}")
        print(f"{overall_recall=}")
        print(f"{total_oracle=}")
        print(f"{accepted_count=}")
        print(f"{review_count=}")
        print(f"{accepted_rate=}")
        print(f"{inspected_files_count=}")
        print(f"{operated_files_count=}")

        print("-----------")
        print()

        # assert len(oracle_refactorings) == len(true_positives) + len(false_negatives)
        # assert len(refactorings) == len(true_positives) + len(false_positives)
        report.append(
            {
                "id": id,
                "oracle_count": len(oracle_refactorings),
                "oracle": [i.model_dump() for i in oracle_refactorings],
                "agent_refactorings": [i.model_dump() for i in refactorings],
                "agent_refactoring_count": len(refactorings),
                "recall": recall/len(oracle_refactorings),
                "precision": precision,
                "false_negatives": [i.model_dump() for i in false_negatives],
                "false_positives": [i.model_dump() for i in false_positives],
                "true_positives": [i.model_dump() for i in true_positives],
                "agent_recommendations_str": str([i.old_name for i in refactorings]),
                "human_review_count": review_count,
                "human_accepted_count": accepted_count,
                "human_rejected_count": rejected_count,
                "human_accepted_rate": accepted_rate,
                "operated_files_count": operated_files_count,
                "inspected_files_count": inspected_files_count,
            }
        )

    with open(report_file_path, 'w') as f:
        json.dump(sorted(report, key=lambda x: x['id']), f, indent=4)


def compute_from_trajectory(id, oracle_refactorings, report, result):
    tool_calls = []
    for fname in result['response']['performed_refactorings']:
        for tool_call in result['response']['performed_refactorings'][fname]:
            if tool_call['response'] == 'success' and tool_call['tool_call']['name'] == 'rename':
                r = scrape_rename.RenameRecommendation(
                    oldName=tool_call['tool_call']['args']['old_name'],
                    type=tool_call['tool_call']['args']['code_element_type'].capitalize(),
                    file=fname,
                    line=tool_call['tool_call']['args']['line_num']
                )
                tool_calls.append(r)
    true_positives = []
    for rename in tool_calls:
        if any([rename.line == oracle.old_name
                and rename.line == oracle.leftSideLocations[0].startLine
                and rename.file == oracle.leftSideLocations[0].filePath
                and rename.type in oracle.type
                for oracle in oracle_refactorings]):
            true_positives.append(rename)
    report.append(
        {
            "id": id,
            "oracle_count": len(oracle_refactorings),
            "oracle": [i.model_dump() for i in oracle_refactorings],
            "agent_refactorings": [tool_call.model_dump() for tool_call in tool_calls],
            "agent_refactoring_count": len(tool_calls),
            "recall": len(true_positives) / len(oracle_refactorings) if len(oracle_refactorings) > 0 else 0,
            "precision": len(true_positives) / len(tool_calls) if len(tool_calls) > 0 else 0,
            # "false_negatives": [i.model_dump() for i in false_negatives],
            # "false_positives": [i.model_dump() for i in false_positives],
            "true_positives": [i.model_dump() for i in true_positives],
            # "agent_recommendations_str": str([i.old_name for i in refactorings])
        }
    )
    print("nothing ;/")


def compute_our_recall():
    df = pd.read_csv(refagent.data_folder.joinpath('renas/ratpack_manualValidation.csv'))
    df_filtered = df[(df['coRename'] != -1) & (df['conceptRename?'] == 'TRUE')]
    groups = list(df_filtered.groupby(['commit', 'coRename']))
    co_renames = [i for i in groups if len(i[1][i[1]['conceptRename?'] == 'TRUE']) >= 2]

    with open(refagent.data_folder.joinpath('renas/ratpack.json')) as f:
        ratpack_data = json.load(f)

    with open("/Users/abhiram/Downloads/icsme2024-renas-dataset/projects/ratpack/recommend.json") as f:
        renas_json = json.load(f)

    with open("") as f:
        agent_results = json.load(f)

    renas_recs = []

    for i, co_rename in enumerate(co_renames):
        commit = co_rename[0][0]
        co_rename_id = co_rename[0][1]

        matching_entry = [i for i in ratpack_data if i['v2_hash'] == commit and i['corename_id'] == co_rename_id]
        assert len(matching_entry) == 1
        matching_entry = matching_entry[0]



        co_rename_df = co_rename[1]
        concept = sorted(co_rename_df[['oldName', 'newName', 'type', 'file', 'line']].to_dict(orient='records'),
                         key=scrape_rename.name_sort_key)
        old_names = co_rename_df['oldName'].tolist()
        oracle = co_rename_df.to_dict(orient='records')

        goldset = renas_json[commit]['goldset']
        goldset_index = [i['oldname'] == concept[0]['oldName'] for i in goldset].index(True)
        assert goldset_index!=-1
        renas_recommendations = renas_json[commit]['renas'][str(goldset_index)]
        matching_oracle = [i for i in renas_recommendations if scrape_rename.has_match(oracle, i)
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


if __name__ == '__main__':
    main()

    # compute_our_recall()
