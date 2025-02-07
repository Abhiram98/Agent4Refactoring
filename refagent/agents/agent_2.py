from typing_extensions import Literal, TypedDict
from langchain_core.messages import HumanMessage, SystemMessage
from typing import Optional
from langgraph.graph import StateGraph, START, END
# from IPython.display import Image, display
from enum import Enum
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
import refagent
import os
from pathlib import Path
from pydantic.v1 import Field, BaseModel
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.graph import MessagesState
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage, AIMessage
import requests

os.environ["OPENAI_API_KEY"] = refagent.OPENAI_KEY
llm = ChatOpenAI(model="gpt-4o-mini")

iterations = 0


class SupportedRefactorings(Enum):
    EXTRACT_METHOD = "extract_method"
    RENAME = "rename"
    MOVE = "move"


class State(TypedDict):
    source_code: str
    suggestion: Optional[str]
    refactoring_tool: Optional[SupportedRefactorings]
    messages_state: MessagesState

def add_line_numbers(text):
    lines = text.split('\n')
    numbered_lines = [f"{i+1}: {line}" for i, line in enumerate(lines)]
    return '\n'.join(numbered_lines)


@tool
def extract_method(
        start_line: int = Field(description="Starting line of the code to be extracted into a new method."),
        end_line: int = Field(description="Ending line of the code to be extracted into a new method."),
        new_method_name: str = Field(description="the name of the extracted method")
):
    '''
    Extract a segment of the code [`start_line`, `end_line`] into a new method with the name `new_method_name`.
    Split up a large method into smaller ones. First, identify a method which is too large and performs too many functions.
    Next, find a block of code that can be split into a new method. Then, call this function.
    PASS ONLY the identified lines of code as argument - NOT the entire method.
    Ex:
    '''
    respose = requests.post('http://localhost:8082/extract-method',
                            json={'startLine': start_line, 'endLine': end_line, 'newName': new_method_name})
    if respose.ok:
        return "success"
    else:
        return "failed to extract the method." + respose.content.decode('utf-8')


@tool
def rename(
        old_name: str = Field(description="old/original name of the variable"),
        new_name: str = Field(description="new and better name for the same variable"),
        line_num: Optional[int] = Field(description="Line number to identify the variable", default=None)
):
    '''
    Rename a variable to a better, new name.
    '''
    line_num = line_num if isinstance(line_num, int) else None
    respose = requests.post('http://localhost:8082/rename',
                            json={'oldName': old_name, 'newName': new_name, 'lineNum': line_num})
    if respose.ok:
        return "success"
    else:
        return "failed to rename." + respose.content.decode('utf-8')


@tool
def move_method(
        method_name: str = Field(description="name of the method that needs to move"),
        target_class: str = Field(description="Class to which the method should move to")):
    '''
    Move the method `method_name` to a `target_class`, to improve the design of the software.
    Move a method only if it is better suited to be located in the `target_class`
    '''
    respose = requests.post('http://localhost:8082/move-method',
                            json={'methodName': method_name, 'target_class': target_class})
    if respose.ok:
        return "success"
    else:
        return "failed to move the method." + respose.content.decode('utf-8')


@tool
def choose_refactoring(
        refactoring_type: SupportedRefactorings = Field(description="select the type of refactoring"),
        reason: str = Field(description="explanation for why the refactoring should be carried out")
):
    """
    Select a refactoring action to perform and provide a reason.
    """
    global overall_state
    tools_by_name = {
        'extract_method': extract_method,
        'rename': rename,
        'move': move_method
    }
    tools = []
    print(refactoring_type)
    if refactoring_type == SupportedRefactorings.EXTRACT_METHOD:
        tools.append(extract_method)
    elif refactoring_type == SupportedRefactorings.RENAME:
        tools.append(rename)
    elif refactoring_type == SupportedRefactorings.MOVE:
        tools.append(move_method)
    else:
        raise Exception("Unknown refactoring type.")
    print(reason)
    llm_with_tools = llm.bind_tools(tools)

    # response = llm_with_tools.invoke()

    def llm_call(state: MessagesState):
        """LLM decides whether to call a tool or not"""

        return {
            "messages": [
                llm_with_tools.invoke(
                    # [
                    #     SystemMessage(
                    #         content="You are a helpful assistant tasked with performing arithmetic on a set of inputs."
                    #     )
                    # ]
                    state["messages"]
                )
            ]
        }

    def tool_node(state: dict):
        """Performs the tool call"""

        result = []
        for tool_call in state["messages"][-1].tool_calls:
            tool = tools_by_name[tool_call["name"]]
            observation = tool.invoke(tool_call["args"])
            result.append(ToolMessage(content=observation, tool_call_id=tool_call["id"]))
        return {"messages": result}

    def should_continue(state: MessagesState) -> Literal["environment", END]:
        """Decide if we should continue the loop or stop based upon whether the LLM made a tool call"""

        messages = state["messages"]
        last_message = messages[-1]
        # If the LLM makes a tool call, then perform an action
        if last_message.tool_calls:
            return "Action"
        # Otherwise, we stop (reply to the user)
        return END

    agent_builder = StateGraph(MessagesState)

    # Add nodes
    agent_builder.add_node("llm_call", llm_call)
    agent_builder.add_node("environment", tool_node)

    # Add edges to connect nodes
    agent_builder.add_edge(START, "llm_call")
    agent_builder.add_conditional_edges(
        "llm_call",
        should_continue,
        {
            # Name returned by should_continue : Name of next node to visit
            "Action": "environment",
            END: END,
        },
    )
    agent_builder.add_edge("environment", "llm_call")

    # Compile the agent
    agent = agent_builder.compile()
    previous_messages = overall_state["messages_state"]['messages'][:-1]
    messages = (previous_messages +
                [
                    AIMessage(reason),
                    HumanMessage(content="Please call the refactoring tools to perform the changes. "
                                      "In case the tool fails, you may choose to retry")])
    messages = agent.invoke({"messages": messages})

    return messages['messages'][-1] # return the last message, to summarize the actions of the tool calls.


