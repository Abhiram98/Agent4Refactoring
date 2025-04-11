import refagent.utils.project_manager as pm

def test_changed_files():
    project = pm.EvalProject('flink')
    changed_files = project.get_changed_files()
    print(changed_files)
    assert isinstance(changed_files, list)