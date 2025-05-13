import os
import pathlib
import json
from dotenv import load_dotenv

load_dotenv() # load environment variables from .env file.

data_folder = pathlib.Path(__file__).parent.parent.joinpath('data')
benchmark_lite_file = pathlib.Path(__file__).parent.parent.joinpath('data/ref_miner/flink.json')
benchmark_full_file = pathlib.Path(__file__).parent.parent.joinpath('data/ref_miner/flink.json')
with open(benchmark_lite_file) as f:
    benchmark_lite_json = json.load(f)
with open(benchmark_full_file) as f:
    benchmark_full_json = json.load(f)

LAST_ID = benchmark_lite_json[-1]['id']

# env_file = pathlib.Path(__file__).parent.parent.joinpath('.env')
# with open(env_file) as f:
#     OPENAI_KEY = f.read().split('\n')[0].split('=')[1].strip('\'')
OPENAI_KEY = os.environ.get('OPENAI_API_KEY')
GH_TOKEN = os.environ.get('GH_TOKEN')
IJ_SERVER_URL = os.environ.get('IJ_SERVER_URL')

