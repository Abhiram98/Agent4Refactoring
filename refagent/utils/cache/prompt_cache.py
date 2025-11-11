import os
import traceback
from typing import List, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage
from typing_extensions import Callable

import refagent
import sqlite3

prompt_cache_db = refagent.repo_root.joinpath(".prompt_cache.sqlite")
_conn = sqlite3.connect(prompt_cache_db)
_cursor = _conn.cursor()
_cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS prompt_cache (
        key TEXT PRIMARY KEY,
        response TEXT
    )
    """
)
_conn.commit()


def prompt(model: BaseChatModel, messages: List[BaseMessage]):
    model_name = str(model.dict().get("profile", model.dict()))
    key_str = str(model_name) + str([i.content for i in messages])
    cursor, conn = None, None
    if os.getenv("PROMPT_CACHING"):
        conn = sqlite3.connect(prompt_cache_db)
        cursor = conn.cursor()
        cursor.execute("SELECT response FROM prompt_cache WHERE key = ?", (key_str,))
        row = cursor.fetchone()
        if row:
            return AIMessage(content=row[0])

    response = model.invoke(messages)

    if cursor is not None and conn is not None:
        cursor.execute(
            "INSERT OR REPLACE INTO prompt_cache (key, response) VALUES (?, ?)",
            (key_str, response.content),
        )
        conn.commit()

    return response


def prompt_stream(
    model: BaseChatModel,
    messages: List[BaseMessage],
    callback: Optional[Callable] = None,
):
    model_name = str(model.dict().get("profile", model.dict()))
    key_str = str(model_name) + str([i.content for i in messages])
    cursor, conn = None, None
    if os.getenv("PROMPT_CACHING"):
        conn = sqlite3.connect(prompt_cache_db)
        cursor = conn.cursor()
        cursor.execute("SELECT response FROM prompt_cache WHERE key = ?", (key_str,))
        row = cursor.fetchone()
        if row:
            return AIMessage(content=row[0])

    all_chunks = []
    for chunk in model.stream(messages):
        all_chunks.append(chunk.content)
        if callback is not None:
            try:
                callback(chunk)
            except Exception as e:
                print(e)
                print("Callback threw the exception")
                traceback.print_exc()
    final_message = "".join(all_chunks)

    if cursor is not None and conn is not None:
        cursor.execute(
            "INSERT OR REPLACE INTO prompt_cache (key, response) VALUES (?, ?)",
            (key_str, final_message),
        )
        conn.commit()

    return final_message
