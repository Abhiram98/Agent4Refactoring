from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, BaseMessage
from langchain_core.language_models import LanguageModelInput
from langchain.chat_models.fake import FakeMessagesListChatModel
from pathlib import Path
from typing import Sequence, Union, Dict, Any, Type, Callable
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool

import refagent.agents.refactrix.refactoring_agent as ra
import refagent
import refagent.utils.project_manager as pm
import refagent.utils.intellij_server as ij
import refagent.agents.refactrix.planning as planning

class MyFakeListChatModel(FakeMessagesListChatModel):
    def bind_tools(
        self,
        tools: Sequence[Union[Dict[str, Any], Type, Callable, BaseTool]],
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, BaseMessage]:
        return self



def test_kafka_AssignmentsManager(mocker):
    faker1_messages = [
        AIMessage(
            '{"refactoring_type":"rename","reason":"The variable \'inflight\' is used to represent assignments currently being processed, which could be more clearly named \'currentAssignments\' to improve code readability."}',
            additional_kwargs={'function_call': 'choose_refactoring'},
            tool_calls=[{'name': 'choose_refactoring', 'args': {'refactoring_type': 'rename',
                                                                'reason': "The variable 'inflight' is used to represent assignments currently being processed, which could be more clearly named 'currentAssignments' to improve code readability."},
                         'id': 'call_choose_refactoring_6af4e70f-24c7-47c3-bc00-abe1d92159df-temp',
                         'type': 'tool_call'}],
            id='run-cc66b481-c884-46c9-9841-974498876fea-0'
        ),
        AIMessage(
            '{"old_name":"inflight","new_name":"currentAssignments"}',
            additional_kwargs={'function_call': 'rename'},
            id='run-3a3c54c9-17ac-42ce-8ee6-515178417938-0',
            tool_calls=[
                {'name': 'rename', 'args': {'old_name': 'inflight', 'new_name': 'currentAssignments'},
                 'id': 'call_rename_deaeb5c8-dab9-4483-b319-f8b23c06bc62-temp', 'type': 'tool_call'}]
        )
        ,
        AIMessage(
            'Nothing more to do.'
        )
    ]

    create_model_mock = mocker.patch("refagent.agents.refactrix.refactoring_agent.Agent.create_model")
    create_model_mock.return_value = MyFakeListChatModel(responses=faker1_messages)


    # initialize repo.
    project = pm.EvalProject('kafka')
    project.checkout('extract-idempotentCreateSnapshot-testIsInStatesCaseInsensitive-130af38')

    # create IJ server connection
    server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    server.open_project(project_path=project.get_project_path())
    rel_file_path = Path("server/src/main/java/org/apache/kafka/server/AssignmentsManager.java")
    server.open_file(rel_file_path)

    # create agent
    agent = ra.Agent(ide_server=server, model_name='fake1')
    output = agent.run(initial_intent="refactor this file", starting_file=str(rel_file_path))
    print(output)

    source_code = server.call_tool_get("get_source_code")

    # Check that the variable indeed got renamed.
    assert "private volatile Map<TopicIdPartition, AssignmentEvent> currentAssignments = null;" in source_code



