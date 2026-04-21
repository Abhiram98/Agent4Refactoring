import logging
import json
from pathlib import Path
from typing import List

from git import Repo
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from refagent.benchmark.design_patterns.scorecard.schema import CandidateScorecard, CheckItem
from refagent.benchmark.design_patterns.scorecard.checks.lenient_ast_checks import (
    ClassMatchingRegexCheck,
    AntiPatternRemovalCheck
)
from refagent.benchmark.design_patterns.scorecard.checks.method_invocation import MethodInvocationCheck
from refagent.benchmark.design_patterns.scorecard.checks.instantiates_class import InstantiatesClassCheck
from refagent.benchmark.design_patterns.scorecard.checks.has_method import HasMethodCheck
from refagent.benchmark.design_patterns.scorecard.checks.implements_abstraction import ImplementsInterfaceCheck, ExtendsClassCheck
from refagent.benchmark.design_patterns.scorecard.checks.has_field import HasFieldCheck
from refagent.benchmark.design_patterns.scorecard.checks.has_constructor_visibility import HasConstructorVisibilityCheck

from refagent.benchmark.design_patterns.pattern_first.models import BirthInfo, GreenfieldVerdict

logger = logging.getLogger(__name__)

class GoalList(BaseModel):
    goals: List[str] = Field(description="A list of high-level natural language goals")

