import refagent.benchmark.load as bm_load
import refagent


def test_load_benchmark():
    benchmark_data = bm_load.load_benchmark(refagent.benchmark_lite_json)
    assert len(benchmark_data) > 0

    print(f"{benchmark_data[0]=}")
    assert benchmark_data[0].pull_request is not None
    print(f"{benchmark_data[0].pull_request=}")