from typing import List, Tuple

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic.v1 import BaseModel # to allow BaseChatmodel (grazie) to be a field for pydantic class

from refagent.agents.memory.memory_models import RefactoringSuggestion
import refagent.agents.refactrix.analysis.scope as scope
import refagent.utils.cache.prompt_cache as prompt_cache

class RefineIntent(BaseModel):
    source_code: str
    original_scope: scope.RenameScope
    model: BaseChatModel
    accepted_renames: List[RefactoringSuggestion]
    rejected_renames: List[RefactoringSuggestion]

    class Config:
        arbitrary_types_allowed = True


    def get_new_scope(self) -> scope.RenameScope:

        response = prompt_cache.prompt(
            model=self.model,
            messages=[
                SystemMessage("Analyze the accepted and rejected renames and "
                              "come up with a condition that prevents the pattern of rejection."),
                HumanMessage("I was asked to perform renames according to this pattern: "
                             f"{self.original_scope.pattern}. However, a few of my suggestions were rejected. "
                             f"Please see below:"),
                self.feedback,
                HumanMessage(f"Respond with a specific condition that reads like this "
                             f"'Do not apply this pattern in cases where ... '")
            ]
        )
        return scope.RenameScope(pattern=self.original_scope.pattern, condition=response.content)


    @property
    def feedback(self) -> HumanMessage:
        """Create few shot examples based on memory content"""
        message = ["Feedback:\n"]

        assert len(self.accepted_renames) + len(self.rejected_renames) > 0

        for rename in self.accepted_renames:
            message.append(f"=== Code ===")
            message.append("...")
            message.append(rename.snippet) # add snippet
            message.append("...")
            message.append(f"=== End of Code ===")

            message.append("")
            message.append("Feedback:")
            example_str = (f"Rename {rename.code_element_type} `{rename.old_name}` -> `{rename.new_name}` near line {rename.line_num} "
                           f"fits the renaming scope. I accept this suggestion.")
            message.append(example_str)

        for rename in self.rejected_renames:
            message.append(f"=== Code ===")
            message.append("...")
            message.append(rename.snippet)  # add snippet
            message.append("...")
            message.append(f"=== End of Code ===")

            message.append("")
            message.append("Feedback:")
            message.append(f"Renaming {rename.code_element_type} `{rename.old_name}` -> `{rename.new_name}` "
                           f"does not fit the renaming scope. I reject this suggestion.")
            message.append("")

        return HumanMessage("\n".join(message))


