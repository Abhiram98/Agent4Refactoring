from typing import List, Tuple

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic.v1 import BaseModel # to allow BaseChatmodel (grazie) to be a field for pydantic class

from agents.refactrix.analysis.component import AnalysisComponent


class RefineIntent(BaseModel):
    source_code: str
    original_intent: str

    positive_examples: List[Tuple[str, str]]
    negative_examples: List[Tuple[str, str]]

    feedback: str
    model: BaseChatModel

    def get_new_intent(self) -> str:
        # renames_str = "\nThe following renames DO NOT fit the pattern:\n"
        # seed_bad = []
        # for i in self.negative_examples:
        #     if (i[0],i[1]) in seed_bad:
        #         continue
        #     renames_str += f"DO NOT suggest renaming `{i[0]}` to `{i[1]}`\n"
        #     seed_bad.append((i[0], i[1]))
        # return self.original_intent + renames_str

        response = AnalysisComponent(
            initial_intent=self.original_intent,
            old_name='',
            new_name='',
            feedback=self.feedback,
            model=self.model,
            source_code=self.source_code,
            source_file_path=None
        ).run()
        return response.augmented_intent


