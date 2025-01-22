import json
import refagent
import refagent.utils.project_manager as pm

bench_lite = refagent.benchmark_lite_json

for b in bench_lite:
    v2_hash = b['v2_hash']
    project = b['project']
    print(v2_hash)
    print(project)
    b['v1_hash'] = str(pm.EvalProject(project_name=project).previous_sha(v2_hash).hexsha)

with open(refagent.benchmark_lite_file, "w") as f:
    json.dump(bench_lite, f, indent=4)

