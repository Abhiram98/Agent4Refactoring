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

    @property
    def old_name(self) -> Optional[str]:
        # TODO: this is hacky, we should store the old name and new name explicitly.
        try:
            old_name = self.pattern.split("'")[1]
        except IndexError:
            print("Failed to get old name. Returning None")
            old_name = None
        return old_name
