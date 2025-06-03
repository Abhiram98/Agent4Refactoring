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

def test_inspections_ratpack():
    project = pm.EvalProject("ratpack")
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    intellij_server.open_file(
        rel_file_path=Path("ratpack-groovy/src/main/java/ratpack/groovy/Groovy.java"))
    result = intellij_server.run_code_inspection(1)
    print(result)


def test_ide_alerting_rename():
    project = pm.EvalProject('ratpack')
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    project.checkout('72bddd865fc1c39377ff00124451c243ef8b62ba', force=True)
    intellij_server.open_project(project_path=project.get_project_path())

    intellij_server.open_file(
        rel_file_path=Path("ratpack-session/src/main/java/ratpack/session/store/SessionStoreAdapter.java"))

    # intellij_server.call_tool('rename', old_name='SessionStoreAdapter', new_name='SessionStore')

def test_rename_compile_ele():
    project = pm.EvalProject("ratpack")
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    intellij_server.open_file(
        rel_file_path=Path("ratpack-groovy/src/main/java/ratpack/groovy/Groovy.java"))
    result = intellij_server.call_tool('rename', old_name='String', new_name='Ele')
    result2 = intellij_server.call_tool('rename', old_name='Path', new_name='Ele')
    print(result)
    print(result2)

def test_rename_invalid_identifiers():
    project = pm.EvalProject("ratpack")
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    intellij_server.open_file(
        rel_file_path=Path("ratpack-groovy/src/main/java/ratpack/groovy/Groovy.java"))
    result = intellij_server.call_tool('rename', old_name='my String', new_name='Ele')
    result2 = intellij_server.call_tool('rename', old_name='Path', new_name='Ele 12')
    result3 = intellij_server.call_tool('rename', old_name='Path', new_name='Ele')
    print(result)
    print(result2)
    print(result3)


def test_rename_line_number():
    project = pm.EvalProject("ratpack")
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    intellij_server.open_project(project_path=project.get_project_path())
    project.checkout('2e1847acf764b317a2f41353b6dad4e47e818d8b', force=True)
    response = intellij_server.open_file(
        rel_file_path=Path("ratpack-core/src/main/java/ratpack/exec/Promise.java"))
    response = intellij_server.call_tool('rename', old_name='function', new_name='rightFunction', line_num=769)
    print(response)


def test_update_comment():
    project = pm.EvalProject("ratpack")
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    intellij_server.open_project(project_path=project.get_project_path())
    project.checkout('2e1847acf764b317a2f41353b6dad4e47e818d8b', force=True)
    response = intellij_server.open_file(
        rel_file_path=Path("ratpack-core/src/main/java/ratpack/exec/Promise.java"))
    response = intellij_server.call_tool('update_comment', find_text='transformer', replace_text='myTransformer', line_num=452)
    print(response)

def test_update_comment_2():
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    intellij_server.call_tool('update_comment', find_text='updated', replace_text='modified', line_num=457)


def test_rename_class():
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    project = pm.EvalProject("ratpack")
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    intellij_server.open_project(project_path=project.get_project_path())
    project.checkout('2e1847acf764b317a2f41353b6dad4e47e818d8b', force=True)
    response = intellij_server.open_file(
        rel_file_path=Path("ratpack-core/src/main/java/ratpack/exec/Promise.java"))
    response = intellij_server.call_tool('rename', old_name='Promise', new_name='MyPromise', line_num=57)
    assert response == 'success'

def test_rename_method():
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    project = pm.EvalProject("ratpack")
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    intellij_server.open_project(project_path=project.get_project_path())
    project.checkout('2e1847acf764b317a2f41353b6dad4e47e818d8b', force=True)
    response = intellij_server.open_file(
        rel_file_path=Path("ratpack-core/src/main/java/ratpack/exec/Promise.java"))
    response = intellij_server.call_tool('rename', old_name='async', new_name='async2', line_num=95)
    assert response == 'success'


def test_rename_overriden_method():
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    project = pm.EvalProject("ratpack")
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    intellij_server.open_project(project_path=project.get_project_path())
    project.checkout('2e1847acf764b317a2f41353b6dad4e47e818d8b', force=True)
    response = intellij_server.open_file(
        rel_file_path=Path("ratpack-core/src/main/java/ratpack/exec/internal/DefaultPromise.java"))
    response = intellij_server.call_tool('rename', old_name='then', new_name='async2', line_num=37)
    assert response == 'success'


def test_rename_return_type():
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    project = pm.EvalProject("ratpack")
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    intellij_server.open_project(project_path=project.get_project_path())
    project.checkout('890017f342d5ac93c7875a4e2be87a9304ff9f73', force=True)
    response = intellij_server.open_file(
        rel_file_path=Path("ratpack-guice/src/main/java/ratpack/guice/internal/DefaultRatpackModule.java"))
    response = intellij_server.call_tool('rename', old_name='Background', new_name='ExecController', line_num=49)
    assert response == 'success'


