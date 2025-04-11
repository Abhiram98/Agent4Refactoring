from pydantic.v1 import BaseModel, Field
import refagent.utils.intellij_server as ij_server
from langchain_core.tools import tool, BaseTool
from typing import Optional, Annotated, List


class RefactoringToolProvider(BaseModel):
    ide_server: Optional[ij_server.IntellijServer] = Field(description="ide server object to interract with")

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
                new_content: Annotated[str, "The replacement text to overwrite the original file contents "
                                            "with."]
                                  ):
            """Replace the entire contents of the chosen file with the newly provided contents,
                 overwriting any existing data."""
            return self.ide_server.call_tool("replace_file_contents", file_path=file_path, new_content=new_content)


        @tool
        def replace_method_contents(
                file_path: Annotated[str, "The path to the file that will be updated."],
                method_name: Annotated[str, "The name of the method that will be updated."],
                new_content: Annotated[str, "The replacement text to overwrite the method's contents with."],
                line_num: Annotated[Optional[int], "Line number to identify the method at"] = None
        ):
            """Replace the entire contents of the chosen method with the newly provided contents, overwriting
                any existing data."""
            return self.ide_server.call_tool("replace_method_contents",
                                             file_path=file_path, method_name=method_name,
                                             new_content=new_content, line_num=line_num)

        @tool
        def extract_class(
                extract_interface: Annotated[bool, "whether to extract an interface, or superclass. If true, an interface will be extracted"],
                members: Annotated[list[str], "names of fields/methods in the host class to be extracted into the super class."],
                super_class_name: Annotated[str, "the name of the super class to be extracted"],
                sub_class_name: Annotated[str, "the name of the current class after extraction."]
        ):
            """Extract a super class/interface from an existing class.
            Choose relevant fields and methods that need to go into the super class.
            Also provide a name for the superclass and the subclass."""
            return self.ide_server.call_tool("extract-class",
                                      extract_interface=extract_interface,
                                      new_class_name=super_class_name,
                                      sub_class_name=sub_class_name,
                                      members=members)


        @tool
        def pull_up(
                members: Annotated[List[str], "The members of the class to pull up into super class/ interface"],
                super_class: Annotated[str, "The name of the super class/interface to move the members into."],
                make_abstract: Annotated[Optional[bool], "Whether to keep a copy of the member in the current class, "
                                                         "and make it abstract in the super class/interface."] = True
        ):
            """Move members of a class (fields/methods) into it's super class/interface.
            If `make_abstract` is True, a copy of the member will be maintained in the current class,
            with an abstract version in the super class.
            """

            return self.ide_server.call_tool('pull-up',
                                             super_class=super_class,
                                             members=members,
                                             make_abstract=make_abstract)

        @tool
        def push_down(
                members: Annotated[List[str], "The members of the class to push down into sub class"],
                keep_abstract: Annotated[Optional[bool], "Whether to keep an abstract copy of "
                                                         "the member in the super class/interface"] = True
        ):
            """Move members of a super-class or interface (fields/methods) into its sub classes.
            If `keep_abstract` is True, an abstract copy of the member will be maintained in the super class/ interface,
            while pushing down the definition into sub classes.
            """

            return self.ide_server.call_tool('push-down',
                                             members=members,
                                             keep_abstract=keep_abstract)

        all_tools: list[BaseTool] = [extract_method, rename, extract_class, pull_up, push_down,
                                     replace_file_contents, replace_method_contents]

        return {i.name: i for i in all_tools}


