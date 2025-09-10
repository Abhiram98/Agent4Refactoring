import json

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
import refagent.agents.refactrix.supported_refactorings as sup_ref

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

    # plan = planning.RefactoringPlan(steps=[planning.PlanningStep(
    #     reason='The TaskInfo interface should provide comprehensive information about task properties. Additional methods such as getTaskId(), getParallelism(), and getJobId() would enhance its utility and allow for better integration with other components in the system. Furthermore, adding JavaDoc comments for each method will improve code readability and maintainability.',
    #     final_code='package org.apache.flink.api.common;\n\n/**\n * Represents information about a task in the Flink framework.\n */\npublic interface TaskInfo {\n    /**\n     * Gets the name of the task.\n     * @return the name of the task\n     */\n    String getTaskName();\n\n    /**\n     * Gets the index of the task.\n     * @return the index of the task\n     */\n    int getTaskIndex();\n\n    /**\n     * Gets the unique identifier for the task.\n     * @return the task ID\n     */\n    String getTaskId();\n\n    /**\n     * Gets the parallelism level of the task.\n     * @return the parallelism level\n     */\n    int getParallelism();\n\n    /**\n     * Gets the unique identifier for the job associated with the task.\n     * @return the job ID\n     */\n    String getJobId();\n}',
    #     refactoring_type=sup_ref.SupportedRefactorings.EXTRACT_CLASS,
    #     file_path='flink-core/src/main/java/org/apache/flink/api/common/TaskInfo.java'), planning.PlanningStep(
    #     reason='The implementation of the TaskInfo interface is incomplete as it does not include the additional methods for task ID, parallelism, and job ID. These methods are essential to provide a full implementation of the TaskInfo interface. Additionally, proper JavaDoc comments should be added for better documentation and code readability.',
    #     final_code='package org.apache.flink.api.common;\n\n/**\n * Implementation of the TaskInfo interface, providing details about a task in the Flink framework.\n */\npublic class TaskInfoImpl implements TaskInfo {\n    private final String taskName;\n    private final int taskIndex;\n    private final String taskId;\n    private final int parallelism;\n    private final String jobId;\n\n    public TaskInfoImpl(String taskName, int taskIndex, String taskId, int parallelism, String jobId) {\n        this.taskName = taskName;\n        this.taskIndex = taskIndex;\n        this.taskId = taskId;\n        this.parallelism = parallelism;\n        this.jobId = jobId;\n    }\n\n    @Override\n    public String getTaskName() {\n        return taskName;\n    }\n\n    @Override\n    public int getTaskIndex() {\n        return taskIndex;\n    }\n\n    @Override\n    public String getTaskId() {\n        return taskId;\n    }\n\n    @Override\n    public int getParallelism() {\n        return parallelism;\n    }\n\n    @Override\n    public String getJobId() {\n        return jobId;\n    }\n}',
    #     refactoring_type=sup_ref.SupportedRefactorings.EXTRACT_CLASS,
    #     file_path='flink-core/src/main/java/org/apache/flink/api/common/TaskInfo.java'), planning.PlanningStep(
    #     reason='The JobInfo interface should provide comprehensive information about job properties. Additional methods such as getJobStatus(), getJobStartTime(), and getJobEndTime() would enhance its utility and allow for better interaction with other components in the system. Furthermore, adding JavaDoc comments for each method will improve code readability and maintainability.',
    #     final_code='package org.apache.flink.api.common;\n\n/**\n * Represents information about a job in the Flink framework.\n */\npublic interface JobInfo {\n    /**\n     * Gets the name of the job.\n     * @return the name of the job\n     */\n    String getJobName();\n\n    /**\n     * Gets the unique identifier for the job.\n     * @return the job ID\n     */\n    String getJobId();\n\n    /**\n     * Gets the current status of the job.\n     * @return the status of the job\n     */\n    String getJobStatus();\n\n    /**\n     * Gets the start time of the job.\n     * @return the start time in milliseconds since epoch\n     */\n    long getJobStartTime();\n\n    /**\n     * Gets the end time of the job.\n     * @return the end time in milliseconds since epoch\n     */\n    long getJobEndTime();\n}',
    #     refactoring_type=sup_ref.SupportedRefactorings.EXTRACT_CLASS,
    #     file_path='flink-core/src/main/java/org/apache/flink/api/common/JobInfo.java'), planning.PlanningStep(
    #     reason="The implementation of the JobInfo interface is incomplete as it does not include methods for job status, start time, and end time. These methods are essential for providing a full representation of a job's information. Additionally, JavaDoc comments should be added to improve documentation and code readability.",
    #     final_code='package org.apache.flink.api.common;\n\n/**\n * Implementation of the JobInfo interface, providing details about a job in the Flink framework.\n */\npublic class JobInfoImpl implements JobInfo {\n    private final String jobName;\n    private final String jobId;\n    private final String jobStatus;\n    private final long jobStartTime;\n    private final long jobEndTime;\n\n    public JobInfoImpl(String jobName, String jobId, String jobStatus, long jobStartTime, long jobEndTime) {\n        this.jobName = jobName;\n        this.jobId = jobId;\n        this.jobStatus = jobStatus;\n        this.jobStartTime = jobStartTime;\n        this.jobEndTime = jobEndTime;\n    }\n\n    @Override\n    public String getJobName() {\n        return jobName;\n    }\n\n    @Override\n    public String getJobId() {\n        return jobId;\n    }\n\n    @Override\n    public String getJobStatus() {\n        return jobStatus;\n    }\n\n    @Override\n    public long getJobStartTime() {\n        return jobStartTime;\n    }\n\n    @Override\n    public long getJobEndTime() {\n        return jobEndTime;\n    }\n}',
    #     refactoring_type=sup_ref.SupportedRefactorings.EXTRACT_CLASS,
    #     file_path='flink-core/src/main/java/org/apache/flink/api/common/JobInfo.java')])
    # plan = planning.RefactoringPlan(steps=[planning.PlanningStep(
    #     reason='To define a contract for task-specific information that can be used by multiple implementations, and to ensure that the interface includes appropriate documentation and potential default methods for future extensibility.',
    #     final_code='public interface TaskInfo {\n    /**\n     * Returns the name of the task.\n     * @return The name of the task.\n     */\n    String getTaskName();\n\n    /**\n     * Gets the maximum number of parallel subtasks.\n     * @return The max number of parallel subtasks.\n     */\n    int getMaxNumberOfParallelSubtasks();\n\n    /**\n     * Gets the index of this parallel subtask.\n     * @return The index of the parallel subtask.\n     */\n    int getIndexOfThisSubtask();\n\n    /**\n     * Gets the number of parallel subtasks.\n     * @return The number of parallel subtasks.\n     */\n    int getNumberOfParallelSubtasks();\n\n    /**\n     * Gets the attempt number of this parallel subtask.\n     * @return The attempt number of the subtask.\n     */\n    int getAttemptNumber();\n\n    /**\n     * Returns the name of the task, appended with the subtask indicator.\n     * @return The name of the task, with subtask indicator.\n     */\n    String getTaskNameWithSubtasks();\n\n    /**\n     * Returns the allocation ID for where this task is executed.\n     * @return The allocation ID for where this task is executed.\n     */\n    String getAllocationIDAsString();\n\n    /**\n     * A default method to get a formatted string representation of the task info.\n     * @return A string representation of the task info.\n     */\n    default String toString() {\n        return getTaskNameWithSubtasks() + " (Max: " + getMaxNumberOfParallelSubtasks() + ")";\n    }\n}',
    #     refactoring_type=sup_ref.SupportedRefactorings.EXTRACT_CLASS,
    #     file_path='flink-core/src/main/java/org/apache/flink/api/common/TaskInfo.java'), planning.PlanningStep(
    #     reason='To ensure that the TaskInfoImpl class properly implements the TaskInfo interface, including a constructor and all necessary methods that align with the interface contract.',
    #     final_code='public class TaskInfoImpl implements TaskInfo {\n    private final String taskName;\n    private final String taskNameWithSubtasks;\n    private final String allocationIDAsString;\n    private final int maxNumberOfParallelSubtasks;\n    private final int indexOfSubtask;\n    private final int numberOfParallelSubtasks;\n    private final int attemptNumber;\n\n    public TaskInfoImpl(\n            String taskName,\n            int maxNumberOfParallelSubtasks,\n            int indexOfSubtask,\n            int numberOfParallelSubtasks,\n            int attemptNumber,\n            String allocationIDAsString) {\n        this.taskName = checkNotNull(taskName, "Task Name must not be null.");\n        this.maxNumberOfParallelSubtasks = maxNumberOfParallelSubtasks;\n        this.indexOfSubtask = indexOfSubtask;\n        this.numberOfParallelSubtasks = numberOfParallelSubtasks;\n        this.attemptNumber = attemptNumber;\n        this.allocationIDAsString = checkNotNull(allocationIDAsString);\n        this.taskNameWithSubtasks = taskName + " (" + (indexOfSubtask + 1) + \'/\' + numberOfParallelSubtasks + ")#" + attemptNumber;\n    }\n\n    @Override\n    public String getTaskName() {\n        return this.taskName;\n    }\n\n    @Override\n    public int getMaxNumberOfParallelSubtasks() {\n        return maxNumberOfParallelSubtasks;\n    }\n\n    @Override\n    public int getIndexOfThisSubtask() {\n        return this.indexOfSubtask;\n    }\n\n    @Override\n    public int getNumberOfParallelSubtasks() {\n        return this.numberOfParallelSubtasks;\n    }\n\n    @Override\n    public int getAttemptNumber() {\n        return this.attemptNumber;\n    }\n\n    @Override\n    public String getTaskNameWithSubtasks() {\n        return this.taskNameWithSubtasks;\n    }\n\n    @Override\n    public String getAllocationIDAsString() {\n        return allocationIDAsString;\n    }\n}',
    #     refactoring_type=sup_ref.SupportedRefactorings.EXTRACT_CLASS,
    #     file_path='flink-core/src/main/java/org/apache/flink/api/common/TaskInfoImpl.java'), planning.PlanningStep(
    #     reason='To ensure that the existing implementation is decoupled from the old class and adheres to the new interface, the implementation should be modified to implement the TaskInfo interface directly, rather than extending it. This will prevent any confusion with the original TaskInfo class and ensure that the new TaskInfoImpl class stands alone with its own implementation.',
    #     final_code='public class TaskInfoImpl implements TaskInfo {\n    private final String taskName;\n    private final String taskNameWithSubtasks;\n    private final String allocationIDAsString;\n    private final int maxNumberOfParallelSubtasks;\n    private final int indexOfSubtask;\n    private final int numberOfParallelSubtasks;\n    private final int attemptNumber;\n\n    public TaskInfoImpl(\n            String taskName,\n            int maxNumberOfParallelSubtasks,\n            int indexOfSubtask,\n            int numberOfParallelSubtasks,\n            int attemptNumber,\n            String allocationIDAsString) {\n        this.taskName = checkNotNull(taskName, "Task Name must not be null.");\n        this.maxNumberOfParallelSubtasks = maxNumberOfParallelSubtasks;\n        this.indexOfSubtask = indexOfSubtask;\n        this.numberOfParallelSubtasks = numberOfParallelSubtasks;\n        this.attemptNumber = attemptNumber;\n        this.allocationIDAsString = checkNotNull(allocationIDAsString);\n        this.taskNameWithSubtasks = taskName + " (" + (indexOfSubtask + 1) + \'/\'+ numberOfParallelSubtasks + ")#" + attemptNumber;\n    }\n\n    @Override\n    public String getTaskName() {\n        return this.taskName;\n    }\n\n    @Override\n    public int getMaxNumberOfParallelSubtasks() {\n        return maxNumberOfParallelSubtasks;\n    }\n\n    @Override\n    public int getIndexOfThisSubtask() {\n        return this.indexOfSubtask;\n    }\n\n    @Override\n    public int getNumberOfParallelSubtasks() {\n        return this.numberOfParallelSubtasks;\n    }\n\n    @Override\n    public int getAttemptNumber() {\n        return this.attemptNumber;\n    }\n\n    @Override\n    public String getTaskNameWithSubtasks() {\n        return this.taskNameWithSubtasks;\n    }\n\n    @Override\n    public String getAllocationIDAsString() {\n        return allocationIDAsString;\n    }\n}',
    #     refactoring_type=sup_ref.SupportedRefactorings.MOVE,
    #     file_path='flink-core/src/main/java/org/apache/flink/api/common/TaskInfoImpl.java')])
    plan = planning.RefactoringPlan(
        steps=[
            planning.PlanningStep(
                reason='To enhance the usability and maintainability of the DefaultTaskInfo class, we should implement validation for the constructor parameters and provide a toString() method for better debugging.',
                final_code='package org.apache.flink.api.common;\n\npublic class DefaultTaskInfo implements TaskInfo {\n    private final String taskName;\n    private final int maxNumberOfParallelSubtasks;\n    private final int indexOfThisSubtask;\n    private final int numberOfParallelSubtasks;\n    private final int attemptNumber;\n    private final String allocationID;\n\n    public DefaultTaskInfo(String taskName, int maxNumberOfParallelSubtasks, int indexOfThisSubtask, int numberOfParallelSubtasks, int attemptNumber, String allocationID) {\n        if (taskName == null || allocationID == null) {\n            throw new IllegalArgumentException("taskName and allocationID cannot be null");\n        }\n        if (maxNumberOfParallelSubtasks <= 0 || numberOfParallelSubtasks <= 0 || indexOfThisSubtask < 0 || indexOfThisSubtask >= numberOfParallelSubtasks) {\n            throw new IllegalArgumentException("Invalid subtask parameters");\n        }\n        this.taskName = taskName;\n        this.maxNumberOfParallelSubtasks = maxNumberOfParallelSubtasks;\n        this.indexOfThisSubtask = indexOfThisSubtask;\n        this.numberOfParallelSubtasks = numberOfParallelSubtasks;\n        this.attemptNumber = attemptNumber;\n        this.allocationID = allocationID;\n    }\n\n    @Override\n    public String getTaskName() {\n        return taskName;\n    }\n\n    @Override\n    public int getMaxNumberOfParallelSubtasks() {\n        return maxNumberOfParallelSubtasks;\n    }\n\n    @Override\n    public int getIndexOfThisSubtask() {\n        return indexOfThisSubtask;\n    }\n\n    @Override\n    public int getNumberOfParallelSubtasks() {\n        return numberOfParallelSubtasks;\n    }\n\n    @Override\n    public int getAttemptNumber() {\n        return attemptNumber;\n    }\n\n    @Override\n    public String getTaskNameWithSubtasks() {\n        return taskName + " (" + indexOfThisSubtask + "/" + numberOfParallelSubtasks + ")";\n    }\n\n    @Override\n    public String getAllocationIDAsString() {\n        return allocationID;\n    }\n\n    @Override\n    public String toString() {\n        return "DefaultTaskInfo{" +\n                "taskName=\'" + taskName + \'\'\' +\n                ", maxNumberOfParallelSubtasks=" + maxNumberOfParallelSubtasks +\n                ", indexOfThisSubtask=" + indexOfThisSubtask +\n                ", numberOfParallelSubtasks=" + numberOfParallelSubtasks +\n                ", attemptNumber=" + attemptNumber +\n                ", allocationID=\'" + allocationID + \'\'\' +\n                \'}\';\n    }\n}',
                file_path='flink-core/src/main/java/org/apache/flink/api/common/TaskInfo.java',
                refactoring_type=sup_ref.SupportedRefactorings.EXTRACT_CLASS
            )
        ]
    )
    planning_patch = mocker.patch('refagent.agents.refactrix.planning.PlanningComponent.run')
    planning_patch.return_value = plan


    project = pm.EvalProject('flink')
    project.checkout('1d15930275545f16a94d19c4a9b67043d5667498')

    # create IJ server connection
    server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)
    server.open_project(project_path=project.get_project_path())
    rel_file_path = Path("flink-core/src/main/java/org/apache/flink/api/common/TaskInfo.java")
    server.open_file(rel_file_path)

    # create agent
    agent = ra.Agent(ide_server=server, model_name='grazie:openai-gpt-4o-mini', project=project)
    # agent = ra.Agent(ide_server=server, model_name='grazie:anthropic-claude-3.5-haiku')
    output = agent.run(initial_intent="Introduce the interface and default implementation of TaskInfo",
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
    
    

def test_flink_4(mocker):
    planning.RefactoringPlan(steps = [
        planning.PlanningStep(reason='To clarify the purpose of the variable and avoid confusion with channels.',
                          final_code='private final int numSubpartitions;',
                          execution_details="Rename variable 'numSubpartitions' to 'numberOfSubpartitions' to enhance clarity. This change will involve replacing all occurrences of 'numSubpartitions' with 'numberOfSubpartitions' within the scope of the SortBufferAccumulator class.",
                          refactoring_type= sup_ref.SupportedRefactorings.RENAME, file_path = 'flink-runtime/src/main/java/org/apache/flink/runtime/io/network/partition/hybrid/tiered/storage/SortBufferAccumulator.java'),
    planning.PlanningStep(
        reason='To ensure consistency in terminology throughout the code, making it clearer and easier to understand.',
        final_code='private boolean isBroadcastBuffer;',
        execution_details="Rename variable 'isBroadcastDataBuffer' to 'isBroadcastBuffer'. This will involve replacing all occurrences of 'isBroadcastDataBuffer' with 'isBroadcastBuffer' within the scope of the SortBufferAccumulator class. This change should be applied to the declaration on line 60 and any other references to this variable throughout the class.",
        refactoring_type= sup_ref.SupportedRefactorings.RENAME, file_path = 'flink-runtime/src/main/java/org/apache/flink/runtime/io/network/partition/hybrid/tiered/storage/SortBufferAccumulator.java'), 
    planning.PlanningStep(
        reason='To maintain clarity in method parameters and avoid confusion with channels by renaming the parameter for better understanding.',
        final_code='public void receive(ByteBuffer record, TieredStorageSubpartitionId subpartitionId, Buffer.DataType dataType, boolean isBroadcast) throws IOException',
        execution_details="Rename the parameter 'isBroadcast' to 'isBroadcastMode' to enhance clarity. This will involve replacing all occurrences of 'isBroadcast' with 'isBroadcastMode' within the scope of the receive method. The line number for the parameter declaration is 45.",
        refactoring_type= sup_ref.SupportedRefactorings.RENAME , file_path = 'flink-runtime/src/main/java/org/apache/flink/runtime/io/network/partition/hybrid/tiered/storage/SortBufferAccumulator.java'), 
    planning.PlanningStep(
        reason='To improve clarity and consistency in naming conventions.',
        final_code='flushBuffer(new BufferWithChannel(new NetworkBuffer(writeBuffer, checkNotNull(bufferRecycler), dataType, toCopy), subpartitionId));',
        execution_details="Rename the variable 'bufferWithChannel' to 'channelBuffer' for better clarity. This will involve replacing all occurrences of 'bufferWithChannel' with 'channelBuffer' within the scope of the flushBuffer method. The line number for the declaration is 112.",
        refactoring_type= sup_ref.SupportedRefactorings.RENAME, file_path = 'flink-runtime/src/main/java/org/apache/flink/runtime/io/network/partition/hybrid/tiered/storage/SortBufferAccumulator.java'),
    planning.PlanningStep(
        reason="To ensure that the comments accurately reflect the terminology used in the code, specifically updating references to 'numBuffers' to 'numberOfSubpartitions' for consistency.",
        final_code='The {@link SortBufferAccumulator} can help use fewer buffers to accumulate data, which decouples the buffer usage from the number of parallel tasks. The number of buffers used by the {@link SortBufferAccumulator} will be at most numberOfSubpartitions.',
        execution_details="Replace all occurrences of 'numBuffers' with 'numberOfSubpartitions' in the comments within the SortBufferAccumulator class, specifically in the comment block starting at line 25.",
        refactoring_type= sup_ref.SupportedRefactorings.RENAME, file_path = 'flink-runtime/src/main/java/org/apache/flink/runtime/io/network/partition/hybrid/tiered/storage/SortBufferAccumulator.java')]
    )


def test_code_inspection():
    project = pm.EvalProject('flink')
    project.checkout('1d15930275545f16a94d19c4a9b67043d5667498', force=True)
    server = ij.IntellijServer(server_url=refagent.IJ_SERVER_URL)

    server.open_project(project_path=project.get_project_path())
    response = server.open_file(Path("flink-core/src/main/java/org/apache/flink/api/common/TaskInfo.java"))
    print(response)
    # requests.post('http://localhost:8082/extract-class',
    #               json={'extraction_type': 'enum', 'new_class_name': 'MyEnum', 'members': ['serialVersionUID'],
    #                     "sub_class_name": "NotImportant"})
    extract_class_response = server.call_tool("extract-class",
                     extraction_type='interface',
                     new_class_name='TaskInfo',
                     members=['taskName', 'getTaskName'],
                     sub_class_name='TaskInfoImpl'
                     )
    print(extract_class_response)
    inspection_results = server.call_tool('run_code_inspection')
    print(inspection_results)
    print(json.loads(inspection_results))
