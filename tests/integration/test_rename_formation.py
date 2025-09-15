from json import JSONDecodeError

from six import assertRaisesRegex

import refagent.utils.project_manager as pm
import refagent.utils.intellij_server as ij
from pathlib import Path
import refagent
import json


def test_flink_test_method_formation():
    project = pm.EvalProject("flink")
    project.checkout("afe4c79efa15902369d41ef5a6e73d79a2e7d525")
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    intellij_server.open_project(project_path=project.get_project_path())
    intellij_server.open_file(
        rel_file_path=Path('flink-core/src/test/java/org/apache/flink/api/common/typeutils/TypeSerializerUpgradeTestBase.java'))
    _json = {
      "old_name": "testDataMatcher",
      "new_name": "testDataMatcherRaihan",
      "line_num": 102,
      "code_element_type": "method"
    }
    intellij_server.reset_project_reload_counters()
    intellij_server.reload_project()
    response = intellij_server.call_tool('form-rename-object',
                                         **_json)
    print(f"{response=}")
    assert response is not None

    response2 = intellij_server.call_tool('rename', **json.loads(response))
    assert response2 == 'success'

    _json = {
        "old_name": "blajblaj",
        "new_name": "bbbb",
        "line_num": 102,
        "code_element_type": "method"
    }
    # intellij_server.reset_project_reload_counters()
    # intellij_server.reload_project()
    response = intellij_server.call_tool('form-rename-object',
                                         **_json)
    try:
        json.loads(response)
        assert False
    except JSONDecodeError:
        print("expcted error")


    _json = {
        "old_name": "TypeSerializer",
        "new_name": "TypeSerializerANAME",
        "line_num": 406,
        "code_element_type": "class"
    }
    # intellij_server.reset_project_reload_counters()
    # intellij_server.reload_project()
    response = intellij_server.call_tool('form-rename-object',
                                         **_json)

    response_json = json.loads(response)
    assert 'resolved_file_path' in response_json
    assert response_json['resolved_file_path'] is not None
    assert 'resolved_start_line' in response_json
    assert response_json['resolved_start_line'] is not None



def test_flink_test_method_formation_all():
    project = pm.EvalProject("flink")
    project.checkout("afe4c79efa15902369d41ef5a6e73d79a2e7d525")
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    intellij_server.open_project(project_path=project.get_project_path())
    intellij_server.open_file(
        rel_file_path=Path('flink-core/src/test/java/org/apache/flink/api/common/typeutils/TypeSerializerUpgradeTestBase.java'))
    _json = {
      "old_name": "testDataMatcher",
      "new_name": "testDataMatcherRaihan",
    }
    intellij_server.reset_project_reload_counters()
    intellij_server.reload_project()
    response = intellij_server.call_tool('form-rename-object-all',
                                         **_json)
    print(f"{response=}")
    assert len(json.loads(response)) == 14