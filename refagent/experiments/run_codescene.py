import json
import refagent
import refagent.benchmark.load as benchmark_load
from typing import List, Optional
import subprocess
from pydantic import BaseModel
import refagent.utils.project_manager as pm


class CodeSceneSmell(BaseModel):
    category: str
    functions: Optional[List] = None
    description: str
    indication: int

class CodeSceneReview(BaseModel):
    score: Optional[float] = None
    review: List[CodeSceneSmell]



def run_codescene(filepath) -> CodeSceneReview:
    result = subprocess.run(
        ['cs', 'review', '--output-format', 'json', filepath], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    out_ = json.loads(result.stdout)
    return CodeSceneReview(**out_)


def process_benchmark(benchmark: List[benchmark_load.BenchmarkItem]) -> List[benchmark_load.BenchmarkItem]:

    bench_with_smells = []

    for i, bench in enumerate(benchmark):
        print(f"processing {bench.project_name} - {bench.ref_id}")
        print(f"progress - {i}/{len(benchmark)}")
        for d in bench.diffs:
            if d.git_diff.b_path is not None and d.git_diff.a_path is not None:

                project = pm.EvalProject(bench.project_name)

                try:
                    project.checkout(bench.v1_hash, force=True)
                    review_before = run_codescene(
                        str(project.get_project_path().joinpath(d.git_diff.b_path))
                    )

                    project.checkout(bench.v2_hash, force=True)
                    review_after = run_codescene(
                        str(project.get_project_path().joinpath(d.git_diff.a_path))
                    )
                except:
                    print("codescene failed. skipping")
                    continue

                if (review_before.score is not None and review_after.score is not None and
                        review_before.score < review_after.score):
                    print("Smell improved!")
                    print(f"before: {review_before.score}")
                    print(f"after: {review_after.score}")
                    print(f"file: {d.git_diff.b_path} and {d.git_diff.a_path} with smells: {review_before.review} -> {review_after.review}")
                    bench_with_smells.append(
                        {"benchmark": bench.to_json(),
                         "a_file": d.git_diff.a_path,
                         "b_file": d.git_diff.b_path,
                         "before": json.loads(review_before.model_dump_json()),
                         "after": json.loads(review_after.model_dump_json())})
                    break
                else:
                    print(f"skipping {d.git_diff.b_path} and {d.git_diff.a_path} because they are not smelly.")
    return bench_with_smells

if __name__ == '__main__':
    benchmark = benchmark_load.load_benchmark(refagent.benchmark_full_json)
    processed = process_benchmark(benchmark)
    print(f"{len(processed)} = ")
    with open(str(refagent.benchmark_full_file) + ".codescene.json", "w") as f:
        json.dump(processed, f, indent=4)

