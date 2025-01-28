import refagent.utils.refminer_utils as rminer
import refagent.utils.project_manager as pm


def test_rminer():
    project = pm.EvalProject('flink')
    changes = rminer.default_runner.run(project.get_project_path(), 'a6412b8')
    assert len(changes)>0
