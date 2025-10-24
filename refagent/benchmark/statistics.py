import json

from pydantic import BaseModel, Field
from collections import Counter
import os

import refagent.benchmark.load as bm_load
import refagent


class Stats(BaseModel):

    data: list[bm_load.BenchmarkItem] = Field(
        description="the data to compute statistics over."
    )
    model_config = {"arbitrary_types_allowed": True}

    def print(self):
        refactoring_types = Counter()

        for i in self.data:
            refactoring_types += Counter([ref.type for ref in i.refactoring_changes])

        print(f"{refactoring_types=}")
        total = sum(refactoring_types.values())
        ref_types_norm = {
            key: value / total for key, value in refactoring_types.items()
        }
        print(f"{ref_types_norm=}")


def filter_benchmark(bench_data: list[bm_load.BenchmarkItem]):
    count = 0
    for d in bench_data:
        type_change_count = len(
            [
                i
                for i in d.refactoring_changes
                if "Type" in i.description and "Change" in i.description
            ]
        )
        if type_change_count / len(d.refactoring_changes) == 0:
            count += 1

    print(f"filtered for no major type changes -> {count=}")


if __name__ == "__main__":
    json_files = [
        i
        for i in os.listdir(refagent.data_folder.joinpath("ref_miner"))
        if i.endswith(".json")
    ]
    all_data = []
    for fname in json_files:
        with open(refagent.data_folder.joinpath("ref_miner").joinpath(fname)) as f:
            data = json.load(f)
            try:
                all_data += bm_load.load_benchmark(data)
            except:
                print(f"failed to load {fname}")
                continue
    # benchmark_data = bm_load.load_benchmark(refagent.benchmark_lite_json)
    print(f"{len(all_data)=}")
    Stats(data=all_data).print()
    filter_benchmark(all_data)
