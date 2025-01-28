import os
import pathlib
import json
from dotenv import load_dotenv

load_dotenv() # load environment variables from .env file.

benchmark_lite_file = pathlib.Path(__file__).parent.parent.joinpath('data/ref_miner/benchmark_lite_v0.1.json')
with open(benchmark_lite_file) as f:
    benchmark_lite_json = json.load(f)

# env_file = pathlib.Path(__file__).parent.parent.joinpath('.env')
# with open(env_file) as f:
#     OPENAI_KEY = f.read().split('\n')[0].split('=')[1].strip('\'')
OPENAI_KEY = os.environ.get('OPENAI_API_KEY')