from enum import Enum


class SupportedRefactorings(Enum):
    EXTRACT_METHOD = "extract_method"
    RENAME = "rename"
    MOVE = "move"
    EXTRACT_CLASS = "extract_class"
    PUSH_DOWN = "push_down"
    PULL_UP = "pull_up"
    UNSUPPORTED = "not_supported"


documentation = {
    SupportedRefactorings.EXTRACT_METHOD: "extract a portion of a method to create a new one - for resuse/modularity.",
    SupportedRefactorings.RENAME: "rename a program element, such as a variable, field, method, class.",
    SupportedRefactorings.MOVE: "move a member of a class (method/field) to another class.",
    SupportedRefactorings.EXTRACT_CLASS: "extract an super class/interface from an existing class.",
    SupportedRefactorings.PUSH_DOWN: "push down a member of a class (method/field) into a subclass, or implementation of interface.",
    SupportedRefactorings.PULL_UP: "pull up a member of a class (method/field) into its super class/interface.",
    SupportedRefactorings.UNSUPPORTED: "Cannot classify the refactoring into on of the other types."
}