# Nodes
def select_refactoring(state: State):
    """First LLM call to generate refactoring ideas"""
    # llm.bind_tools()
    global iterations
    file_path = "/Users/abhiram/Documents/TBE/evaluation_projects/selenium/java/src/org/openqa/selenium/firefox/FirefoxDriver.java"
    with open(file_path) as f:
        source_code = add_line_numbers(f.read())
    llm_with_tools = llm.bind_tools([choose_refactoring])
    extra_message = "" if iterations == 0 else "Here's the modified source code: \n"
    new_messages = state["messages_state"]['messages'] + [HumanMessage(content=extra_message + source_code)]

    response = llm_with_tools.invoke(
        new_messages
    )
    iterations += 1
    new_messages.append(response)
    return {
        "messages_state": {"messages": new_messages},
        "source_code": source_code
    }


# def tool_node(state: dict):
#     """Performs the tool call"""
#     tools_by_name = {}
#     result = []
#     for tool_call in state["messages"][-1].tool_calls:
#         tool = tools_by_name[tool_call["name"]]
#         observation = tool.invoke(tool_call["args"])
#         result.append(ToolMessage(content=observation, tool_call_id=tool_call["id"]))
#     return {"messages": result}


def any_refactoring(state: State) -> bool:
    """Check if there are any refactoring suggestions in this message"""
    # Simple check. Is the LLM telling us to stop or not.
    messages = state["messages_state"]["messages"]
    last_message = messages[-1]
    # If the LLM makes a tool call, then perform an action
    if last_message.tool_calls:
        return True
    # Otherwise, we stop (reply to the user)
    return False


def perform_refactoring(state: State):
    """Perform refactoring in retry loop"""
    # invoke LLM with tool.
    """Performs the tool call"""
    # tools_by_name = {"choose_refactoring": choose_refactoring}
    result = []
    for tool_call in state["messages_state"]["messages"][-1].tool_calls:
        tool = choose_refactoring
        global overall_state
        overall_state = state
        observation = tool.invoke(tool_call["args"])
        result.append(ToolMessage(content=observation.content, tool_call_id=tool_call["id"]))
    messages = state["messages_state"]["messages"]
    messages += result
    return {"messages_state": {"messages": messages}}


# def refactoring_success(state: State):
#     """Third LLM call for final polish"""
#
#     return "SUCCESS" if state['tool_status'] else "FAIL"


class Agent(BaseModel):
    file_path: Path = Field(description="path to the file to be refactored.")
    state: State = Field(description="state of the agent")

    def __init__(self, *args, **kwargs):
        super().__init__(args, kwargs)
        self.workflow = StateGraph(State)

    def build_workflow(self):
        self.workflow.add_node("select_refactoring", select_refactoring)
        self.workflow.add_node("perform_refactoring", perform_refactoring)

    def refresh_file_contents(self):
        with open(self.file_path) as f:
            self.state['source_code'] = add_line_numbers(f.read())


if __name__ == '__main__':
    # Build workflow
    workflow = StateGraph(State)

    # Add nodes
    workflow.add_node("select_refactoring", select_refactoring)
    workflow.add_node("perform_refactoring", perform_refactoring)

    # Add edges to connect nodes
    workflow.add_edge(START, "select_refactoring")
    workflow.add_conditional_edges(
        "select_refactoring", any_refactoring, {True: "perform_refactoring", False: END}
    )
    # workflow.add_conditional_edges(
    #     "perform_refactoring", refactoring_success,
    #     {"YES": "select_refactoring", "RETRY": "perform_refactoring", "STOP": "select_refactoring"}
    # )
    workflow.add_edge("perform_refactoring", "select_refactoring")

    # Compile
    chain = workflow.compile()

    # Show workflow
    # display(Image(chain.get_graph().draw_mermaid_png()))

    # Invoke
    file_path = "/Users/abhiram/Documents/TBE/evaluation_projects/selenium/java/src/org/openqa/selenium/firefox/FirefoxDriver.java"
    with open(file_path) as f:
        source_code = f.read()
    overall_state: State = {
        "source_code": source_code,
        "refactoring_tool": None,
        "suggestion": None,
        "messages_state":
            {
                "messages": [SystemMessage(content="You are a helpful assistant who suggests changes to "
                                                   "improve the quality of the given code.")]
            }
    }
    state = chain.invoke(overall_state)
    # print("Initial joke:")
    # print(state["joke"])
    # print("\n--- --- ---\n")
    # if "improved_joke" in state:
    #     print("Improved joke:")
    #     print(state["improved_joke"])
    #     print("\n--- --- ---\n")
    #
    #     print("Final joke:")
    #     print(state["final_joke"])
    # else:
    #     print("Joke failed quality gate - no punchline detected!")
