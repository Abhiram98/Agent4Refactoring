import refagent.utils.project_manager as pm

def test_changed_files():
    project = pm.EvalProject('flink')
    changed_files = project.get_changed_files()
    print(changed_files)
    assert isinstance(changed_files, list)


def test_git_diff():
    project = pm.EvalProject('flink')
    changed_files = project.get_changed_files()
    diff = project.get_git_diff(changed_files[0])
    print(diff)

def test_git_diff():
    project = pm.EvalProject('flink')
    changed_files = project.get_changed_files()
    diff = project.get_git_diff('flink-runtime/src/test/java/org/apache/flink/runtime/scheduler/exceptionhistory/ExceptionHistoryEntryTest.java')
    print(diff)
