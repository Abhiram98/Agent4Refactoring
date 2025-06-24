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

def test_ratpack_507():
    project = pm.EvalProject('ratpack')
    changes = rminer.default_runner.run(project.get_project_path(), '05aaa17550d8266b428bb7cbac4514669b696d75')
    assert len(changes) > 0

def test_ratpack_540():
    project = pm.EvalProject('ratpack')
    changes = rminer.default_runner.run(project.get_project_path(), '1cadba3f34e0a3d34c1c97686d825d54f92ced1c')
    assert len(changes) > 0


def test_ratpack_602():
    project = pm.EvalProject('ratpack')
    changes = rminer.default_runner.run(project.get_project_path(), '4f61fc84e93185e6f08ec3b84202543df6275dfb')
    assert len(changes) > 0


def test_ratpack_617():
    project = pm.EvalProject('ratpack')
    changes = rminer.default_runner.run(project.get_project_path(), '08abc8fe1453c91b5997e4fb5a7155799aefa54a')
    print(changes)
    assert len(changes) > 0

def test_ratpack_572():
    project = pm.EvalProject('ratpack')
    changes = rminer.default_runner.run(project.get_project_path(), '3cddf4dcfd342155f156bfd813e22699e9e92098')
    print(changes)
    assert len(changes) > 0

def test_ratpack_557():
    project = pm.EvalProject('ratpack')
    changes = rminer.default_runner.run(project.get_project_path(), '30b186e119df5bf959a4234f640a2dbab406db71')
    print(changes)
    assert len(changes) > 0
    #