def test_custom_refactoring(mocker):
    new_method_content = """public void run() {
        // Ensure no assignments are in flight while dispatching
        if (inflight != null) {
            throw new IllegalStateException("Bug. Should not be dispatching while there are assignments in flight");
        }

        // If no pending assignments, log and return early
        if (pending.isEmpty()) {
            log.trace("No pending assignments, no-op dispatch");
            return;
        }

        // Move all pending assignments to the inflight map, but only up to the max allowed
        Collection<AssignmentEvent> events = new ArrayList<>(pending.values());
        pending.clear();  // Clear the pending assignments map
        inflight = new HashMap<>();  // Reinitialize the inflight assignments map

        for (AssignmentEvent event : events) {
            if (inflight.size() < AssignReplicasToDirsRequest.MAX_ASSIGNMENTS_PER_REQUEST) {
                inflight.put(event.partition, event);
            } else {
                // Once max assignments are reached, put the remaining ones back in pending
                pending.put(event.partition, event);
            }
        }

        // Log if there are too many assignments to fit in one request
        if (!pending.isEmpty()) {
            log.warn("Too many assignments ({} total) to fit in one call, sending only {} and queueing the rest",
                    AssignReplicasToDirsRequest.MAX_ASSIGNMENTS_PER_REQUEST + pending.size(),
                    AssignReplicasToDirsRequest.MAX_ASSIGNMENTS_PER_REQUEST);
        }

        // Prepare the assignments map for dispatching
        Map<TopicIdPartition, Uuid> assignment = inflight.entrySet().stream()
                .collect(Collectors.toMap(Map.Entry::getKey, e -> e.getValue().dirId));

        // Log the assignments being dispatched
        log.debug("Dispatching {} assignments: {}", assignment.size(), assignment);

        // Send the request to the channel manager
        channelManager.sendRequest(new AssignReplicasToDirsRequest.Builder(
                buildRequestData(brokerId, brokerEpochSupplier.get(), assignment)),
                new AssignReplicasToDirsRequestCompletionHandler());
    }
    """
    fake_messages = [
    AIMessage(
        '{"refactoring_type":"custom_refactoring","reason":""}',
        additional_kwargs={'function_call': 'choose_refactoring'},
        tool_calls=[{'name': 'choose_refactoring', 'args': {'refactoring_type': 'custom_refactoring',
                                                            'reason': "improve the `run` method in DispathEvent class, "
                                                                      "to focus on increasing code "
                                                                      "clarity, reducing potential issues, "
                                                                      "and improving performance where possible. I've "
                                                                      "also added a few comments for clarity."},
                     'id': 'call_choose_refactoring_6af4e70f-24c7-47c3-bc00-abe1d92159df-temp',
                     'type': 'tool_call'}],
        id='run-cc66b481-c884-46c9-9841-974498876fea-0'
    ),
    AIMessage(
        '{"file_path":"AssignmentsManager","method_name":"run","new_content":"'+new_method_content+'"}',
        additional_kwargs={'function_call': 'replace_method_contents'},
        id='run-3a3c54c9-17ac-42ce-8ee6-515178417938-0',
        tool_calls=[
            {'name': 'replace_method_contents', 'args': {'file_path': 'AssignmentsManager',
                                                         'method_name': 'run',
                                                         'new_content': new_method_content},
             'id': 'call_rename_deaeb5c8-dab9-4483-b319-f8b23c06bc62-temp', 'type': 'tool_call'}]
    ),
    AIMessage(
        '{"file_path":"AssignmentsManager","method_name":"run","new_content":"'+new_method_content+'","line_num":308}',
        additional_kwargs={'function_call': 'replace_method_contents'},
        id='run-3a3c54c9-17ac-42ce-8ee6-515178417938-01',
        tool_calls=[
            {'name': 'replace_method_contents', 'args': {'file_path': 'AssignmentsManager',
                                                         'method_name': 'run',
                                                         'new_content': new_method_content,
                                                         'line_num': 308},
             'id': 'call_rename_deaeb5c8-dab9-4483-b319-f8b23c06bc62-temp1', 'type': 'tool_call'}]
    ),
        AIMessage("I give up."),
        AIMessage("No more refactorings to perform.")
]

    create_model_mock = mocker.patch("refagent.agents.refactrix.refactoring_agent.Agent.create_model")
    create_model_mock.return_value = MyFakeListChatModel(responses=fake_messages)

    # initialize repo.
    project = pm.EvalProject('kafka')
    project.checkout('extract-idempotentCreateSnapshot-testIsInStatesCaseInsensitive-130af38')

    # create IJ server connection
    server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    server.open_project(project_path=project.get_project_path())
    rel_file_path = Path("server/src/main/java/org/apache/kafka/server/AssignmentsManager.java")
    server.open_file(rel_file_path)

    # initial source code
    init_source_code = server.call_tool_get("get_source_code")

    # create agent
    agent = ra.Agent(ide_server=server, model_name='fake1')
    output = agent.run(initial_intent="refactor this file", starting_file=str(rel_file_path))
    print(output)

    source_code = project.get_file_contents(rel_file_path)

    # Check that refactorings have been reverted, due to failing tests.
    assert init_source_code == source_code


def test_flink_flaky():

    # initialize repo.
    project = pm.EvalProject('flink')
    project.checkout('21403e31f4761bdddf5e4e802e0e5eb9b4533202')

    # create IJ server connection
    server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    server.open_project(project_path=project.get_project_path())
    rel_file_path = Path("flink-runtime/src/test/java/org/apache/flink/"
                         "runtime/scheduler/exceptionhistory/ExceptionHistoryEntryTest.java")
    server.open_file(rel_file_path)

    # create agent
    agent = ra.Agent(ide_server=server, model_name='grazie:openai-gpt-4o-mini')
    output = agent.run(initial_intent="please split up methods into reusable code fragments",
                       starting_file=str(rel_file_path))
    print(output)

    source_code = server.call_tool_get("get_source_code")



