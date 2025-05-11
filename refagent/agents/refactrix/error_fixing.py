from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from pydantic.v1 import BaseModel, Field, PrivateAttr
from typing import List
import refagent.utils.intellij_server as ij


class ErrorMessage(BaseModel):
    line_num: int = Field(description="The line number of the error.")
    problem: str = Field(description="The error message.")


class ErrorFixing(BaseModel):

    refactoring_intent: str = Field(description="The intent of the refactoring.")
    errors: List[ErrorMessage] = Field(description="The errors that need fixing.")
    tools: List[BaseTool] = Field(description="The tools that can be used to fix the errors.")
    model: BaseChatModel = Field(description="The model that can be used to fix the code.")
    ide_server: ij.IntellijServer = Field(description="The IDE server that can be used to fix the code.")

    def compile_and_run(self) -> bool:
        """Return True if the code was successfully fixed, False otherwise."""
        return False

