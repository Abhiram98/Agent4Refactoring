import logging
from json import JSONDecodeError
from pathlib import Path
from typing import List, Literal, Optional
from git import Repo
import re
import json

from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from refagent.benchmark.design_patterns.scorecard.schema import (
    CandidateScorecard,
    CheckItem
)
from refagent.benchmark.design_patterns.scorecard.checks.lenient_ast_checks import (
    ClassMatchingRegexCheck,
    AntiPatternRemovalCheck
)
from refagent.benchmark.design_patterns.pattern_first.models import BirthInfo, GreenfieldVerdict
from refagent.utils.refminer_utils import default_runner

logger = logging.getLogger(__name__)

class ASTContext(BaseModel):
    target_file: str
    diff: str
    content: str


class LenientScoreCardCreator:
    def __init__(self, repo_path: Path, llm: ChatOpenAI):
        self.repo = Repo(repo_path)
        self.repo_path = repo_path
        self.llm = llm

    def create_scorecard(self, candidate_id: str, birth_info: BirthInfo, verdict: GreenfieldVerdict,
                         max_call_sites: int = 3) -> CandidateScorecard:
        """Generates a lenient CandidateScorecard by focusing on API contracts rather than strict AST replication."""
        
        pattern_type = birth_info.pattern_instance.pattern.value if hasattr(birth_info.pattern_instance.pattern, "value") else str(birth_info.pattern_instance.pattern)
        detection_reasoning = birth_info.pattern_instance.reasoning or ""
        commit_hash = birth_info.birth_commit_sha
        parent_hash = birth_info.parent_sha

        # Determine context files
        diff_contexts = self._extract_modified_contexts(commit_hash, parent_hash, verdict, max_call_sites)
        
        checks: List[CheckItem] = []
        for ctx in diff_contexts:
            logger.info(f"Generating lenient AST checks for {ctx.target_file}")
            res = self._generate_lenient_checks(pattern_type, detection_reasoning, ctx)
            checks.extend(res)

        try:
            adjusted_checks = self.adjust_checks(checks, commit_hash, parent_hash)
        except Exception as e:
            logger.error(f"Failed to adjust checks. {e}")
            adjusted_checks = checks

        return CandidateScorecard(
            candidate_id=candidate_id,
            checks=adjusted_checks,
        )

    def _extract_modified_contexts(self, commit_hash: str, parent_hash: str, verdict: GreenfieldVerdict, max_call_sites: int) -> List[ASTContext]:
        """Extracts Diff and Content of specifically interesting modified files without strictly relying on RM"""
        selected_files = set()
        
        # 1. Add files from greenfield call sites
        call_sites = verdict.modified_preexisting_files[:max_call_sites]
        for cf in call_sites:
            selected_files.add(cf)
            
        # 2. Extract key changed files directly from Git Diff heuristics (ignore very small changes)
        diff_index = self.repo.commit(parent_hash).diff(self.repo.commit(commit_hash))
        for diff_obj in diff_index.iter_change_type('A'):
            if diff_obj.b_path and diff_obj.b_path.endswith('.java'):
                selected_files.add(diff_obj.b_path)
        for diff_obj in diff_index.iter_change_type('M'):
            if diff_obj.b_path and diff_obj.b_path.endswith('.java'):
                selected_files.add(diff_obj.b_path)
                
        # To avoid blowing up LLM context, we might safely limit 'selected_files' if it's too large
        contexts = []
        for file_path in list(selected_files)[:10]:  # Arbitrary limit to stay sane
            diff_text = self.repo.git.diff(parent_hash, commit_hash, "--", file_path)
            if not diff_text.strip():
                continue
                
            try:
                blob = self.repo.commit(commit_hash).tree / file_path
                content = blob.data_stream.read().decode('utf-8', errors='replace')
                if len(content) > 15000:
                    content = content[:15000] + "\n... [TRUNCATED CONTENT] ..."
            except KeyError:
                content = "[File Deleted]"
                
            contexts.append(ASTContext(
                target_file=file_path,
                diff=diff_text,
                content=content
            ))
            
        return contexts

    def _generate_lenient_checks(self, pattern_type: str, reasoning: str, ctx: ASTContext) -> List[CheckItem]:
        prompt = f"""You are generating an evaluation scorecard for an AI developer replicating a {pattern_type} design pattern.
The target outcome reasoning is: {reasoning}

We are evaluating the following specific file: {ctx.target_file}

What changed (Git Diff):
```diff
{ctx.diff}
```

Task:
Call the provided tools to emit GOAL-ORIENTED structural constraints for this file.
DO NOT demand exact class names (like `TableBuilderBase`). Instead, use `ClassMatchingRegexCheck` to use duck-typing. For example, if a `Builder` was introduced, ensure *any* class matching `.*Builder.*` has a `build` method.
If the diff shows that a legacy anti-pattern was removed (e.g., deleted a constructor with 12 parameters, or removed old setters like `setRpcTimeout`), use the `AntiPatternRemovalCheck`.
Assign strict weights (0.5 to 3.0) based on importance.
"""
        
        tools_to_bind = [
            ClassMatchingRegexCheck, AntiPatternRemovalCheck
        ]
        
        llm_with_tools = self.llm.bind_tools(tools_to_bind)
        result = llm_with_tools.invoke(prompt)
        
        valid_checks = []
        target_file_basename = ctx.target_file.split('/')[-1]
        
        tool_mapping = {
            "ClassMatchingRegexCheck": ClassMatchingRegexCheck,
            "AntiPatternRemovalCheck": AntiPatternRemovalCheck
        }
        
        type_mapping = {
            "ClassMatchingRegexCheck": "class_matching_regex",
            "AntiPatternRemovalCheck": "anti_pattern_removal"
        }
        
        for tool_call in result.tool_calls:
            name = tool_call.get("name")
            args = tool_call.get("args", {})
            
            if name == "AntiPatternRemovalCheck":
                args["target_file"] = target_file_basename
                # LLM often forgets target_class or generates it incorrectly for AntiPattern check.
                # Try our best to deduce it, or let the LLM dict pass through.
                if "target_class" not in args:
                    args["target_class"] = target_file_basename.replace('.java', '')
                    
            if name in tool_mapping:
                args["type"] = type_mapping[name]
                try:
                    valid_checks.append(tool_mapping[name](**args))
                except Exception as e:
                    logger.error(f"Failed to instantiate lenient check from tool call {name}: {e}")
                    
        return valid_checks

    def adjust_checks(self, checks: List[CheckItem],
                      commit_hash: str, parent_hash: str) -> List[CheckItem]:
        final_checks = []
        # Run the check against the previous commit and the gold commit.
        adjusted_count = 0
        check_failed_count = 0

        for check in checks:
            try:
                parent_status = check.check(commit_hash=parent_hash,
                                            project_path=self.repo_path)
            except Exception as e:
                logger.error(f"Failed to evaluate lenient check {check.type} on parent: {e}")
                check_failed_count += 1
                continue

            try:
                gold_status = check.check(commit_hash=commit_hash,
                                          project_path=self.repo_path)
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
