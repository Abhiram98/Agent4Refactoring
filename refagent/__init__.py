import os
import pathlib
import json
from dotenv import load_dotenv
from pathlib import Path

load_dotenv() # load environment variables from .env file.

repo_root = pathlib.Path(__file__).parent.parent
data_folder = pathlib.Path(__file__).parent.parent.joinpath('data')
benchmark_lite_file = pathlib.Path(__file__).parent.parent.joinpath('data/ref_miner/benchmark_lite_v0.2.json')
benchmark_full_file = pathlib.Path(__file__).parent.parent.joinpath('data/ref_miner/benchmark_full.json')
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

import logging
import inspect

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
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


# if os.getenv('PROMPT_CACHING'):
#     from langchain_core.globals import set_llm_cache
#     from langchain_community.cache import SQLiteCache
#
#     # For SQLite persistent caching
#     set_llm_cache(SQLiteCache(database_path=str(repo_root.joinpath("logs/.langchain_cache.db"))))

    # from langchain_core.language_models.chat_models import BaseChatModel
    #
    # _original_agenerate_with_cache = BaseChatModel._agenerate_with_cache
    # _original_generate_with_cache = BaseChatModel._generate_with_cache
    #
    #
    # async def _agenerate_with_cache_with_tool_workaround(self, messages, *args, **kwargs):
    #     messages = [message.copy(update={"id": None}) for message in messages]
    #     return await _original_agenerate_with_cache(self, messages, *args, **kwargs)
    #
    #
    # def _generate_with_cache_with_tool_workaround(self, messages, *args, **kwargs):
    #     messages = [message.copy(update={"id": "xx"}) for message in messages]
    #     return _original_generate_with_cache(self, messages, *args, **kwargs)
    #
    #
    # BaseChatModel._agenerate_with_cache = _agenerate_with_cache_with_tool_workaround
    # BaseChatModel._generate_with_cache = _generate_with_cache_with_tool_workaround