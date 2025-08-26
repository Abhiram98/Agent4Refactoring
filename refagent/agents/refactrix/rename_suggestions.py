from pydantic.v1 import BaseModel, Field
from typing import List, Optional
from enum import Enum


class CodeElementType(str, Enum):
    """Supported code element types for renaming."""
    METHOD = "method"
    VARIABLE = "variable"
    CLASS = "class"
    PARAMETER = "parameter"

class RenameSuggestion(BaseModel):
    """A single rename suggestion from the LLM."""
    old_name: str = Field(description="Current name of the code element")
    new_name: str = Field(description="Proposed new name for the code element")
    line_num: int = Field(description="Line number where the element is located")
    code_element_type: CodeElementType = Field(description="Type of code element to rename")
    reason: Optional[str] = Field(description="Explanation for why this rename is suggested", default="")


class RenameAnalysis(BaseModel):
    """Complete analysis and rename suggestions from the LLM."""
    analysis: str = Field(description="Brief description of the analysis performed")
    rename_suggestions: List[RenameSuggestion] = Field(description="List of suggested renames")
    
    class Config:
        # Allow enum values to be serialized as strings
        use_enum_values = True


class ValidatedRenames(BaseModel):
    """Result after critique validation of rename suggestions."""
    valid_suggestions: List[RenameSuggestion] = Field(description="Suggestions that passed critique")
    invalid_suggestions: List[RenameSuggestion] = Field(description="Suggestions that failed critique")
    critique_feedback: str = Field(description="Feedback from critique component")