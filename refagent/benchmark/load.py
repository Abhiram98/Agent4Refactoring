from __future__ import annotations
from typing import Optional
import refagent.utils.project_manager as pm
import refagent.refactoring_types.refactorings as refactoring_types
import refagent.benchmark.creation.add_gh_comments as gh_comment

class BenchmarkItem:
    def __init__(self, ref_id: int, project_name: str,
                 v1_hash: str, v2_hash: str, intent: str,
                 necessary_context: str, hint: str,
                 starting_files: list[str], changes: list[refactoring_types.RefminerOut],
                 diffs: list[pm.MyDiff],
                 # pull_request: gh_comment.GithubPR
                 ):
        self.ref_id = ref_id
        self.project_name = project_name
        self.v1_hash = v1_hash
        self.v2_hash = v2_hash
        self.intent = intent
        self.necessary_context = necessary_context
        self.hint = hint
        self.starting_files = starting_files
        self.changes = changes
        self.diffs: list[pm.MyDiff] = diffs
        # self.pull_request = pull_request

    @classmethod
    def load(cls, _json) -> BenchmarkItem:
        return cls(_json['id'], _json['project'],
                   _json['v1_hash'], _json['v2_hash'],
                   _json['intent'], _json['necessary_context'],
                   _json['hint'], _json['starting_files'],
                   [refactoring_types.RefminerOut(**c) for c in _json['changes']],
                   pm.EvalProject(_json['project']).get_changes(_json['v2_hash']))

    def to_json(self):
        return {
            'id': self.ref_id, 'project': self.project_name,
            'v1_hash': self.v1_hash, 'v2_hash': self.v2_hash,
            'intent': self.intent, 'necessary_context': self.necessary_context,
            'hint': self.hint, 'starting_files': self.starting_files,
            'changes': [c.model_dump(mode='json') for c in self.changes],
            'diffs': [d.to_json() for d in self.diffs]
        }


def load_benchmark(json_benchmark) -> list[BenchmarkItem]:
    return [BenchmarkItem.load(i) for i in json_benchmark]
