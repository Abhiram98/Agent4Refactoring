from __future__ import annotations
from typing import Optional
import refagent.utils.project_manager as pm
import refagent.refactoring_types.refactorings as refactoring_types
import refagent.benchmark.creation.add_gh_comments as gh_comment
from pydantic import BaseModel
from typing import List, Optional
from pydantic import BaseModel, model_validator


class BenchmarkItem(BaseModel):
    ref_id: int
    project_name: str
    v1_hash: str
    v2_hash: str
    # intent: str
    # necessary_context: str
    # hint: str
    starting_file: str
    changes: List[refactoring_types.RefminerOut]
    diffs: List[pm.MyDiff]
    pull_request: Optional[gh_comment.GithubPR] = None

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def load(cls, _json) -> "BenchmarkItem":
        return cls(
            ref_id=_json['id'],
            project_name=_json['project'],
            v1_hash=_json['v1_hash'],
            v2_hash=_json['v2_hash'],
            intent=_json['intent'],
            necessary_context=_json['necessary_context'],
            hint=_json['hint'],
            starting_file=_json['starting_file'],
            changes=[refactoring_types.RefminerOut(**c) for c in _json['changes']],
            diffs=pm.EvalProject(_json['project']).get_changes(_json['v2_hash']),
            pull_request=gh_comment.GithubPR(**_json['pull_request']) if _json.get("pull_request") else None
        )

    def to_json(self):
        return {
            'id': self.ref_id,
            'project': self.project_name,
            'v1_hash': self.v1_hash,
            'v2_hash': self.v2_hash,
            'intent': self.intent,
            'necessary_context': self.necessary_context,
            'hint': self.hint,
            'starting_file': self.starting_file,
            'changes': [c.model_dump(mode='json') for c in self.changes],
            'diffs': [d.to_json() for d in self.diffs]
        }


def load_benchmark(json_benchmark) -> list[BenchmarkItem]:
    return [BenchmarkItem.load(i) for i in json_benchmark]
