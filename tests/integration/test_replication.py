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


def test_flink_4(mocker):
    '''Renaming channel to subpartition'''
    project = pm.EvalProject('flink')
    project.checkout('c4b51d92ad4', force=True)
    project.reset_head()

    plan = planning.RefactoringPlan(
        steps=[
            {
                    "reason": "To improve clarity and maintainability of the code by using a more appropriate term.",
                    "final_code": "public class SortBufferAccumulator implements BufferAccumulator {\n    /** The number of the subpartitions. */\n    private final int numSubpartitions;\n    /** The total number of the buffers used by the {@link SortBufferAccumulator}. */\n    private final int numBuffers;\n    /** The byte size of one single buffer. */\n    private final int bufferSizeBytes;\n    /** The empty buffers without storing data. */\n    private final LinkedList<MemorySegment> freeSegments = new LinkedList<>();\n    /** The memory manager of the tiered storage. */\n    private final TieredStorageMemoryManager memoryManager;\n    @Nullable private DataBuffer currentDataBuffer;\n    @Nullable private BufferRecycler bufferRecycler;\n    @Nullable private BiConsumer<TieredStorageSubpartitionId, List<Buffer>> accumulatedBufferFlusher;\n    private boolean isBroadcastDataBuffer;\n    public SortBufferAccumulator(\n            int numSubpartitions,\n            int numBuffers,\n            int bufferSizeBytes,\n            TieredStorageMemoryManager memoryManager) {\n        this.numSubpartitions = numSubpartitions;\n        this.bufferSizeBytes = bufferSizeBytes;\n        this.numBuffers = numBuffers;\n        this.memoryManager = memoryManager;\n    }\n    @Override\n    public void setup(BiConsumer<TieredStorageSubpartitionId, List<Buffer>> bufferFlusher) {\n        this.accumulatedBufferFlusher = bufferFlusher;\n    }\n    @Override\n    public void receive(\n            ByteBuffer record,\n            TieredStorageSubpartitionId subpartitionId,\n            Buffer.DataType dataType,\n            boolean isBroadcast)\n            throws IOException {\n        int targetSubpartition = subpartitionId.getSubpartitionId();\n        switchCurrentDataBufferIfNeeded(isBroadcast);\n        if (!checkNotNull(currentDataBuffer).append(record, targetSubpartition, dataType)) {\n            return;\n        }\n        if (!currentDataBuffer.hasRemaining()) {\n            currentDataBuffer.release();\n            writeLargeRecord(record, targetSubpartition, dataType);\n            return;\n        }\n        flushDataBuffer();\n        checkState(record.hasRemaining(), \"Empty record.\");\n        receive(record, subpartitionId, dataType, isBroadcast);\n    }\n    @Override\n    public void close() {\n        flushCurrentDataBuffer();\n        releaseFreeBuffers();\n        if (currentDataBuffer != null) {\n            currentDataBuffer.release();\n        }\n    }\n    private void switchCurrentDataBufferIfNeeded(boolean isBroadcast) {\n        if (isBroadcast == isBroadcastDataBuffer\n                && currentDataBuffer != null\n                && !currentDataBuffer.isReleased()\n                && !currentDataBuffer.isFinished()) {\n            return;\n        }\n        isBroadcastDataBuffer = isBroadcast;\n        flushCurrentDataBuffer();\n        currentDataBuffer = createNewDataBuffer();\n    }\n    private DataBuffer createNewDataBuffer() {\n        requestBuffers();\n        int numBuffersForSort = freeSegments.size() / 2;\n        return new TieredStorageSortBuffer(\n                freeSegments,\n                this::recycleBuffer,\n                numSubpartitions,\n                bufferSizeBytes,\n                numBuffersForSort);\n    }\n    private void requestBuffers() {\n        while (freeSegments.size() < numBuffers) {\n            Buffer buffer = requestBuffer();\n            freeSegments.add(checkNotNull(buffer).getMemorySegment());\n            if (bufferRecycler == null) {\n                bufferRecycler = buffer.getRecycler();\n            }\n        }\n    }\n    private void flushDataBuffer() {\n        if (currentDataBuffer == null || currentDataBuffer.isReleased() || !currentDataBuffer.hasRemaining()) {\n            return;\n        }\n        currentDataBuffer.finish();\n        do {\n            MemorySegment freeSegment = getFreeSegment();\n            BufferWithChannel bufferWithChannel = currentDataBuffer.getNextBuffer(freeSegment);\n            if (bufferWithChannel == null) {\n                break;\n            }\n            flushBuffer(bufferWithChannel);\n        } while (true);\n        releaseFreeBuffers();\n        currentDataBuffer.release();\n    }\n    private void flushCurrentDataBuffer() {\n        if (currentDataBuffer != null) {\n            flushDataBuffer();\n            currentDataBuffer = null;\n        }\n    }\n    private void writeLargeRecord(ByteBuffer record, int subpartitionId, Buffer.DataType dataType) {\n        checkState(dataType != Buffer.DataType.EVENT_BUFFER);\n        while (record.hasRemaining()) {\n            int toCopy = Math.min(record.remaining(), bufferSizeBytes);\n            MemorySegment writeBuffer = requestBuffer().getMemorySegment();\n            writeBuffer.put(0, record, toCopy);\n            flushBuffer(\n                    new BufferWithChannel(\n                            new NetworkBuffer(\n                                    writeBuffer, checkNotNull(bufferRecycler), dataType, toCopy),\n                            subpartitionId));\n        }\n        releaseFreeBuffers();\n    }\n    private MemorySegment getFreeSegment() {\n        MemorySegment freeSegment = freeSegments.poll();\n        if (freeSegment == null) {\n            freeSegment = requestBuffer().getMemorySegment();\n        }\n        return freeSegment;\n    }\n    private void flushBuffer(BufferWithChannel bufferWithChannel) {\n        checkNotNull(accumulatedBufferFlusher)\n                .accept(\n                        new TieredStorageSubpartitionId(bufferWithChannel.getChannelIndex()),\n                        Collections.singletonList(bufferWithChannel.getBuffer()));\n    }\n    private Buffer requestBuffer() {\n        BufferBuilder bufferBuilder = memoryManager.requestBufferBlocking(this);\n        BufferConsumer bufferConsumer = bufferBuilder.createBufferConsumerFromBeginning();\n        Buffer buffer = bufferConsumer.build();\n        bufferBuilder.close();\n        bufferConsumer.close();\n        return buffer;\n    }\n    private void releaseFreeBuffers() {\n        freeSegments.forEach(this::recycleBuffer);\n        freeSegments.clear();\n    }\n    private void recycleBuffer(MemorySegment memorySegment) {\n        checkNotNull(bufferRecycler).recycle(memorySegment);\n    }\n}",
                    "execution_details": "Rename the class 'SortBufferAccumulator' to 'SubpartitionBufferAccumulator' and all instances of 'channel' to 'subpartition' in the class and its methods. Update all references to this class in related files to ensure consistency.",
                    "refactoring_type": "rename",
                    "file_path": "flink-runtime/src/main/java/org/apache/flink/runtime/io/network/partition/hybrid/tiered/storage/SortBufferAccumulator.java"
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
    rel_file_path = Path("flink-runtime/src/main/java/org/apache/flink/runtime/"
                         "io/network/partition/hybrid/tiered/storage/SortBufferAccumulator.java")
    server.open_file(rel_file_path)

    # create agent
    with ls.trace(name=f"refactoring agent test - test_replication:test_flink_4",
                  tags=["test"]) as tracer:
        agent = ra.Agent(ide_server=server, model_name='grazie:openai-gpt-4o-mini', project=project)
        output = agent.run(initial_intent="Rename the concept channel to subpartition. "
                                          "Rename variables, parameters, fields, classes.",
                           starting_file=str(rel_file_path))
    print(output)

    source_code = server.call_tool_get("get_source_code")
    print(source_code)
    print(agent.get_trajectory())
