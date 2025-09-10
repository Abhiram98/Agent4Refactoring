from typing import List, Tuple
from pydantic import BaseModel


class RefineIntent(BaseModel):
    original_intent: str

    positive_examples: List[Tuple[str, str]]
    negative_examples: List[Tuple[str, str]]

    def get_new_intent(self) -> str:
        renames_str = ""
        for i in self.negative_examples:
            renames_str += f"Avoid {i[0]} -> {i[1]}\n"
        return self.original_intent + f"\nAvoid the following renames: {renames_str}"

