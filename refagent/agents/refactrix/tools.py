import json

from pydantic.v1 import BaseModel, Field
import refagent.utils.intellij_server as ij_server
from langchain_core.tools import tool, BaseTool
from typing import Optional, Annotated, List

import refagent.agents.refactrix.supported_refactorings as sup_ref


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
            response = self.ide_server.call_tool("replace_file_contents", file_path=file_path, new_content=new_content)
            self.ide_server.call_tool('run_code_inspection')
            return response


        @tool
        def replace_method_contents(
                file_path: Annotated[str, "The path to the file that will be updated."],
                method_name: Annotated[str, "The name of the method that will be updated."],
                new_content: Annotated[str, "The replacement text to overwrite the method's contents with."],
                line_num: Annotated[Optional[int], "Line number to identify the method at"] = None
        ):
            """Replace the entire contents of the chosen method with the newly provided contents, overwriting
                any existing data. Make sure to include the method's signature while in `new_content` parameter"""
            return self.ide_server.call_tool("replace_method_contents",
                                             file_path=file_path, method_name=method_name,
                                             new_content=new_content, line_num=line_num)

        @tool
        def extract_class(
                extraction_type: Annotated[sup_ref.ExtractionType,
                                    "Specifies the type of extraction: choose from 'interface', 'super_class', 'class', or 'enum'. "
                                    "Selecting 'super_class' will make the current class inherit from the extracted one. "
                                    "Selecting 'class' creates a new class without inheritance."],
                members: Annotated[list[str], "List of member names (fields or methods) in the current class to move into the extracted class."],
                new_class_name: Annotated[str, "Name of the new class/interface/superclass/enum to be created"],
                sub_class_name: Annotated[str, "Name of the updated version of the current class after extraction."]
        ):
            """Extracts a new class, interface, superclass, or enum from an existing class.
            This refactoring tool allows you to modularize code by moving selected fields and methods
            from a current class into a newly created type. You can specify what kind of type to extract
            (e.g., superclass or interface), which members to move, and the names of both the new and
            remaining class."""
            return self.ide_server.call_tool("extract-class",
                                             extraction_type=extraction_type.value,
                                             new_class_name=new_class_name,
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

        @tool
        def change_method_signature(
                method_name: Annotated[str, "The name of the method whose signature needs to be changed"],
                method_line_num: Annotated[Optional[int], "The line number to indentify the method at"],
                new_method_name: Annotated[Optional[str], "The name of the new method"],
                new_parameters: Annotated[Optional[List[sup_ref.Parameter]], "The updated list of parameters to method"],
                new_return_type: Annotated[Optional[str], "The new return type of the method"],
                new_modifier: Annotated[Optional[str], "The new modifiers (private/public/protected) of the method. "]
        ):
            """
            Change the signature of the given method.
            To leave some elements of the method signature unchanged, do not pass any value for them.
            """

            return self.ide_server.call_tool('change_signature',
                                             method_name=method_name,
                                             method_line_num=method_line_num,
                                             new_signature={'method_name': new_method_name,
                                                            'parameters': [json.loads(i.json()) for i in new_parameters],
                                                            'return_type': new_return_type,
                                                            'modifier': new_modifier
                                                            })

        @tool
        def introduce_parameter_object(
                method_name: Annotated[str, "The name of the method to refactor."],
                method_line_num: Annotated[Optional[int], "The line number where the method is defined (if known)." 
                                                          "If None, the method will be located using just its name."],
                parameter_names: Annotated[List[str], "The list of parameter names "
                                                  "that should be encapsulated in the new class."],
                new_class_name: Annotated[str, "The name of the new class "
                                               "that will encapsulate the specified parameters."]

        ):
            """
            This refactoring replaces a group of parameters in a method with a single object that encapsulates them.
            It helps to improve code readability, reduce duplication, and group related data more meaningfully.
            Use this refactoring to extract a class from a method's parameters
            """
            return self.ide_server.call_tool(
                "introduce_param_object",
                method_name=method_name,
                method_line_num=method_line_num,
                parameter_names=parameter_names,
                new_class_name=new_class_name
            )

        @tool
        def move_method(
                method_name: Annotated[str, "The name of the method to move."],
                target_class: Annotated[str, "The class to move the method to"]
        ):
            """
            Moves a method to a given target class, changing references accordingly.
            """
            return self.ide_server.call_tool(
                "move-method",
                method_name=method_name,
                target_class=target_class
            )

        @tool
        def extract_field(
                field_name: Annotated[str, "The name of the newly created field"],
                make_static: Annotated[bool, "Whether to make the field static?"],
                expression: Annotated[str, "The expression from which"],
                line_num: Annotated[int, "The line number to find the expression at"]
        ):
            """
            Extracts a field from the given expression.
            """
            if expression.isidentifier():
                return self.ide_server.call_tool(
                    "extract_field",
                    new_field_name=field_name,
                    variable_name=expression,
                    line_num=line_num,
                    make_static=make_static
                )
            else:
                return self.ide_server.call_tool(
                    "extract_field_from_literal",
                    new_field_name=field_name,
                    line_num=line_num,
                    literal_value=expression,
                    make_static=make_static
                )


        @tool
        def type_change(
                variable_name: Annotated[str, "The variable who's type needs to change"],
                new_type: Annotated[str, "The new type for the variable"],
                line_num: Annotated[Optional[int], "A line number to identify the variable at"]
        ):
            """Change the type of a program element to a new type.
            E.g. change the type of a variable, parameter, field"""
            return self.ide_server.call_tool(
                "type_change",
                variable_name=variable_name,
                new_type=new_type,
                line_num=line_num
            )

        all_tools: list[BaseTool] = [extract_method, rename, extract_class, pull_up, push_down,
                                     change_method_signature, introduce_parameter_object, move_method,
                                     extract_field, type_change,
                                     replace_file_contents, replace_method_contents]

        return {i.name: i for i in all_tools}


