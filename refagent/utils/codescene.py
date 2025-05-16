from pydantic import BaseModel
import subprocess
import json
from typing import List, Optional

class CodeSceneSmell(BaseModel):
    category: str
    functions: Optional[List] = None
    description: str
    indication: int

class CodeSceneReview(BaseModel):
    score: Optional[float] = None
    review: List[CodeSceneSmell]



def run_codescene(filepath, commit: Commit) -> CodeSceneReview:
    result = subprocess.run(
        ['cs', 'review', '--output-format', 'json', filepath], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    out_ = json.loads(result.stdout)
    return CodeSceneReview(**out_)
