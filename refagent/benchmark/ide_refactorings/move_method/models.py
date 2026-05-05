from pydantic import BaseModel
from typing import Optional

class MoveMethodTask(BaseModel):
    id: str
    instruction: str
    project_name: str
    url: str
    base_commit: str
    gold_commit: str
    branch_name: str
    method_name: str
    source_class: str
    target_class: str
    ref_id: int
    original_description: str
