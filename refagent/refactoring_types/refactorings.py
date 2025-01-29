from pydantic import BaseModel, Field
from typing import List, Self


class CodeLocation(BaseModel):
    filePath: str = Field(..., description="Path to the file where the code element is located")
    startLine: int = Field(..., description="Starting line of the code element")
    endLine: int = Field(..., description="Ending line of the code element")
    startColumn: int = Field(..., description="Starting column of the code element")
    endColumn: int = Field(..., description="Ending column of the code element")
    codeElementType: str = Field(..., description="Type of the code element (e.g., CLASS, METHOD, VARIABLE)")
    description: str = Field(..., description="Description of the code element")
    codeElement: str = Field(..., description="Actual code element")


class RefminerOut(BaseModel):
    type: str = Field(..., description="Refactoring type")
    description: str = Field(..., description="Description of the refactoring")
    leftSideLocations: List[CodeLocation] = Field(..., description="Code element that _was_ refactored")
    rightSideLocations: List[CodeLocation] = Field(..., description="Modified/refactored code element")

    @classmethod
    def load(cls, raw_json) -> List[Self]:
        return [cls(**r) for r in raw_json['commits'][0]['refactorings']]

    def __eq__(self, other):
        if not isinstance(other, RefminerOut):
            return False
        if self.type != other.type:
            return False
        if self.leftSideLocations[0].filePath != other.leftSideLocations[0].filePath:
            return False
        return True  # TODO: make this more precise,
        # by creating a class for each refactoring type and defining eq there
