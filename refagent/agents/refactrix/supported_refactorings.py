from enum import Enum
from pydantic.v1 import BaseModel, Field
from typing import List, Optional


class Parameter(BaseModel):
    param_name: str = Field(description="the name of the parameter")
    param_type: str = Field(description="the type of the parameter")


class ExtractionType(Enum):
    INTERFACE = "interface"
    SUPER_CLASS = "super_class"
    CLASS = "class"
    ENUM = "enum"

class CodeElementType(Enum):
    METHOD = "method"
    FIELD = "field"
    CLASS = "class"
    PARAMETER = "parameter"
    VARIABLE = "variable"

    @staticmethod
    def get_rminer_str(rminer_type: str):
        name_map = {'attribute': 'field'}
        key = rminer_type.split('Rename ')[-1].lower()
        return name_map.get(key, key)

class SupportedRefactorings(Enum):
    EXTRACT_METHOD = "extract_method"
    RENAME = "rename"
    MOVE = "move"
    EXTRACT_CLASS = "extract_class"
    PUSH_DOWN = "push_down"
    PULL_UP = "pull_up"
    TYPE_CHANGE = "type_change"
    CHANGE_SIGNATURE = "change_method_signature"
    EXTRACT_FIELD = "extract_field"
    UNSUPPORTED = "not_supported"


documentation = {
    SupportedRefactorings.EXTRACT_METHOD: "extract a portion of a method to create a new one - for resuse/modularity.",
    SupportedRefactorings.RENAME: "rename a program element, such as a variable, field, method, class.",
    SupportedRefactorings.MOVE: "move a program element (class/method/field) to another location. "
                                "E.g. move a method to another class, move a class to a different package.",
    SupportedRefactorings.EXTRACT_CLASS: "extract an class/super_class/interface/enum from an existing class. "
                                         "choose to perform composition instead of inheritance if possible",
    SupportedRefactorings.PUSH_DOWN: "push down a member of a class (method/field) into a subclass, "
                                     "or implementation of interface.",
    SupportedRefactorings.PULL_UP: "pull up a member of a class (method/field) into its super class/interface.",
    SupportedRefactorings.TYPE_CHANGE: "Change the type of a program element (variable, field, parameter)",
    SupportedRefactorings.CHANGE_SIGNATURE: "Change the signature of a method - "
                                            "add a parameter, delete a parameter, change parameter type, "
                                            "change return type",
    SupportedRefactorings.EXTRACT_FIELD: "Extract a field from a method's local variable/ literal expression. "
                                         "Use this refactoring to generate a class's field out of existing code",
    SupportedRefactorings.UNSUPPORTED: "Cannot classify the refactoring into on of the other types."
}