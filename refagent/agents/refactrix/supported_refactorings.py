from enum import Enum


class SupportedRefactorings(Enum):
    EXTRACT_METHOD = "extract_method"
    RENAME = "rename"
    MOVE = "move"
    EXTRACT_CLASS = "extract_class"
    UNSUPPORTED = "not_supported"


documentation = {
    SupportedRefactorings.EXTRACT_METHOD: "extract a portion of a method to create a new one - for resuse/modularity.",
    SupportedRefactorings.RENAME: "rename a program element, such as a variable, field, method, class.",
    SupportedRefactorings.MOVE: "move a member of a class (method/field).",
    SupportedRefactorings.EXTRACT_CLASS: "extract an super class/interface from an existing class.",
    SupportedRefactorings.UNSUPPORTED: "Cannot classify the refactoring into on of the other types."
}