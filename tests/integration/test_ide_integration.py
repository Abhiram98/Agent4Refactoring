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