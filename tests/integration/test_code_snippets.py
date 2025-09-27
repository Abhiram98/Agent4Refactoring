from json import JSONDecodeError

from six import assertRaisesRegex

import refagent.utils.project_manager as pm
import refagent.utils.intellij_server as ij
from pathlib import Path
import refagent
import json


def test_flink_snippet():
    project = pm.EvalProject("flink")
    project.checkout("afe4c79efa15902369d41ef5a6e73d79a2e7d525")
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    intellij_server.open_project(project_path=project.get_project_path())
    # intellij_server.open_file(
    #     rel_file_path=Path('flink-core/src/test/java/org/apache/flink/api/common/typeutils/TypeSerializerUpgradeTestBase.java'))
    _json = {
      "name": "testDataMatcher",
      "line_num": 102,
      "code_element_type": "method",
      "file_path": "flink-core/src/test/java/org/apache/flink/api/common/typeutils/TypeSerializerUpgradeTestBase.java"
    }
    intellij_server.reset_project_reload_counters()
    intellij_server.reload_project()
    intellij_server.open_file(Path("flink-core/src/test/java/org/apache/flink/api/java/typeutils/runtime/PojoSerializerUpgradeTestSpecifications.java"))
    response = intellij_server.call_tool('get_source_code_snippet',
                                         **_json)
    print(f"{response=}")
    assert response is not None

    _json = {
        "name": "TypeSerializer",
        "line_num": 406,
        "code_element_type": "class",
        "file_path": "flink-core/src/test/java/org/apache/flink/api/common/typeutils/TypeSerializerUpgradeTestBase.java"
    }
    response = intellij_server.call_tool('get_source_code_snippet',
                                         **_json)

    print(f"{response=}")
    assert response is not None


    _json = {
        "name": "TypeSerializer",
        "line_num": 406,
        "code_element_type": "file",
        "file_path": "flink-core/src/test/java/org/apache/flink/api/common/typeutils/TypeSerializerUpgradeTestBase.java"
    }
    response = intellij_server.call_tool('get_source_code_snippet',
                                         **_json)

    print(f"{response=}")
    assert response is not None
    assert len(response.splitlines()) > 100

    _json = {
        "name": "setupClassloader",
        "line_num": 117,
        "code_element_type": "field",
        "file_path": "flink-core/src/test/java/org/apache/flink/api/common/typeutils/TypeSerializerUpgradeTestBase.java"
    }
    response = intellij_server.call_tool('get_source_code_snippet',
                                         **_json)
    print(f"{response=}")
    assert response is not None
