import argparse
import json

import refagent
import refagent.benchmark.load as bm_load
import refagent.utils.project_manager as pm
import refagent.utils.refminer_utils as rminer
import refagent.refactoring_types.refactorings as refactoring_types


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
    args = parser.parse_args()

    print(f'File Path: {args.agent_outfile_path}')
    with open(args.agent_outfile_path) as f:
        agent_results = json.load(f)

    overall_recall = 0
    total_oracle = 0
    benchmark = bm_load.load_benchmark(refagent.benchmark_lite_json)
    for result in agent_results:
        bench_points = [i for i in benchmark if i.ref_id==result['id']]
        assert len(bench_points) == 1
        bench_point = bench_points[0]

        id = result['id']
        assert id == bench_point.ref_id
        commit = result['response']['commit_hash']
        project = pm.EvalProject(bench_point.project_name)
        refactorings = rminer.default_runner.run(project.get_project_path(), commit)
        oracle_refactorings = rminer.default_runner.run(project.get_project_path(), bench_point.v2_hash)
        recall = 0
        total_oracle += 1
        for oracle in oracle_refactorings:
            # if oracle.type in ['Extract Variable', 'Inline Variable']:
            #     continue
            for i in refactorings:
                if oracle == i:
                    recall += 1
                    break
        print(f"captured {recall}/{len(oracle_refactorings)} in bench point {bench_point.ref_id}")
        if len(oracle_refactorings) > 0:
            overall_recall += recall/len(oracle_refactorings)
        # total_oracle += len(oracle_refactorings)

        print(f"recall = {overall_recall / total_oracle}")
        print(f"{overall_recall=}")
        print(f"{total_oracle=}")




if __name__ == '__main__':
    main()
