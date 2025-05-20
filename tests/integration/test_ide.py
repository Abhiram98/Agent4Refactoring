import refagent.utils.intellij_server as ij
import refagent
import refagent.utils.project_manager as pm
from pathlib import Path

def test_empty_inspections():
    project = pm.EvalProject("ratpack")
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    project.checkout('9f64053dc0bb21a2d8714f4fca5ae58cbaef2a7d', force=True)
    intellij_server.open_project(project_path=project.get_project_path())
    intellij_server.reset_project_reload_counters()
    intellij_server.reload_project()
    intellij_server.open_file(rel_file_path=Path("ratpack-core/src/main/java/ratpack/override/Override.java"))


    inspections = intellij_server.run_code_inspection(1)
    assert inspections == '[]'

def test_rename():
    project = pm.EvalProject("ratpack")
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    project.checkout('9f64053dc0bb21a2d8714f4fca5ae58cbaef2a7d', force=True)
    intellij_server.open_project(project_path=project.get_project_path())
    intellij_server.reload_project()
    intellij_server.open_file(rel_file_path=Path("ratpack-core/src/main/java/ratpack/override/UserRegistryOverrides.java"))

    result = intellij_server.call_tool('rename', old_name='UserRegistryOverrides', new_name='UserRegistryImpositions')
    assert result=='success'


def test_rename_overridden_method():
    project = pm.EvalProject("ratpack")
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    project.checkout('d803134afbaa200920b95007ab6cb4e975fc2b5c', force=True)
    intellij_server.open_project(project_path=project.get_project_path())

    intellij_server.reset_project_reload_counters()
    intellij_server.reload_project()
    intellij_server.open_file(
        rel_file_path=Path("ratpack-groovy/src/main/java/ratpack/groovy/"
                           "internal/RatpackDslClosureToHandlerTransformer.java"))

    result = intellij_server.call_tool('rename', old_name='modules', new_name='bindings')
    print(result)



def test_rename_overridden_method_flink():
    project = pm.EvalProject("flink")
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    project.checkout('21403e31f4761bdddf5e4e802e0e5eb9b4533202', force=True)
    intellij_server.open_project(project_path=project.get_project_path())

    intellij_server.reset_project_reload_counters()
    intellij_server.reload_project()
    intellij_server.open_file(
        rel_file_path=Path("flink-runtime/src/main/java/org/apache/flink/runtime/state/filesystem/FsStateBackend.java"))


    result = intellij_server.call_tool('rename',
                                       old_name='createOperatorStateBackend',
                                       new_name='createOperatorStateBackend2')
    print(result)



def test_rename_class_flink():
    project = pm.EvalProject("flink")
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    project.checkout('21403e31f4761bdddf5e4e802e0e5eb9b4533202', force=True)
    intellij_server.open_project(project_path=project.get_project_path())

    intellij_server.reset_project_reload_counters()
    intellij_server.reload_project()
    intellij_server.open_file(
        rel_file_path=Path("flink-runtime/src/main/java/org/apache/flink/runtime/state/filesystem/FsStateBackend.java"))


    result = intellij_server.call_tool('rename',
                                       old_name='FsStateBackend',
                                       new_name='FsStateBackend2')
    print(result)

