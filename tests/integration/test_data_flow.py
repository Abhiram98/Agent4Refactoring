import refagent.utils.project_manager as pm
import refagent.utils.intellij_server as ij
import refagent
from pathlib import Path
import json

def test_data_flow_ioexecutor():
    project = pm.EvalProject("flink")
    project.checkout("be25a140f011e6ff93a23f28b3826d376a1c0ba7")
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    intellij_server.open_project(project_path=project.get_project_path())
    intellij_server.open_file(
        rel_file_path=Path('flink-runtime/src/main/java/org/apache/flink/runtime/checkpoint/StandaloneCompletedCheckpointStore.java'))
    _json = {
      "old_name": "ioExecutor",
      "new_name": "ioExecutor2",
    }
    intellij_server.reset_project_reload_counters()
    intellij_server.reload_project()
    response = intellij_server.call_tool('data-flow',
                                         **_json)
    print(f"{response=}")

    assert len(json.loads(response)) == 13
    response_json = json.loads(response)

    expected_files = [
        "flink-runtime/src/main/java/org/apache/flink/runtime/checkpoint/StandaloneCompletedCheckpointStore.java",
        "flink-runtime/src/main/java/org/apache/flink/runtime/checkpoint/CheckpointsCleaner.java",
        "flink-runtime/src/main/java/org/apache/flink/runtime/checkpoint/Checkpoint.java",
        "flink-runtime/src/main/java/org/apache/flink/runtime/checkpoint/PendingCheckpoint.java",
        "flink-runtime/src/test/java/org/apache/flink/runtime/checkpoint/CompletedCheckpointStoreTest.java",
        "flink-runtime/src/main/java/org/apache/flink/runtime/checkpoint/CompletedCheckpoint.java",
        "flink-core/src/main/java/org/apache/flink/util/concurrent/FutureUtils.java",
        "flink-core/src/main/java/org/apache/flink/util/concurrent/Executors.java",
        "flink-runtime/src/main/java/org/apache/flink/runtime/checkpoint/StandaloneCheckpointRecoveryFactory.java",
        "flink-runtime/src/test/java/org/apache/flink/runtime/checkpoint/PerJobCheckpointRecoveryTest.java",
        "flink-runtime/src/main/java/org/apache/flink/runtime/scheduler/SchedulerUtils.java",
        "flink-runtime/src/main/java/org/apache/flink/runtime/dispatcher/cleanup/CheckpointResourcesCleanupRunner.java",
        "flink-core/src/main/java/org/apache/flink/util/Preconditions.java"]
    for file in expected_files:
        assert file in response_json



def test_data_flow_log():
    project = pm.EvalProject("flink")
    project.checkout("be25a140f011e6ff93a23f28b3826d376a1c0ba7")
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    intellij_server.open_project(project_path=project.get_project_path())
    intellij_server.open_file(
        rel_file_path=Path('flink-runtime/src/main/java/org/apache/flink/runtime/checkpoint/Checkpoints.java'))
    _json = {
      "old_name": "LOG",
      "new_name": "LOG2",
    }
    intellij_server.reset_project_reload_counters()
    intellij_server.reload_project()
    response = intellij_server.call_tool('data-flow',
                                         **_json)
    print(f"{response=}")
    assert json.loads(response) == ["flink-runtime/src/main/java/org/apache/flink/runtime/checkpoint/Checkpoints.java"]



def test_data_flow_class():
    project = pm.EvalProject("flink")
    project.checkout("be25a140f011e6ff93a23f28b3826d376a1c0ba7")
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    intellij_server.open_project(project_path=project.get_project_path())
    intellij_server.open_file(
        rel_file_path=Path('flink-runtime/src/main/java/org/apache/flink/runtime/checkpoint/Checkpoints.java'))
    _json = {
      "old_name": "Checkpoints",
      "new_name": "Checkpoints2",
    }
    intellij_server.reset_project_reload_counters()
    intellij_server.reload_project()
    response = intellij_server.call_tool('data-flow',
                                         **_json)
    print(f"{response=}")
    expected_files = [
        'flink-runtime/src/test/java/org/apache/flink/runtime/jobmaster/TestUtils.java',
        'flink-runtime/src/test/java/org/apache/flink/runtime/dispatcher/DispatcherTest.java',
        'flink-libraries/flink-state-processing-api/src/main/java/org/apache/flink/state/api/runtime/SavepointLoader.java',
        'flink-runtime/src/test/java/org/apache/flink/runtime/checkpoint/CheckpointMetadataLoadingTest.java',
        'flink-runtime/src/main/java/org/apache/flink/runtime/checkpoint/PendingCheckpoint.java',
        'flink-runtime/src/test/java/org/apache/flink/runtime/checkpoint/CheckpointsTest.java',
        'flink-libraries/flink-state-processing-api/src/main/java/org/apache/flink/state/api/output/SavepointOutputFormat.java',
        'flink-test-utils-parent/flink-test-utils/src/main/java/org/apache/flink/test/util/TestUtils.java',
        'flink-runtime/src/main/java/org/apache/flink/runtime/checkpoint/Checkpoints.java',
        'flink-runtime/src/main/java/org/apache/flink/runtime/checkpoint/CheckpointCoordinator.java',
        'flink-runtime/src/main/java/org/apache/flink/runtime/dispatcher/Dispatcher.java',
        'flink-runtime/src/test/java/org/apache/flink/runtime/operators/coordination/OperatorCoordinatorSchedulerTest.java',
    ]
    for file in expected_files:
        assert file in json.loads(response)

