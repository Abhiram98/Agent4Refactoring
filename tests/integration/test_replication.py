from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, BaseMessage
from langchain_core.language_models import LanguageModelInput
from langchain.chat_models.fake import FakeMessagesListChatModel
from pathlib import Path
from typing import Sequence, Union, Dict, Any, Type, Callable
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
import langsmith as ls


import refagent.agents.refactrix.refactoring_agent as ra
import refagent
import refagent.utils.project_manager as pm
import refagent.utils.intellij_server as ij
import refagent.agents.refactrix.planning as planning
import refagent.agents.refactrix.supported_refactorings as sup_ref

def test_flink_5(mocker):
    project = pm.EvalProject('flink')
    project.checkout('30970f56a598b63ace991ff8a89a3409e8d4cb6a', force=True)

    plan = planning.RefactoringPlan(
        steps=[
        {
            "reason": "To improve clarity and convey that the variable represents a range of indices.",
            "final_code": "int subpartitionIndexStart, subpartitionIndexEnd;",
            "execution_details": "Rename variable 'subpartitionIndexSetStart' to 'subpartitionIndexStart' and 'subpartitionIndexSetEnd' to 'subpartitionIndexEnd' in the scope of the ResultPartitionManager class. Ensure all occurrences are updated accordingly.",
            "refactoring_type": "rename",
            "file_path": "flink-runtime/src/main/java/org/apache/flink/runtime/io/network/partition/ResultPartitionManager.java"
        },
        {
            "reason": "To encapsulate the start and end indices into a single object for better structure and maintainability, allowing for easier handling of subpartition index ranges.",
            "final_code": "public class SubpartitionIndexSet { private final int start; private final int end; public SubpartitionIndexSet(int start, int end) { this.start = start; this.end = end; } public int getStart() { return start; } public int getEnd() { return end; } public boolean isEmpty() { return start > end; } public int size() { return end - start + 1; }}",
            "execution_details": "Create a new class 'SubpartitionIndexSet' in the specified file path. Move the fields 'start' and 'end' from the host class to this new class. Update all references to the start and end indices in the host class to use the new 'SubpartitionIndexSet' class. Ensure to implement additional methods like 'isEmpty()' and 'size()' for better usability.",
            "refactoring_type": "extract_class",
            "file_path": "flink-runtime/src/main/java/org/apache/flink/runtime/io/network/partition/SubpartitionIndexSet.java"
        },
        {
            "reason": "To replace the use of two separate integers with the new SubpartitionIndexSet object, improving code readability and maintainability.",
            "final_code": "SubpartitionIndexSet subpartitionIndexSet = new SubpartitionIndexSet(subpartitionIndexStart, subpartitionIndexEnd);",
            "execution_details": "Update all occurrences of 'subpartitionIndexStart' and 'subpartitionIndexEnd' to use the new 'subpartitionIndexSet' object. Ensure that any logic that previously operated on the individual indices is updated to use the methods provided by 'SubpartitionIndexSet', such as 'getStart()' and 'getEnd()'. Additionally, review any method signatures that previously accepted two integers and update them to accept 'SubpartitionIndexSet' instead.",
            "refactoring_type": "type_change",
            "file_path": "flink-runtime/src/main/java/org/apache/flink/runtime/io/network/partition/ResultPartitionManager.java"
        },
        {
            "reason": "To ensure that the method signature of 'createSubpartitionView' is updated to accept the new 'SubpartitionIndexSet' object instead of separate indices, allowing for better encapsulation and readability.",
            "final_code": "subpartitionView = partition.createSubpartitionView(subpartitionIndexSet, availabilityListener);",
            "execution_details": "Update the method signature of 'createSubpartitionView' in the ResultPartition class to accept a 'SubpartitionIndexSet' parameter instead of two integers. Ensure that the implementation of 'createSubpartitionView' is modified accordingly to handle the new parameter. Review all calls to this method throughout the codebase to ensure they are updated to match the new signature.",
            "refactoring_type": "change_method_signature",
            "file_path": "flink-runtime/src/main/java/org/apache/flink/runtime/io/network/partition/ResultPartitionManager.java"
        }
    ]
    )

    planning_patch = mocker.patch('refagent.agents.refactrix.refactoring_agent.Agent.generate_initial_plan')
    planning_patch.return_value = plan

    execution_patch = mocker.patch('refagent.agents.refactrix.refactoring_agent.Agent.execute_initial_plan')
    execution_patch.return_value = AIMessage("Successfullly performed the refactoring")


    # create IJ server connection
    server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    server.open_project(project_path=project.get_project_path())
    rel_file_path = Path("flink-runtime/src/main/java/org/apache/flink/"
                         "runtime/io/network/partition/ResultPartitionManager.java")
    server.open_file(rel_file_path)

    # create agent
    with ls.trace(name=f"refactoring agent test - test_replication:test_flink_5",
                  tags=["test"]) as tracer:
        agent = ra.Agent(ide_server=server, model_name='grazie:openai-gpt-4o-mini', project=project)
        output = agent.run(initial_intent="Modify subpartitionIndex to subpartitionIndexSet (start to end index). "
                                          "Encapsulate int in special object which contains "
                                          "start and end index information.",
                       starting_file=str(rel_file_path))
    print(output)

    source_code = server.call_tool_get("get_source_code")
    print(source_code)
    print(agent.get_trajectory())
