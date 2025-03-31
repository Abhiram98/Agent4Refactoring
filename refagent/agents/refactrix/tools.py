from pydantic import BaseModel, Field
import refagent.utils.intellij_server as ij_server
from langchain_core.tools import tool, BaseTool
from typing import Optional, Annotated


class RefactoringToolProvider(BaseModel):
    ide_server: ij_server.IntellijServer = Field(description="ide server object to interract with")

    def get(self) -> dict[str, BaseTool]:
        @tool
        def extract_method(start_line: Annotated[int, "The starting line number from which "
                                                      "the block of code will be extracted. Must be a positive integer."],
                           end_line: Annotated[int , "The ending line number to which the block of code will "
                                                     "be extracted. Must be a positive integer greater than "
                                                     "or equal to `start_line`."],
                           new_method_name: Annotated[str, "The name of the new method that will contain the "
                                                            "extracted block of code. Must be a valid "
                                                            "method name."]):
            """Extracts a method from the specified range of lines in a source code file and creates a new method
            with the given name. This is intended to refactor a block of code within a file, taking the
            lines from `start_line` to `end_line`, inclusive, and moving them into a new method named
            `new_method_name`. The original block of code is replaced with a call to the newly created method."""

            return self.ide_server.call_tool('extract_method',
                                      start_line=start_line, end_line=end_line, new_method_name=new_method_name)



        @tool
        def rename(old_name: Annotated[str, "The name of the variable to be renamed."],
                   new_name: Annotated[str, "The new name for the variable."],
                   line_num:  Annotated[Optional[int], "An optional parameter to identify the variable using "
                                                       "a line number, if there are multiple variables with "
                                                       "the same name"] = None):
            """Renames occurrences of an entity (variable, field, class) within the scope of a method/class.

            This will refactor the code by replacing all occurrences of the variable named `old_name`
            with the new variable name `new_name` within the scope of the class or method where it is called."""
            return self.ide_server.call_tool("rename", old_name=old_name, new_name=new_name, line_num=line_num)

        @tool
        def replace_file_contents(
                file_path: Annotated[str, "The path to the file that will be updated."],
                new_contents: Annotated[str, "The replacement text to overwrite the original file contents "
                                                      "with."]
                                  ):
            """Replace the entire contents of the chosen file with the newly provided contents,
                 overwriting any existing data."""
            return self.ide_server.call_tool("replace_file_contents", file_path=file_path, new_contents=new_contents)


        @tool
        def replace_method_contents(
                file_path: Annotated[str, "The path to the file that will be updated."],
                method_name: Annotated[str, "The name of the method that will be updated."],
                new_content: Annotated[str, "The replacement text to overwrite the method's contents with."],
                line_num: Annotated[Optional[int], "Line number to identify the method at"] = None
        ):
            """Replace the entire contents of the chosen method with the newly provided contents, overwriting
                any existing data."""
            return self.ide_server.call_tool("replace_method_contents", file_path=file_path, method_name=method_name,
                                      new_content=new_content, line_num=line_num)

        all_tools: list[BaseTool] = [extract_method, rename, replace_file_contents, replace_method_contents]

        return {i.name: i for i in all_tools}