class LenientScoreCardCreator:
    def __init__(self, repo_path: Path, llm: ChatOpenAI):
        self.repo = Repo(repo_path)
        self.repo_path = repo_path
        self.llm = llm

    def create_scorecard(self, candidate_id: str, birth_info: BirthInfo, verdict: GreenfieldVerdict) -> CandidateScorecard:
        """Generates a lenient CandidateScorecard using a 3-phase Goal-to-Check NLP pipeline."""
        
        pattern_type = birth_info.pattern_instance.pattern.value if hasattr(birth_info.pattern_instance.pattern, "value") else str(birth_info.pattern_instance.pattern)
        reasoning = birth_info.pattern_instance.reasoning or ""
        commit_hash = birth_info.birth_commit_sha
        parent_hash = birth_info.parent_sha

        # Extract Contexts
        core_files_diff = self._extract_core_files_diff(commit_hash, parent_hash, verdict)
        call_site_files_diff = self._extract_call_site_diff(commit_hash, parent_hash, verdict)

        checks: List[CheckItem] = []

        # --- Phase 1: Pattern Application ---
        logger.info(f"Starting Phase 1 (Pattern Application) for {candidate_id}")
        p1_instructions = (
            "Focus on the newly introduced design abstractions. "
            "As an example, if applying a Builder pattern, your goals might be:\n"
            "- create a Builder class\n"
            "- make sure the builder class has `setXXX` methods\n"
            "- the `setXXX` methods should return the builder itself (fluent interface)\n"
            "- there exists a build function in the builder class, which returns the ConcreteClass\n"
        )
        p1_goals = self._generate_goals(p1_instructions, pattern_type, reasoning, core_files_diff)
        p1_checks = self._synthesize_checks(p1_goals, core_files_diff)
        checks.extend(p1_checks)

        # --- Phase 2: Smell Removal ---
        logger.info(f"Starting Phase 2 (Smell Removal) for {candidate_id}")
        p2_instructions = (
            "Focus on eradicating legacy anti-patterns. "
            "For example, if applying a Builder pattern, your goals might be to replace smelly code by:\n"
            "- the object to be built now has a private constructor\n"
            "- no more telescoping constructors"
        )
        p2_goals = self._generate_goals(p2_instructions, pattern_type, reasoning, core_files_diff)
        p2_checks = self._synthesize_checks(p2_goals, core_files_diff)
        checks.extend(p2_checks)

        # --- Phase 3: Call Site Updates ---
        logger.info(f"Starting Phase 3 (Call Site Updates) for {candidate_id}")
        p3_instructions = (
            "Focus on updating downstream dependencies to consume the new abstractions. "
            "For example, if applying a Builder pattern, your goals might be:\n"
            "- legacy `new Class(...)` is replaced by `Builder().setXXX().setXXX().build()` invocations"
        )
        p3_goals = self._generate_goals(p3_instructions, pattern_type, reasoning, call_site_files_diff)
        p3_checks = self._synthesize_checks(p3_goals, call_site_files_diff)
        checks.extend(p3_checks)

        # Adjust Checks
        try:
            adjusted_checks = self.adjust_checks(checks, commit_hash, parent_hash)
        except Exception as e:
            logger.error(f"Failed to adjust checks. {e}")
            adjusted_checks = checks

        return CandidateScorecard(
            candidate_id=candidate_id,
            checks=adjusted_checks,
        )

    def _extract_core_files_diff(self, commit_hash: str, parent_hash: str, verdict: GreenfieldVerdict) -> str:
        """Extracts diff limited to core files identified by the candidate pipeline."""
        diff_texts = []
        
        # Determine core files from diff heuristics (A/M files excluding call sites)
        diff_index = self.repo.commit(parent_hash).diff(self.repo.commit(commit_hash))
        call_sites = set(verdict.modified_preexisting_files)
        
        core_files = set()
        for diff_obj in diff_index:
            path = diff_obj.b_path if diff_obj.b_path else diff_obj.a_path
            if path and path.endswith('.java') and path not in call_sites:
                core_files.add(path)

        for file_path in list(core_files)[:10]:  # Cap to prevent giant context
            diff_text = self.repo.git.diff(parent_hash, commit_hash, "--", file_path)
            diff_texts.append(f"--- File: {file_path} ---\n{diff_text}")
            
        return "\n\n".join(diff_texts)

    def _extract_call_site_diff(self, commit_hash: str, parent_hash: str, verdict: GreenfieldVerdict) -> str:
        """Extracts diff limited strictly to identified call sites."""
        diff_texts = []
        for file_path in verdict.modified_preexisting_files[:10]:
            try:
                diff_text = self.repo.git.diff(parent_hash, commit_hash, "--", file_path)
                diff_texts.append(f"--- Call Site File: {file_path} ---\n{diff_text}")
            except Exception as e:
                logger.warning(f"Could not get diff for call site {file_path}: {e}")
                
        return "\n\n".join(diff_texts)

    def _generate_goals(self, phase_instructions: str, pattern: str, reasoning: str, diff_text: str) -> List[str]:
        if not diff_text.strip():
            return []
            
        prompt = f"""You are building an evaluation scorecard for an AI developer replicating a {pattern} design pattern.
Original developer reasoning for the refactoring: {reasoning}

Here is the Git Diff of the relevant files:
```diff
{diff_text}
```

Task:
Generate a discrete list of structural goals that must be accomplished to achieve the design change.
{phase_instructions}
"""
        llm_with_structure = self.llm.with_structured_output(GoalList)
        try:
            result = llm_with_structure.invoke(prompt)
            return result.goals
        except Exception as e:
            logger.error(f"Failed to generate goals: {e}")
            return []

    def _synthesize_checks(self, goals: List[str], diff_text: str) -> List[CheckItem]:
        if not goals:
            return []
            
        valid_checks = []
        tools_to_bind = [
            ClassMatchingRegexCheck, AntiPatternRemovalCheck, 
            MethodInvocationCheck, InstantiatesClassCheck, 
            HasMethodCheck, ImplementsInterfaceCheck,
            ExtendsClassCheck, HasFieldCheck, HasConstructorVisibilityCheck
        ]
        
        tool_mapping = {tool.__name__: tool for tool in tools_to_bind}
        type_mapping = {
            "ClassMatchingRegexCheck": "class_matching_regex",
            "AntiPatternRemovalCheck": "anti_pattern_removal",
            "MethodInvocationCheck": "method_invocation",
            "InstantiatesClassCheck": "instantiates_class",
            "HasMethodCheck": "has_method",
            "ImplementsInterfaceCheck": "implements_interface",
            "ExtendsClassCheck": "extends_class",
            "HasFieldCheck": "has_field",
            "HasConstructorVisibilityCheck": "has_constructor_visibility"
        }
        
        for goal in goals:
            prompt = f"""You are mapping a natural language refactoring goal into strict structural AST checks.

Goal to enforce: "{goal}"

Relevant Git Diff context for reference:
```diff
{diff_text}
```

Task:
Call one or more of the provided tool schema functions to generate the checks that enforce this goal.
Use generic regex (e.g. `ClassMatchingRegexCheck`) if exact naming wasn't mandated by the goal.
"""
            llm_with_tools = self.llm.bind_tools(tools_to_bind)
            try:
                result = llm_with_tools.invoke(prompt)
                
                for tool_call in result.tool_calls:
                    name = tool_call.get("name")
                    args = tool_call.get("args", {})
                    
                    if name in tool_mapping:
                        args["type"] = type_mapping[name]
                        # Fix LLM omissions
                        if "target_file" not in args and name != "ClassMatchingRegexCheck":
                            args["target_file"] = ".*" # Dummy fallback
                        if "target_class" not in args and name != "ClassMatchingRegexCheck":
                            args["target_class"] = ".*"
                        
                        try:
                            valid_checks.append(tool_mapping[name](**args))
                        except Exception as e:
                            logger.error(f"Failed to instantiate check from tool call {name}: {e}")
            except Exception as e:
                logger.error(f"Failed to synthesize check for goal '{goal}': {e}")
                
        return valid_checks

    def adjust_checks(self, checks: List[CheckItem], commit_hash: str, parent_hash: str) -> List[CheckItem]:
        final_checks = []
        adjusted_count = 0
        check_failed_count = 0

        for check in checks:
            try:
                parent_status = check.check(commit_hash=parent_hash, project_path=self.repo_path)
            except Exception as e:
                logger.error(f"Failed to evaluate lenient check {check.type} on parent: {e}")
                check_failed_count += 1
                continue

            try:
                gold_status = check.check(commit_hash=commit_hash, project_path=self.repo_path)
            except Exception as e:
                logger.error(f"Failed to evaluate lenient check {check.type} on gold: {e}")
                check_failed_count += 1
                continue

            check.impacts_recall = parent_status != gold_status

            if ((parent_status == True and gold_status == False)
                    or (parent_status == False and gold_status == False)):
                adjusted_count += 1
                check.expected = not check.expected

            final_checks.append(check)

        logger.info(f"{adjusted_count} lenient checks were adjusted.")
        logger.info(f"{check_failed_count} lenient checks threw an exception.")
        return final_checks
