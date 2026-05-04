from pydantic import BaseModel
from typing import Optional

class OracleData(BaseModel):
    loc: int
    line_start: int
    line_end: int
    filename: str
    hf_body_loc: int
    url: str

class ExtractMethodTask(BaseModel):
    id: str
    instruction: str
    project_name: str
    url: str
    commit: str
    gold_commit: str
    host_method_name: str
    extracted_method_name: str
    oracle: OracleData
