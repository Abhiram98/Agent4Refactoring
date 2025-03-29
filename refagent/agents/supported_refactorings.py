from enum import Enum


class SupportedRefactorings(Enum):
    EXTRACT_METHOD = "extract_method"
    RENAME = "rename"
    MOVE = "move"
    CUSTOM = "custom_refactoring"
