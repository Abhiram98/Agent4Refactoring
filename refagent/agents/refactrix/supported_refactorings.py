from enum import Enum


class SupportedRefactorings(Enum):
    EXTRACT_METHOD = "extract_method"
    RENAME = "rename"
    MOVE = "move"
    EXTRACT_CLASS = "extract_class"
    UNSUPPORTED = "not_supported"
