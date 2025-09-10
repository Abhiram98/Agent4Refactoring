import os
from functools import wraps


import json
from typing import List

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage
import refagent

prompt_cache_file = refagent.repo_root.joinpath('.prompt_cache.json')
if not prompt_cache_file.exists():
    with open(prompt_cache_file, 'w') as f:
        json.dump({}, f)

with open(prompt_cache_file) as f:
    prompt_cache = json.load(f)

def prompt(model: BaseChatModel, messages: List[BaseMessage]):
    key_str = str([i.content for i in messages])

    if os.getenv('PROMPT_CACHING'):
        if prompt_cache.get(key_str):
            return AIMessage(content=prompt_cache.get(key_str))

    response = model.invoke(messages)

    prompt_cache[key_str] = response.content
    with open(prompt_cache_file, 'w') as f:
        json.dump(prompt_cache, f)
    return response