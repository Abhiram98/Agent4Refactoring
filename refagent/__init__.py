import os
import pathlib
import json
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()  # load environment variables from .env file.

repo_root = pathlib.Path(__file__).parent.parent
data_folder = pathlib.Path(__file__).parent.parent.joinpath("data")

data_folder_exists = data_folder.exists()

benchmark_lite_file = pathlib.Path(__file__).parent.parent.joinpath(
    "data/ref_miner/benchmark_lite_v0.2.json"
)
benchmark_full_file = pathlib.Path(__file__).parent.parent.joinpath(
    "data/ref_miner/benchmark_full.json"
)

if data_folder_exists:
    with open(benchmark_lite_file) as f:
        benchmark_lite_json = json.load(f)
    with open(benchmark_full_file) as f:
        benchmark_full_json = json.load(f)

    LAST_ID = benchmark_lite_json[-1]["id"]


OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
GH_TOKEN = os.environ.get("GH_TOKEN")
IJ_SERVER_URL = os.environ.get("IJ_SERVER_URL")

import logging
import inspect

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)


def my_print(*args, **kwargs):
    frame = inspect.currentframe().f_back
    try:
        filename = Path(frame.f_code.co_filename).relative_to(repo_root)
    except ValueError:
        filename = Path(frame.f_code.co_filename)
    lineno = frame.f_lineno

    message = " ".join(str(a) for a in args)
    logging.info(f"{filename}:{lineno} - {message}")


import builtins

builtins.print = my_print
