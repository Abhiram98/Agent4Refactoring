from __future__ import annotations


class BenchmarkItem:
    def __init__(self, ref_id: int, project_name: str,
                v1_hash: str, v2_hash: str, intent: str,
                necessary_context: str, hint: str,
                starting_files: list[str], changes: list):
        self.ref_id = ref_id
        self.project_name = project_name
        self.v1_hash = v1_hash
        self.v2_hash = v2_hash
        self.intent = intent
        self.necessary_context = necessary_context
        self.hint = hint
        self.starting_files = starting_files
        self.changes = changes

    @staticmethod
    def load(_json) -> BenchmarkItem:
        return BenchmarkItem(_json['id'], _json['project'],
                             _json['v1_hash'], _json['v2_hash'],
                             _json['intent'], _json['necessary_context'],
                             _json['hint'], _json['starting_files'],
                             _json['changes'])


def load_benchmark(json_benchmark) -> list[BenchmarkItem]:
    return [BenchmarkItem.load(i) for i in json_benchmark]
