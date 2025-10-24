import refagent.utils.intellij_server as ij
import refagent.utils.project_manager as pm
import refagent
from pathlib import Path
import json

def test_graph_restore_mode():
    project = pm.EvalProject("flink")
    project.checkout("be25a140f011e6ff93a23f28b3826d376a1c0ba7")
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    intellij_server.open_project(project_path=project.get_project_path())
    intellij_server.open_file(
        rel_file_path=Path('flink-core/src/main/java/org/apache/flink/core/execution/RestoreMode.java'))
    intellij_server.reset_project_reload_counters()
    intellij_server.reload_project()
    response = intellij_server.call_tool('get_linked_elements', line_num=34)
    linked_files = json.loads(response)
    assert len(linked_files) > 0


def test_find_base_class():
    project = pm.EvalProject("flink")
    project.checkout("d14c2d589433bc27d7b90ffdaa5ab5a19cc3842e")
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    intellij_server.open_project(project_path=project.get_project_path())
    intellij_server.open_file(
        rel_file_path=Path('flink-runtime/src/main/java/org/apache/flink/runtime/state/metrics/LatencyTrackingMapState.java'))
    intellij_server.reset_project_reload_counters()
    intellij_server.reload_project()
    response = intellij_server.call_tool('get_linked_elements', line_num=373)
    linked_files = json.loads(response)
    assert len(linked_files) > 0

    assert 'StateLatencyMetricBase.java' in str(linked_files) # this is a parent class that should be linked.
