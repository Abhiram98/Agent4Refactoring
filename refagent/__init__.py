import pathlib
import json

benchmark_lite_file = pathlib.Path(__file__).parent.parent.joinpath('data/ref_miner/benchmark_lite_v0.json')
with open(benchmark_lite_file) as f:
    benchmark_lite_json = json.load(f)

env_file = pathlib.Path(__file__).parent.parent.joinpath('.env')
with open(env_file) as f:
    OPENAI_KEY = f.read().split('\n')[0].split('=')[0].strip('\'')
