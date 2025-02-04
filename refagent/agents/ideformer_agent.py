import asyncio
import math
from argparse import ArgumentParser, BooleanOptionalAction
import requests

from ideformer.client.agents.simple_grazie_chat_v2_runner import (
    IdeFormerSimpleGrazieChatV2Runner,
)
from ideformer.client.client import IdeFormerClient
from ideformer.client.tools.langchain.implementation import (
    ToolImplementationProvider,
    tool_implementation,
)
from pydantic import Field

from ideformer.client.utils.logging import configure_client


class IntelliJToolImplementationProvider(ToolImplementationProvider):

    @tool_implementation()
    def rename(self,
                      old_name: str = Field(description="old/original name of the variable"),
                      new_name: str = Field(description="new and better name for the same variable")):
        '''
        Rename a variable to a better, new name.
        '''
        respose = requests.post('http://localhost:8082/rename',
                                json={'oldName':old_name, 'newName':new_name})
        if respose.ok:
            return "success"
        else:
            return "failed to rename." + respose.content.decode('utf-8')

    @tool_implementation()
    def extract_method(self,
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

    @tool_implementation()
    def move_method(self,
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



def add_line_numbers(text):
    lines = text.split('\n')
    numbered_lines = [f"{i+1}: {line}" for i, line in enumerate(lines)]
    return '\n'.join(numbered_lines)


async def main():
    configure_client()

    argparser = ArgumentParser()
    argparser.add_argument("--host", type=str, help="IdeFormer host", default="127.0.0.1")
    argparser.add_argument("--port", type=int, help="IdeFormer port", default=5137)
    argparser.add_argument(
        "--grazie_jwt_token", type=str, help="Grazie JWT token", required=True
    )
    argparser.add_argument(
        "--client_auth_type",
        type=str,
        help="Grazie Auth Type (User/Service/Application)",
        required=True,
    )
    argparser.add_argument(
        "--max_chat_iterations",  # --chat or --no-chat
        type=int,
        default=50,
        help="How many times to ask for user feedback",
    )

    args = argparser.parse_args()

    system_prompt = ("You are an expert developer who makes refactoring suggestions to "
                     "improve the quality of the given code. ONLY make TOOL CALLS to perform actions.")
    file_path = input("Please enter the complete path to the file you would like to refactor:")
    with open(file_path) as f:
        user_prompt = add_line_numbers(f.read())

    client = IdeFormerClient(
        ideformer_host=args.host,
        ideformer_port=args.port,
    )
    runner = IdeFormerSimpleGrazieChatV2Runner(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        client=client,
        tools_implementation_provider=IntelliJToolImplementationProvider(),
        grazie_jwt_token=args.grazie_jwt_token,
        client_auth_type=args.client_auth_type,
        max_chat_iterations=args.max_chat_iterations,
        max_tool_calling_iterations=50,
        early_stopping_method="generate",
        client_url="https://api.app.stgn.grazie.aws.intellij.net",
        profile="openai-gpt-4o-mini",
        temperature=0.4
    )
    await runner.arun()
    print(f"The answer is: {runner.result}")


if __name__ == "__main__":
    asyncio.run(main())