def test_rename_called_method():
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    project = pm.EvalProject("ratpack")
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    intellij_server.open_project(project_path=project.get_project_path())
    project.checkout('890017f342d5ac93c7875a4e2be87a9304ff9f73', force=True)
    response = intellij_server.open_file(
        rel_file_path=Path("ratpack-guice/src/main/java/ratpack/guice/internal/DefaultRatpackModule.java"))
    response = intellij_server.call_tool('rename', old_name='getBackground', new_name='getExecController', line_num=50)
    assert response == 'success'

def test_rename_compiled_element():
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    project = pm.EvalProject("ratpack")
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    intellij_server.open_project(project_path=project.get_project_path())
    project.checkout('890017f342d5ac93c7875a4e2be87a9304ff9f73', force=True)
    response = intellij_server.open_file(
        rel_file_path=Path("ratpack-guice/src/main/java/ratpack/guice/internal/DefaultRatpackModule.java"))
    response = intellij_server.call_tool('rename', old_name='ByteBufAllocator', new_name='ByteBufAllocator2', line_num=44)
    print(response)
    assert response != 'success'

def test_rename_equal_method_and_param():
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    project = pm.EvalProject("ratpack")
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    intellij_server.open_project(project_path=project.get_project_path())
    project.checkout('aee5543003af39deb386843db1be1c791e668605', force=True)
    response = intellij_server.open_file(
        rel_file_path=Path("ratpack-groovy/src/main/java/ratpack/groovy/handling/internal/DefaultGroovyChain.java"))
    response = intellij_server.call_tool('rename',
                                         old_name='handler',
                                         new_name='path',
                                         line_num=121,
                                         code_element_type='parameter'
                                         )
    # print(response)
    assert response == 'success'

def test_rename_equal_method_and_param2():
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    project = pm.EvalProject("ratpack")
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    intellij_server.open_project(project_path=project.get_project_path())
    project.checkout('aee5543003af39deb386843db1be1c791e668605', force=True)
    response = intellij_server.open_file(
        rel_file_path=Path("ratpack-groovy/src/main/java/ratpack/groovy/handling/internal/DefaultGroovyChain.java"))
    response = intellij_server.call_tool('rename',
                                         old_name='handler',
                                         new_name='path',
                                         line_num=121,
                                         code_element_type='method'
                                         )
    # print(response)
    assert response == 'success'


def test_argouml_905():
    project = pm.EvalProject("argouml")
    project.checkout('8154894d806e29d83bcdd34655ed2417a24d4ffc', force=True)
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    intellij_server.open_project(project_path=project.get_project_path())
    intellij_server.open_file(rel_file_path=Path("src_new/org/argouml/uml/cognitive/critics/ClAttributeCompartment.java"))
    response = intellij_server.call_tool('rename',
                                         old_name='fig',
                                         new_name='attributesCompartmentFig',
                                         line_num=56,
                                         code_element_type='field')
    assert response == 'success'


def test_argouml_910():
    project = pm.EvalProject("argouml")
    project.checkout('982c953f978c3238fa7bde44e2a1147197a7d1bb', force=True)
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    intellij_server.open_project(project_path=project.get_project_path())
    intellij_server.open_file(rel_file_path=Path("src_new/org/argouml/uml/diagram/ui/ActionAddAllClassesFromModel.java"))
    response = intellij_server.call_tool('rename',
                                         old_name='myTabName',
                                         new_name='tabName',
                                         line_num=55,
                                         code_element_type='parameter')
    assert response == 'success'

def test_argouml_913():
    project = pm.EvalProject("argouml")
    project.checkout('3a89da0fec36336116decff9a81fc66551c1ef4d', force=True)
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    intellij_server.open_project(project_path=project.get_project_path())
    intellij_server.open_file(
        rel_file_path=Path("src/uci/gef/ModeCreateEdge.java"))
    response = intellij_server.call_tool('rename',
                                         old_name='_editor',
                                         new_name='ce',
                                         line_num=97,
                                         code_element_type='variable')
    assert response == 'success'

def test_argouml_921():
    project = pm.EvalProject("argouml")
    project.checkout('1ab4e8046393cac62d61eb0e3c5e82eb5e8bb921', force=True)
    intellij_server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    intellij_server.open_project(project_path=project.get_project_path())
    intellij_server.open_file(
        rel_file_path=Path("src_new/org/argouml/uml/diagram/activity/ui/SelectionActionState.java"))

    response = intellij_server.call_tool('rename',
                                         old_name='cls',
                                         new_name='existingNode',
                                         line_num=237,
                                         code_element_type='variable')
    assert response == 'success'

#