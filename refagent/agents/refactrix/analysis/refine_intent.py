from typing import List, Tuple

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel


class RefineIntent(BaseModel):
    source_code: str
    original_intent: str

    positive_examples: List[Tuple[str, str]]
    negative_examples: List[Tuple[str, str]]

    feedback: str
    model: BaseChatModel

    def get_new_intent(self) -> str:
        renames_str = ""
        for i in self.negative_examples:
            renames_str += f"Avoid {i[0]} -> {i[1]}\n"
        messages = [
            HumanMessage("Please refine the renaming scope, as the human rejected some refactorings. "
                         "See below:\n"
                         f"{self.feedback}\n"
                         f"This was the original intent: {self.original_intent}\n"
                         f"Here is the source code: {self.source_code}\n"),
            HumanMessage("Please provide a new intent which defines the renaming scope properly.\n"
                         "Limit to 2 sentences.")
        ]

        response = self.model.invoke(messages)
        return response.content

