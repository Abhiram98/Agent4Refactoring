import refagent.benchmark.load as bm_load
import sys
import json
from collections import Counter, defaultdict

if __name__ == "__main__":
    bench_file = sys.argv[1]

    with open(bench_file) as f:
        dataset = bm_load.load_benchmark(json.load(f), bm_load.RenameItem)

    count = Counter()
    tracker = defaultdict(list)
    for item in dataset:
        count[len(item.refactoring_changes)] += 1
        tracker[len(item.refactoring_changes)].append(item)
    print(f"{len(dataset)=}")
    print(f"{count=}")

    # filter count with keys >=5
    filtered_count = {k: v for k, v in count.items() if k >= 4}
    print(f"{sum(filtered_count.values())=}")
    print(f"{filtered_count=}")
    # print(f"{[i.ref_id for i in tracker.values()]=}")
    filtered_tracker = {k: v for k, v in tracker.items() if k >= 4}
    ids = []
    for v in filtered_tracker:
        ids += [i.ref_id for i in filtered_tracker[v]]

    print(f"{len(ids)=}")
    print(f"{sorted(ids)=}")
    print(",".join([str(i) for i in sorted(ids)]))
