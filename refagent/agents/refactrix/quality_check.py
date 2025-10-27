from pydantic.v1 import BaseModel, Field, PrivateAttr
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.output_parsers import PydanticOutputParser
import refagent.utils.intellij_server as ij
import refagent.utils.code_utils as code_utils
import refagent.utils.project_manager as pm
import tiktoken
from pathlib import Path
import json
import time
from enum import Enum
from typing import Optional


class IntentAlignment(str, Enum):
    MET = "met"
    PARTIALLY_MET = "partially met"
    NOT_MET = "not met"


class ImprovementResult(str, Enum):
    IMPROVEMENTS = "improvements"
    NO_IMPROVEMENTS = "no improvements"
    NEGATIVE_IMPROVEMENTS = "negative improvements"


# class IntentCoverage(str, Enum):
#     NOT_ADDRESSED = "not addressed"
#     PARTIALLY_ADDRESSED = "partially addressed"
#     FULLY_ADDRESSED = "fully addressed"


class IssueStatus(str, Enum):
    ISSUES = "issues"
    NO_ISSUES = "no issues"
    NEGATIVE_ISSUES = "negative issues"


class OverallAssessment(str, Enum):
    PASS = "Pass"
    FAIL = "Fail"


class QualityCheckResult(BaseModel):
    """
    Result of a quality check analysis on code changes.
    """

    intent_alignment: IntentAlignment = Field(
        description="How well the changes align with the stated intent"
    )
    intent_alignment_explanation: str = Field(
        description="Detailed explanation for the intent alignment"
    )

    improvements: ImprovementResult = Field(
        description="Whether the refactoring made improvements"
    )
    improvements_explanation: str = Field(
        description="Detailed explanation of the improvements"
    )

    # intent_coverage: IntentCoverage = Field(description="Whether all aspects of the intent were addressed")
    # intent_coverage_explanation: str = Field(description="Detailed explanation of intent coverage")

    issues: IssueStatus = Field(description="Potential issues with the refactoring")
    issues_explanation: str = Field(description="Detailed explanation of any issues")

    overall_assessment: OverallAssessment = Field(
        description="Final assessment of the refactoring"
    )
    refined_intent: str = Field(
        description="Refined intent based to address the unmet refactoring"
    )


class QualityCheck(BaseModel):
    """
    Component to check if the refactoring intent has been met by analyzing
    the code changes before and after refactoring.
    """

    model: BaseChatModel = Field(description="Langchain Chat model")
    ide_server: ij.IntellijServer = Field(
        description="IntelliJ Server to interact with IDE"
    )
    original_code: str = Field(description="The original code")
    refactored_code: str = Field(description="The refactored code")
    intent: str = Field(description="The refactoring intent")

    class Config:
        arbitrary_types_allowed = True

    def count_tokens(self, text: str) -> int:
        """Count the number of tokens in a text using tiktoken. [Maybe will need in the future]"""
        encoding = tiktoken.get_encoding("cl100k_base")  # Using OpenAI's encoding
        return len(encoding.encode(text))

    def analyze_code_changes(
        self, before_code: str, after_code: str, intent: str
    ) -> QualityCheckResult:
        """Analyze how well the code changes meet the intended refactoring goals."""
        parser = PydanticOutputParser(pydantic_object=QualityCheckResult)

        system_message = SystemMessage(
            "You are an expert code reviewer specializing in refactoring analysis. "
            "Your task is to analyze how well the code changes meet the intended refactoring goals. "
            "Please provide a detailed analysis that includes:\n"
            "1. How well the changes align with the stated intent.\n"
            "2. What specific improvements were made.\n"
            "3. Whether there are any aspects of the intent that were not addressed.\n"
            "4. Any potential issues or concerns with the refactoring.\n"
            "5. Refined intent based to address the unmet refactoring.\n"
            "Be specific and reference the actual code changes in your analysis.\n\n"
            f"{parser.get_format_instructions()}"
        )

        # Split into two separate human messages for better visibility
        human_message1 = HumanMessage(
            f"Here is the refactoring intent: {intent}\n\n"
            f"Original code:\n{before_code}"
        )

        human_message2 = HumanMessage(
            f"Refactored code:\n{after_code}\n\n"
            "Please analyze how well the refactoring meets the stated intent."
        )

        response = self.model.invoke([system_message, human_message1, human_message2])
        try:
            result = parser.parse(response.content)
            return result
        except Exception as e:
            print(f"Error parsing response: {e}")
            print(f"Raw response: {response.content}")
            raise Exception(f"Error parsing response: {e}")

    def get_file_contents(self, file_path: str) -> str:
        """Get the contents of a file using the IDE server."""
        try:
            self.ide_server.open_file(Path(file_path))
            source_code = self.ide_server.call_tool_get("get_source_code")
            return source_code
        except Exception as e:
            print(f"Error getting file contents: {e}")
            return ""

    def get_v1_hash_from_benchmark(self, benchmark_file_path, target_id):
        """Extract data from the benchmark file for the specified id."""
        with open(benchmark_file_path, "r") as file:
            benchmark_data = json.load(file)
            for item in benchmark_data:
                if isinstance(item, dict) and item.get("id") == target_id:
                    return (
                        item.get("v1_hash"),
                        item.get("improve_commit_message"),
                        item.get("starting_file_rel_path"),
                    )
        raise ValueError(f"No item found for id {target_id} in benchmark file")

    def get_commit_hash_from_results(self, results_file_path, target_id):
        """Extract a commit hash from the results.json file for the specified id."""
        with open(results_file_path, "r") as file:
            results = json.load(file)
            for item in results:
                if (
                    isinstance(item, dict)
                    and item.get("id") == target_id
                    and item.get("response")
                    and item["response"].get("commit_hash")
                ):
                    return item["response"]["commit_hash"]
        raise ValueError(f"No commit hash found for id {target_id} in results file")

    def compile_and_run(self) -> Optional[QualityCheckResult]:
        """
        Run quality check to determine if the refactoring intent was met using commit hashes.

        Args:
            target_id: The ID of the refactoring in the benchmark file
            project_name: The name of the project being evaluated
            results_path: Path to the results JSON file containing the post-refactoring commit hash
            benchmark_path: Path to the benchmark JSON file containing the pre-refactoring data

        Returns:
            QualityCheckResult: The analysis result as a structured object
        """

        try:
            # Analyze code changes
            analysis_result = self.analyze_code_changes(
                before_code=self.original_code,
                after_code=self.refactored_code,
                intent=self.intent,
            )

            print("\n=== Refactoring Analysis ===\n")
            print(f"INTENT ALIGNMENT: {analysis_result.intent_alignment.value}")
            print(f"Explanation: {analysis_result.intent_alignment_explanation}\n")

            print(f"IMPROVEMENTS: {analysis_result.improvements.value}")
            print(f"Explanation: {analysis_result.improvements_explanation}\n")

            # print(f"INTENT COVERAGE: {analysis_result.intent_coverage}")
            # print(f"Explanation: {analysis_result.intent_coverage_explanation}\n")

            print(f"ISSUES: {analysis_result.issues.value}")
            print(f"Explanation: {analysis_result.issues_explanation}\n")

            print(f"OVERALL ASSESSMENT [{analysis_result.overall_assessment.value}]:")
            print(analysis_result.refined_intent)

            return analysis_result

        except ValueError as e:
            print(f"Error: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error: {e}")
            import traceback

            traceback.print_exc()
            return None
