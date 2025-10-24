from typing import Optional

from pydantic.v1 import BaseModel


class RenameScope(BaseModel):
    pattern: str
    condition: Optional[str] = None

    def __str__(self) -> str:
        s = self.pattern
        if self.condition is not None:
            s += f". {self.condition}"
        return s
