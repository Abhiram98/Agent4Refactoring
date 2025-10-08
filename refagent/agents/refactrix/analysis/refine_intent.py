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
        if len(self.rejected_renames) <= 3:
            print("Got the first rejection. Attempting to refine pattern.")
            minimal_edit_str = ("Look for relevant keywords, concepts, and patterns around the accepted renames "
                                "to come up with the pattern. Look at how the accepted/rejected identifiers are being used. "
                                "DO NOT make blanket statements like 'rename only private identifiers.'")
        else:
            minimal_edit_str = ""

        response = prompt_cache.prompt(
            model=self.model,
            messages=[
                SystemMessage("Analyze the accepted and rejected renames and "
                              "come up with a condition that prevents the pattern of rejection."),
                HumanMessage("I was asked to perform renames according to this pattern: "
                             f"{self.original_scope.pattern}. However, a few of my suggestions were rejected. "
                             f"Please see below:"),
                self.feedback,
                HumanMessage(f""
                             f""
                             f""
                             f"Respond with a specific condition explaining the pattern of rejections. "
                             f"Analyze the roles and responsibilities of the identifiers for which there is feedback - "
                             f"this includes classes, methods, and fields - "
                             f"before coming up with a condition. "
                             f"When forming conditions, avoid making blanket statements like “rename only classes.” - "
                             f"keep in mind that there may be other methods/variables which are part of the scope but no feedback is available for them. "
                             f""
                             f"{minimal_edit_str}"
                             # f"Here are some examples of the kind of conditions I am looking for:"
                             # f""
                             f"Base the condition on responsibilities. Respond with a condition like this (2 sentences maximum): \n"
                             # f"Focus on renaming identifiers who's role is ... "
                             f"Do not apply this pattern for identifiers who's role is ...'")
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


class GeneralizedScopeCreator(BaseModel):
    model: BaseChatModel
    old_name: str
    new_name: str

    def get_generalized_intent(self) -> scope.RenameScope:
        # assert len(self.accepted_renames) == 1 and len(self.rejected_renames) == 0
        response = prompt_cache.prompt(
            model=self.model,
            messages=[
                SystemMessage("Analyse the seed rename performed by the developer and come up with a pattern. Respond with a pattern only."),
                HumanMessage("Here are a few examples on how to perform your task:\n"
                             ""
                             "seed rename: 'JoinHintsResolver' -> 'QueryHintsResolver'\n"
                             "pattern: 'join' -> 'query'\n\n"
                             ""
                             "seed rename: 'deprecatedRestoreMode' -> 'deprecatedRecoveryClaimMode'\n"
                             "pattern: 'restore' -> 'recoveryClaim'\n\n"
                             ""
                             "seed rename: 'rescaleManager' -> 'stateTransitionManager'\n"
                             "pattern: 'rescale' -> 'stateTransition'\n\n"
                             ""
                             "seed rename: 'trackLatencyOnIteratorInit' -> 'trackMetricsOnIteratorInit'\n"
                             "pattern: 'latency' -> 'metrics'\n\n"
                             ""
                             "For seed renames with word additions, pick up the specific concept:\n"
                             "seed rename: 'testDropMaterializedTable' -> 'testDropMaterializedTableInContinuousMode'\n"
                             "pattern: 'table' -> 'tableInContinuousMode'\n\n"
                             ""
                             "seed rename: 'testEnvironment' -> 'testStreamEnvironment'\n"
                             "pattern: 'environment' -> 'streamEnvironment'\n\n"
                             ""
                             "For seed renames with word deletions, pick up the specific concept:\n"
                             "seed rename: 'extractExplicitTable' -> 'extractTableOperand'\n"
                             "pattern: 'explicitTable' -> 'Table'\n"
                             ""
                             ""
                             "For seed renames of constant keywords (all upper case), convert the pattern to camelCase:\n"
                             "seed rename: 'ASYNC_INFLIGHT_RECORDS_LIMIT' -> 'ASYNC_STATE_TOTAL_BUFFER_SIZE'\n"
                             "pattern: 'inflight' -> 'state'\n\n"
                             ""
                             ""
                             ),
                HumanMessage(f"seed rename: '{self.old_name}' -> '{self.new_name}'"),
            ]
        )
        pattern = response.content
        if response.content.startswith("pattern: "):
            pattern = response.content[len("pattern: "):]
        return scope.RenameScope(pattern=f"Perform renames that follow this general pattern (case-insensitive): {pattern}")
