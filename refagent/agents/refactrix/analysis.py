from pydantic.v1 import BaseModel, Field, PrivateAttr
from typing import Optional
from langchain_core.language_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph
from langgraph.graph import StateGraph, START, END, MessagesState
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import PydanticOutputParser
from refagent.experiments.run_codescene import run_codescene
import pathlib
import os

class AugmentedIntent(BaseModel):
    original_intent: str = Field(description="The original intent provided by the user.")
    augmented_intent: str = Field(description="The enriched intent with extra details.")

class AnalysisComponent(BaseModel):
    """An agent that takes an initial intent and augments it with additional details."""
    initial_intent: str = Field(description="The initial intent provided by the user.")
    codescene_context: Optional[bool] = Field(
        default=None,
        description="Optional context from CodeScene to help augment the intent."
    )
    source_code: str = Field(description="Source code to work with")
    source_file_path: str = Field(description="Path to the source file.")
    model: BaseChatModel = Field(description="Model to use for augmenting the intent")
    generation_system_message: str = Field(
        default=(
            "You are an expert assistant tasked with enhancing the user intents "
            "from the provided context and source code. Return ONLY the JSON as instructed."
        ),
        description=(
            "System message for the intent augmentation LLM call. "
            "Return the original intent and the augmented intent in a structured JSON format."
        )
    )

    # store the result for retrieval after flow
    _augmented_intent: Optional[AugmentedIntent] = PrivateAttr(default=None)

    def compile(self) -> CompiledStateGraph:
        def augment_intent_node(state: MessagesState):
            parser = PydanticOutputParser(pydantic_object=AugmentedIntent)
            fmt = parser.get_format_instructions()

            system_msg = (
                f"{self.generation_system_message}\n\n"
                f"Return ONLY the JSON—no markdown or commentary.\n"
                f"{fmt}"
            )

            llm_messages = [
                SystemMessage(content=system_msg),
                HumanMessage(content=f"Initial intent: {self.initial_intent}")
            ]
            
            if self.codescene_context:
                projects_base_path = pathlib.Path(os.environ.get('PROJECTS_BASE_PATH'))

                codescene_result = run_codescene(self.source_file_path)
                # print("CodeScene context:", codescene_result.score)
                
                # # Only add CodeScene context if we have meaningful output
                if codescene_result and (codescene_result.score is not None or codescene_result.review):
                    # Add CodeScene-specific instructions to the system message
                    system_msg = (
                        f"{self.generation_system_message}\n\n"
                        "Consider the CodeScene analysis in your response:\n"
                        "- Factor in the code quality score if available\n"
                        "- Consider any identified code smells or review points when augmenting the intent\n\n"
                        f"Return ONLY the JSON—no markdown or commentary.\n"
                        f"{fmt}"
                    )
                    # Update the first message with new system message
                    llm_messages[0] = SystemMessage(content=system_msg)
                    # Add CodeScene context
                    llm_messages.append(
                        HumanMessage(content=f"CodeScene Analysis:\n{codescene_result}")
                    )

            llm_messages.append(
                HumanMessage(content=f"Source code:\n{self.source_code}")
            )

            response = self.model.invoke(llm_messages)
            augmented_obj = parser.parse(response.content)
            # save for retrieval
            self._augmented_intent = augmented_obj
            # update only messages in state
            return {'messages': [response]}

        workflow = StateGraph(MessagesState)
        workflow.add_node("augment_intent", augment_intent_node)
        workflow.add_edge(START, "augment_intent")
        workflow.add_edge("augment_intent", END)
        return workflow.compile()

    def run(self) -> AugmentedIntent:
        compiled_flow = self.compile()
        # invoke the graph (initial messages not used in node logic)
        compiled_flow.invoke({'messages': []})
        if self._augmented_intent is None:
            raise ValueError("Augmented intent was not generated or found in the component.")
        return self._augmented_intent
