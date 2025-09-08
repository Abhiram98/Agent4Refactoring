from pydantic.v1 import BaseModel, Field, PrivateAttr
from typing import Optional
from langchain_core.language_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph
from langgraph.graph import StateGraph, START, END, MessagesState
from langchain_core.messages import SystemMessage, HumanMessage


class AugmentedIntent(BaseModel):
    original_intent: str = Field(description="The original intent provided by the user.")
    augmented_intent: str = Field(description="The enriched intent with extra details.")


class AnalysisComponent(BaseModel):
    """An agent that takes an initial intent and augments it with additional details."""
    initial_intent: str = Field(description="The initial intent provided by the user.")
    old_name: str = Field(description="The name of the variable that was renamed.")
    new_name: str = Field(description="The new name for the variable.")
    context_information: Optional[str] = Field(
        default=None,
        description="Optional context to help augment the intent."
    )
    source_code: str = Field(description="Source code to work with")
    source_file_path: str = Field(description="Path to the source file.")
    model: BaseChatModel = Field(description="Model to use for augmenting the intent")
    generation_system_message: str = Field(
        default=(
            "You are an expert software developer tasked with enhancing the user intents "
            "from the provided context and source code."
        ),
        description=(
            "System message for the intent augmentation LLM call. "
            "Return the original intent and the augmented intent in a structured JSON format."
        )
    )

    # store the result for retrieval after flow
    _augmented_intent: Optional[AugmentedIntent] = PrivateAttr(default=None)

    def compile(self) -> CompiledStateGraph:
        def generate_transformation_rule(state: MessagesState):
            system_msg = (
                f"{self.generation_system_message}\n\n"
                f"You must return ONLY the transformation rule using the specified template format. "
                f"Do not include any other text, explanations, or formatting."
            )

            llm_messages = [
                SystemMessage(content=system_msg),
                HumanMessage(content=f"Initial intent: {self.initial_intent}")
            ]

            print(f"old name: {self.old_name} new name: {self.new_name}")
            # Provide both diff and source code when available for complete context
            if self.context_information:
                code_context = f"Code Diff:\n{self.context_information}\n\nSource Code:\n{self.source_code}"
            else:
                code_context = f"Source Code:\n{self.source_code}"

            llm_messages.append(
                HumanMessage(content=f"Analyze this identifier transformation: {self.old_name} -> {self.new_name}\n\n"
                                     f"{code_context}\n\n"
                                     f"Create actionable transformation instructions by completing this template:\n\n"
                                     f'"Transform identifiers that [PATTERN TO MATCH] by [TRANSFORMATION RULE]. Apply this to [SCOPE/CONTEXT]."\n\n'
                                     f"Guidelines:\n"
                                     f"- [PATTERN TO MATCH]: Focus on SEMANTIC PATTERNS (e.g., 'identifiers with verbose suffixes', 'methods containing redundant prefixes') rather than exact identifier names\n"
                                     f"- [TRANSFORMATION RULE]: Describe changes to word parts/suffixes/prefixes (e.g., 'replacing verbose suffixes with concise equivalents')\n"
                                     f"- [SCOPE/CONTEXT]: Define the type of code context where this applies using code element terms - avoid specific class or method names\n\n"
                                     f"CRITICAL: Think about WORD PARTS and SEMANTIC CONCEPTS, not exact identifiers. Focus on what part of the identifier changed (prefix, suffix, middle word) and why that change would apply to similar identifiers.\n\n"
                                     f"Write exactly 1-2 sentences using this template structure, then provide a concrete example using the given transformation: 'Example: {self.old_name} -> {self.new_name}'."
                             )
            )

            response = self.model.invoke(llm_messages)
            # Get the transformation rule from LLM response
            transformation_rule = response.content if isinstance(response.content, str) else str(response.content)
            print(f"DEBUG: LLM Response content: {transformation_rule}")

            # Create AugmentedIntent using existing initial_intent and new transformation rule
            self._augmented_intent = AugmentedIntent(
                original_intent=self.initial_intent,
                augmented_intent=transformation_rule.strip()
            )

            return {'messages': llm_messages + [response]}

        workflow = StateGraph(MessagesState)
        workflow.add_node("generate_transformation_rule", generate_transformation_rule)
        workflow.add_edge(START, "generate_transformation_rule")
        workflow.add_edge("generate_transformation_rule", END)
        return workflow.compile()

    def run(self) -> AugmentedIntent:
        compiled_flow = self.compile()
        # invoke the graph (initial messages not used in node logic)
        compiled_flow.invoke({'messages': []})
        if self._augmented_intent is None:
            raise ValueError("Augmented intent was not generated or found in the component.")
        return self._augmented_intent



class NaiveAnalysisComponent(AnalysisComponent):
    def run(self) -> AugmentedIntent:
        return AugmentedIntent(
            original_intent=self.initial_intent,
            augmented_intent=f"Please rename the variable '{self.old_name}' to '{self.new_name}'"
        )