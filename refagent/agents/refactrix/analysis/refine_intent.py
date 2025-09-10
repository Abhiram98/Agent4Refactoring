from typing import List, Tuple
from pydantic import BaseModel


class RefineIntent(BaseModel):
    original_intent: str

    positive_examples: List[Tuple[str, str]]
    negative_examples: List[Tuple[str, str]]

    def get_new_intent(self) -> str:
        return self.original_intent + f"\nAvoid renames like {self.negative_examples[0][0]} -> {self.negative_examples[0][1]}"