def test_ghidra_12(mocker):

    plan = """To refactor the PDB symbol server property 'remote' to 'untrusted' in the given file, follow these actionable steps:

### Step-by-Step Refactoring Plan

1. **Identify the Property Definition**:
   - Open `PdbAnalyzer.java` in your code editor.
   - Locate the definition of the 'remote' property. This is usually found in a static property declaration or as part of the constructor where properties are initialized.

2. **Rename the Property**:
   - Change the property name from `remote` to `untrusted`. Update any annotations if present.
   - Example:
     ```java
     @Option(
         description = "PDB symbol server URL (untrusted)",
         // other parameters...
     )
     private String untrusted; // Previously remote
     ```

3. **Update References in the Class**:
   - Conduct a search within `PdbAnalyzer.java` for occurrences of `remote`. Update each occurrence to reference the new property name `untrusted`.
   - This includes:
     - Method parameters
     - Local variables
     - Any method calls that utilize this property
     - Comments if they mention 'remote'

4. **Adjust Method Parameters**:
   - If there are methods that accept `remote` as a parameter, change the parameter name to `untrusted`.
   - Example:
     ```java
     public void setSymbolServer(String untrusted) {
         // Use the new property name
     }
     ```

5. **Update Configuration Processing Logic**:
   - If there is logic in the class responsible for retrieving or processing configuration values related to `remote`, modify it so that it references `untrusted`. This may include updating any default values or handling logic.

6. **Modify Any Documentation or Comments**:
   - Go through the class and update any relevant comments or documentation that mention the `remote` property to clarify that it has been refactored to `untrusted`. Ensure that any usage examples also reflect the change.

7. **Test Existing Functionality**:
   - If there are unit tests or integration tests related to the PDB functionality, ensure that they are updated to accommodate the change from `remote` to `untrusted`. Adjust any test data or expected results accordingly.
   - If there are no tests covering this functionality, consider writing new tests to ensure the refactor maintains the expected behavior.

8. **Code Review**:
   - After making the changes, submit your code for review to ensure that it meets the new naming conventions and does not break existing functionality.

9. **Final Cleanup**:
   - After obtaining feedback from the code review, make any necessary adjustments and finalize the changes.
   - Run the complete test suite to confirm that everything is functioning correctly after the refactor.

By following this plan step-by-step, you will successfully refactor the 'remote' property to 'untrusted' in the `PdbAnalyzer.java` file."""

    # initialize repo.
    project = pm.EvalProject('ghidra')
    project.checkout('21d433b26c9d68a585d3c8956cb87b1e3929aed1')

    # create IJ server connection
    server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    server.open_project(project_path=project.get_project_path())
    rel_file_path = Path("Ghidra/Features/PDB/src/main/java/ghidra/app/plugin/core/analysis/PdbAnalyzer.java")
    server.open_file(rel_file_path)
    # server.reload_project()

    planning_patch = mocker.patch('refagent.agents.refactrix.planning.NaivePlanningComponent.run')
    planning_patch.return_value = AIMessage(content=plan)
    # create agent
    agent = ra.Agent(ide_server=server, model_name='grazie:openai-gpt-4o-mini')
    output = agent.run(initial_intent="refactor pdb symbol server 'remote' to 'untrusted'. "
                                      "Change name of symbolserver 'remote' property to 'untrusted' "
                                      "to reflect its intended usage.",
                       starting_file=str(rel_file_path))
    print(output)

    source_code = server.call_tool_get("get_source_code")
    print(source_code)
    print(agent.get_trajectory())


def test_flink_4():
    project = pm.EvalProject('flink')
    project.checkout('cdf314d30b59994283e0bbf70f350618de02118c')

    # create IJ server connection
    server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    server.open_project(project_path=project.get_project_path())
    rel_file_path = Path("flink-runtime/src/main/java/org/apache/"
                         "flink/runtime/io/network/partition/BufferWithChannel.java")
    server.open_file(rel_file_path)

    # create agent
    agent = ra.Agent(ide_server=server, model_name='grazie:openai-gpt-4o-mini')
    output = agent.run(initial_intent="Distinguish between channel and subpartition, by renaming appropriate elements",
                       starting_file=str(rel_file_path))
    print(output)

    source_code = server.call_tool_get("get_source_code")
    print(source_code)
    print(agent.get_trajectory())


