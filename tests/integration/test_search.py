import json

import refagent.utils.project_manager as pm
import refagent
import refagent.utils.intellij_server as ij

from pathlib import Path

def test_flink_test_method2():
    project = pm.EvalProject("flink")
    project.checkout("afe4c79efa15902369d41ef5a6e73d79a2e7d525")
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    intellij_server.open_project(project_path=project.get_project_path())
    intellij_server.open_file(
        rel_file_path=Path('flink-core/src/test/java/org/apache/flink/api/common/typeutils/TypeSerializerUpgradeTestBase.java'))
    intellij_server.reset_project_reload_counters()
    intellij_server.reload_project()
    response = intellij_server.call_tool('search_symbol',
                                         symbol='testDataMatcher')
    response_dict = json.loads(response)
    assert 'hit_count' in response_dict
    assert 'files' in response_dict
    assert 'file_path' in response_dict['files'][0]
    assert 'hit_count' in response_dict['files'][0]
    assert 'line_nums' in response_dict['files'][0]
    assert len(response_dict['files']) > 2

def test_flink_test_restore_mode():
    project = pm.EvalProject("flink")
    project.checkout("be25a140f011e6ff93a23f28b3826d376a1c0ba7")
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    intellij_server.open_project(project_path=project.get_project_path())
    intellij_server.open_file(
        rel_file_path=Path('flink-runtime-web/src/main/java/org/apache/flink/runtime/webmonitor/handlers/JarRunRequestBody.java'))
    intellij_server.reset_project_reload_counters()
    intellij_server.reload_project()
    response = intellij_server.call_tool('search_symbol',
                                         symbol='restoreMode')
    response_dict = json.loads(response)
    assert 'hit_count' in response_dict
    assert 'files' in response_dict
    assert 'file_path' in response_dict['files'][0]
    assert 'hit_count' in response_dict['files'][0]
    assert 'line_nums' in response_dict['files'][0]
    assert len(response_dict['files']) == 2


def test_flink_test_pojo():
    project = pm.EvalProject("flink")
    project.checkout("afe4c79efa1")
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    intellij_server.open_project(project_path=project.get_project_path())
    intellij_server.open_file(
        rel_file_path=Path('flink-core/src/main/java/org/apache/flink/api/java/typeutils/runtime/PojoSerializer.java'))
    intellij_server.reset_project_reload_counters()
    intellij_server.reload_project()
    response = intellij_server.call_tool('search_symbol',
                                         symbol='serializerConfig')
    response_dict = json.loads(response)
    assert 'hit_count' in response_dict
    assert 'files' in response_dict
    assert 'file_path' in response_dict['files'][0]
    assert 'hit_count' in response_dict['files'][0]
    assert 'line_nums' in response_dict['files'][0]
    assert len(response_dict['files']) == 2

