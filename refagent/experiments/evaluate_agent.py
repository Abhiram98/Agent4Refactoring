import argparse
import json

import refagent
import refagent.benchmark.load as bm_load
import refagent.utils.project_manager as pm
import refagent.utils.refminer_utils as rminer
import refagent.refactoring_types.refactorings as refactoring_types

from pathlib import Path


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

    with open(args.benchmark_file_path) as f:
        benchmark_json = json.load(f)
    benchmark = bm_load.load_benchmark(benchmark_json)

    for result in agent_results:
        bench_points = [i for i in benchmark if i.ref_id==result['id']]
        assert len(bench_points) == 1
        bench_point = bench_points[0]

        id = result['id']
        assert id == bench_point.ref_id
        commit = result['response']['commit_hash']
        project = pm.EvalProject(bench_point.project_name)
        refactorings = rminer.default_runner.run(project.get_project_path(), commit)
        refactorings = [i for i in refactorings if i.type.split()[0] == 'Rename']
        oracle_refactorings = bench_point.refactoring_changes
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

        print(f"avg recall = {overall_recall / total_oracle}")
        print(f"avg precision = {overall_precision / total_oracle}")
        print(f"{precision=}")
        print(f"{len(oracle_refactorings)=}")
        print(f"{len(refactorings)=}")
        print(f"{overall_recall=}")
        print(f"{total_oracle=}")
        print("-----------")
        print()

        assert len(oracle_refactorings) == len(true_positives) + len(false_negatives)
        assert len(refactorings) == len(true_positives) + len(false_positives)

        report.append(
            {
                "id": id,
                "oracle": [i.model_dump() for i in oracle_refactorings],
                "agent_refactorings": [i.model_dump() for i in refactorings],
                "recall": recall/len(oracle_refactorings),
                "precision": precision,
                "false_negatives": [i.model_dump() for i in false_negatives],
                "false_positives": [i.model_dump() for i in false_positives],
                "true_positives": [i.model_dump() for i in true_positives],
            }
        )

    with open(report_file_path, 'w') as f:
        json.dump(sorted(report, key=lambda x: x['id']), f, indent=4)




if __name__ == '__main__':
    main()
