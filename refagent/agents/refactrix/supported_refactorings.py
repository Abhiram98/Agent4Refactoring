from enum import Enum


class SupportedRefactorings(Enum):
    EXTRACT_METHOD = "extract_method"
    RENAME = "rename"
    MOVE = "move"
    EXTRACT_CLASS = "extract_class"
    PUSH_DOWN = "push_down"
    PULL_UP = "pull_up"
    TYPE_CHANGE = "type_change"
    CHANGE_SIGNATURE = "change_method_signature"
    UNSUPPORTED = "not_supported"


documentation = {
    SupportedRefactorings.EXTRACT_METHOD: "extract a portion of a method to create a new one - for resuse/modularity.",
    SupportedRefactorings.RENAME: "rename a program element, such as a variable, field, method, class.",
    SupportedRefactorings.MOVE: "move a program element (class/method/field) to another location. "
                                "E.g. move a method to another class, move a class to a different package.",
    SupportedRefactorings.EXTRACT_CLASS: "extract an super class/interface from an existing class.",
    SupportedRefactorings.PUSH_DOWN: "push down a member of a class (method/field) into a subclass, "
                                     "or implementation of interface.",
    SupportedRefactorings.PULL_UP: "pull up a member of a class (method/field) into its super class/interface.",
    SupportedRefactorings.TYPE_CHANGE: "Change the type of a program element (variable, field, parameter)",
    SupportedRefactorings.CHANGE_SIGNATURE: "Change the signature of a method - "
                                            "add a parameter, delete a parameter, change return type",
    SupportedRefactorings.UNSUPPORTED: "Cannot classify the refactoring into on of the other types."
}