def test_flink_16():
    project = pm.EvalProject('flink')
    project.checkout('4cce1bffb8160d2bfe64a4fb26172fc639e26dc1')

    # create IJ server connection
    server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    server.open_project(project_path=project.get_project_path())
    rel_file_path = Path("flink-runtime/src/test/java/org/apache/"
                         "flink/runtime/taskexecutor/slot/TaskSlotTableImplTest.java")
    server.open_file(rel_file_path)

    # create agent
    agent = ra.Agent(ide_server=server, model_name='grazie:openai-gpt-4o-mini')
    output = agent.run(initial_intent="Refactors test to use proper Executor service for the main thread",
                       starting_file=str(rel_file_path))
    print(output)

    source_code = server.call_tool_get("get_source_code")
    print(source_code)
    print(agent.get_trajectory())

def test_flink_2(mocker):
    # This one requires multi file editing.

    plan = planning.RefactoringPlan(
        steps=[
            planning.PlanningStep(reason='To create an interface for TaskInfo, by extracting common fragments from it.',
                                  refactoring_type='Introduce Interface',
                                  file_path='flink-core/src/main/java/org/apache/flink/api/common/TaskInfo.java',
                                  final_code='public interface TaskInfo {\n    // define methods specific to task information\n}\n'),
            # planning.PlanningStep(reason='To ensure TaskInfo has a clear implementation for common task attributes',
            #                       refactoring_type='Implement Default Class',
            #                       file_path='flink-core/src/main/java/org/apache/flink/api/common/TaskInfo.java',
            #                       final_code='public class DefaultTaskInfo implements TaskInfo {\n    // implementation of the methods defined in TaskInfo\n}\n'),
            planning.PlanningStep(
                reason='To provide a contract for job-related information and better future extensibility',
                refactoring_type='Introduce Interface',
                file_path='flink-core/src/main/java/org/apache/flink/api/common/JobInfo.java',
                final_code='public interface JobInfo {\n    // define methods specific to job information\n}\n'),
            planning.PlanningStep(
                reason='To create a concrete class that fulfills the contract of JobInfo',
                refactoring_type='Implement Default Class',
                file_path='flink-core/src/main/java/org/apache/flink/api/common/DefaultJobInfo.java',
                final_code='public class DefaultJobInfo implements JobInfo {\n    // implementation of the methods defined in JobInfo\n}\n')
        ]
    )
    planning_patch = mocker.patch('refagent.agents.refactrix.planning.NaivePlanningComponent.run')
    planning_patch.return_value = plan


    project = pm.EvalProject('flink')
    project.checkout('1d15930275545f16a94d19c4a9b67043d5667498')

    # create IJ server connection
    server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    server.open_project(project_path=project.get_project_path())
    rel_file_path = Path("flink-core/src/main/java/org/apache/flink/api/common/TaskInfo.java")
    server.open_file(rel_file_path)

    # create agent
    agent = ra.Agent(ide_server=server, model_name='grazie:openai-gpt-4o-mini')
    output = agent.run(initial_intent="Introduce the interface and default implementation of JobInfo and TaskInfo",
                       starting_file=str(rel_file_path))
    print(output)

    source_code = server.call_tool_get("get_source_code")
    print(source_code)
    print(agent.get_trajectory())



def test_kafka_155():
    # The source file is so large that it wouldn't fit in the context window.
    # Need to write a component that summarizes the code
    # initialize repo.
    project = pm.EvalProject('kafka')
    project.checkout('be6653c8bc25717e25a7db164527635a6579b4cc')

    # create IJ server connection
    server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    server.open_project(project_path=project.get_project_path())
    rel_file_path = Path("group-coordinator/src/test/java/org/apache/"
                         "kafka/coordinator/group/GroupMetadataManagerTest.java")
    server.open_file(rel_file_path)

    # create agent
    agent = ra.Agent(ide_server=server, model_name='grazie:openai-gpt-4o-mini')
    output = agent.run(initial_intent="`GroupMetadataManagerTest` class got a little under control. "
                                      "We have too many things defined in it.",
                       starting_file=str(rel_file_path))
    print(output)

    source_code = server.call_tool_get("get_source_code")



def test_kafka_99():

    project = pm.EvalProject('kafka')
    project.checkout('b31aa651156fbc961fbb8460604393fef1c09185')

    # create IJ server connection
    server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    server.open_project(project_path=project.get_project_path())
    rel_file_path = Path("streams/src/main/java/org/apache/"
                         "kafka/streams/kstream/internals/suppress/TimeDefinitions.java")
    server.open_file(rel_file_path)

    # create agent
    agent = ra.Agent(ide_server=server, model_name='grazie:openai-gpt-4o-mini')
    output = agent.run(initial_intent="Refactor TimeDefintiions to not use old ProcessorContext any longer",
                       starting_file=str(rel_file_path))
    print(output)

    source_code = server.call_tool_get("get_source_code")

