import refagent.utils.refminer_utils as rminer
import refagent.utils.project_manager as pm


def test_rminer():
    project = pm.EvalProject('flink')
    changes = rminer.default_runner.run(project.get_project_path(), 'a6412b8')
    assert len(changes)>0


def test_spring_integration():
    project = pm.EvalProject('spring-integration')
    changes = rminer.default_runner.run(project.get_project_path(), 'e5ce83329f53194727b5190be6215278f7f3d995')
    assert len(changes)>0

def test_ratpack_501():
    project = pm.EvalProject('ratpack')
    changes = rminer.default_runner.run(project.get_project_path(), '025e6366b349bae2ae3622026ff1938a9e418ee7')
    assert len(changes) > 0
