from openai import project
import refagent.utils.project_manager as pm
from datetime import datetime, timedelta, UTC


def test_changed_files():
    project = pm.EvalProject("flink")
    changed_files = project.get_changed_files()
    print(changed_files)
    assert isinstance(changed_files, list)


def test_git_diff():
    project = pm.EvalProject("flink")
    changed_files = project.get_changed_files()
    diff = project.get_git_diff(changed_files[0])
    print(diff)


def test_git_diff():
    project = pm.EvalProject("flink")
    changed_files = project.get_changed_files()
    diff = project.get_git_diff(
        "flink-runtime/src/test/java/org/apache/flink/runtime/scheduler/exceptionhistory/ExceptionHistoryEntryTest.java"
    )
    print(diff)


def test_reset_head():
    project = pm.EvalProject("flink")
    project.reset_head(3)
    print(project.git_repo.head.commit.hexsha)


def test_restore_changes():
    project = pm.EvalProject("flink")
    project.restore_changes()


def test_iter_commits():
    project = pm.EvalProject("flink")
    project.git_repo.iter_commits()


def test_flink_master_branch_name():
    project = pm.EvalProject("flink")
    master_branch = project.get_master_branch_name()
    assert master_branch == "master"


def test_spring_integration_master_branch_name():
    project = pm.EvalProject("spring-integration")
    master_branch = project.get_master_branch_name()
    assert master_branch == "main"


def test_kafka_master_branch_name():
    project = pm.EvalProject("kafka")
    master_branch = project.get_master_branch_name()
    assert master_branch == "trunk"


def test_get_remote_url():
    project = pm.EvalProject("flink")
    remote_url = project.get_remote_url()
    print(remote_url)
    assert remote_url.startswith("https://github.com/")
    assert remote_url.endswith("flink")


def test_commit_time():
    project = pm.EvalProject("flink")
    commit = project.git_repo.commit("a6412b8")
    # check if the commit if older than two days from current time
    should_send_message = commit.authored_datetime > datetime.now(UTC) - timedelta(
        days=2
    )
    print(should_send_message)
    print(commit.authored_datetime)
    assert not should_send_message
