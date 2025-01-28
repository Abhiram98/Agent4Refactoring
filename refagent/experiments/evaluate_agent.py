import argparse

import refagent.benchmark.load as bm_load
import refagent.utils.project_manager as pm


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


if __name__ == '__main__':
    main()
