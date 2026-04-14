import logging
from json import JSONDecodeError
from pathlib import Path
from typing import List, Dict, Any, Optional, Literal
from git import Repo
import re
import json

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from refagent.benchmark.design_patterns.scorecard.schema import (
    CandidateScorecard,
    FilePresenceCheck,
    RefactoringMinerCheck,
    CheckItem
)
from refagent.benchmark.design_patterns.pattern_first.models import BirthInfo, GreenfieldVerdict
from refagent.utils.refminer_utils import default_runner
import refagent.refactoring_types.refactorings as refactoring_types

logger = logging.getLogger(__name__)


# Temporary wrapper models for LangChain's structured output parser limitation
class FileCheckList(BaseModel):
    checks: List[FilePresenceCheck] = Field(description="List of file presence/absence checks")


class RMCheckList(BaseModel):
    checks: List[RefactoringMinerCheck] = Field(description="List of Refactoring Miner checks")


class ASTCheckList(BaseModel):
    checks: List[CheckItem] = Field(description="List of parameterized AST structural checks")


class ScoreCardCreator:
    def __init__(self, repo_path: Path, llm: ChatOpenAI):
        self.repo = Repo(repo_path)
        self.llm = llm

    def create_scorecard(self, candidate_id: str, birth_info: BirthInfo, verdict: GreenfieldVerdict,
                         max_call_sites: int = 3,
                         run_file_checks: bool = True, run_rm_checks: bool = True, run_ast_checks: bool = True) -> CandidateScorecard:
        """Generates a CandidateScorecard by analyzing the commit diff and RM output via an LLM."""
        
        pattern_type = birth_info.pattern_instance.pattern.value if hasattr(birth_info.pattern_instance.pattern, "value") else str(birth_info.pattern_instance.pattern)
        detection_reasoning = birth_info.pattern_instance.reasoning or ""
        commit_hash = birth_info.birth_commit_sha
        parent_hash = birth_info.parent_sha

        # Step 1: File Checks
        file_checks = []
        if run_file_checks:
            added_diff_text = self._extract_diff_text(commit_hash, parent_hash, 'A')
            file_checks.extend(self._generate_file_checks(pattern_type, detection_reasoning, added_diff_text, "ADDED"))
            
            deleted_diff_text = self._extract_diff_text(commit_hash, parent_hash, 'D')
            file_checks.extend(self._generate_file_checks(pattern_type, detection_reasoning, deleted_diff_text, "DELETED"))

        # Step 2: RM Checks
        rm_checks = []
        rm_output = default_runner.run(project_path=self.repo.working_dir, commit_hash=commit_hash)
        if run_rm_checks or run_ast_checks: 
            # RM output is needed for AST context filtering too
            if run_rm_checks:
                rm_checks = self._generate_rm_checks(pattern_type, detection_reasoning, rm_output)

        # Step 3: AST Checks
        ast_checks = []
        if run_ast_checks:
            ast_contexts = self._extract_ast_context(commit_hash, parent_hash, file_checks, rm_output, verdict, max_call_sites)
            for ctx in ast_contexts:
                res = self._generate_ast_checks(pattern_type, detection_reasoning, ctx)
                ast_checks.extend(res)

        # Combine
        return CandidateScorecard(
            candidate_id=candidate_id,
            checks=file_checks + rm_checks + ast_checks
        )

    def _extract_diff_text(self, commit_hash: str, parent_hash: str, change_type: Literal["A", "D"]) -> Optional[str]:
        """Extracts diff info for files of a specific change type ('A' or 'D')."""
        diff_index = self.repo.commit(parent_hash).diff(self.repo.commit(commit_hash))
        target_diffs = list(diff_index.iter_change_type(change_type))

        status_label = "ADDED" if change_type == 'A' else "DELETED"
        if not target_diffs:
            return None

        exceeds_threshold = len(target_diffs) > 10
        output = []

        for diff_obj in target_diffs:
            b_path = diff_obj.b_path if diff_obj.b_path else diff_obj.a_path
            output.append(f"--- {status_label} FILE: {b_path} ---")

            try:
                blob = diff_obj.b_blob if diff_obj.b_blob else diff_obj.a_blob
                if blob is not None:
                    content = blob.data_stream.read().decode('utf-8', errors='replace')
                    lines = content.splitlines()

                    if exceeds_threshold:
                        lines = lines[:50]
                        output.extend(lines)
                        output.append("... [TRUNCATED DUE TO FILE LIMIT HEURISTIC] ...")
                    else:
                        output.extend(lines)
                else:
                    output.append("[No blob content available]")
            except Exception as e:
                output.append(f"[Error reading file content: {e}]")

            output.append("")

        return "\n".join(output)

    def _generate_file_checks(self, pattern_type: str, reasoning: str, diff_text: Optional[str], status: str) -> List[FilePresenceCheck]:
        if diff_text is None:
            return []
            
        existence_verb = "exist" if status == "ADDED" else "be absent"
        expected_val: Literal["exists", "absent"] = "exists" if status == "ADDED" else "absent"

        prompt = f"""You are generating an evaluation scorecard for an AI developer replicating a {pattern_type} design pattern.
The target outcome reasoning is: {reasoning}

Here is the set of {status} files from the original developer's commit. 
If there were >10 files, only the first 50 lines of each are included:
```
{diff_text}
```

Task:
Identify which of these files MUST {existence_verb} to fulfill the core architecture of the {pattern_type}.
Return a structured list of JSON Objects with the following keys - "file_regex" and "weight". 
Assign higher weights (2.0 or 3.0) to central interfaces/classes, and lower weights (0.5 or 1.0) to tests or secondary helpers.
The `file_regex` should be a regular expression matching the required base filename (e.g. '.*TableBuilder.*\.java'). Be careful to properly escape dots and wildcards.
"""
        result = self.llm.invoke(prompt)
        try:
            files_and_weights = json.loads(result.content)
        except JSONDecodeError:
            logger.error("Failed to parse JSON")
            return []
        checks = [FilePresenceCheck(weight=i['weight'], file_regex=i["file_regex"],
                           expected=True, expected_state=expected_val, type="file_presence") for i in files_and_weights]
        return checks

    def _generate_rm_checks(self, pattern_type: str, reasoning: str, rm_output: List[refactoring_types.RefminerOut]) -> List[
        RefactoringMinerCheck]:
        # Serialize the Pydantic models for the LLM
        rm_text = "\n".join([f"{r.type}: {r.description}." for r in rm_output])

        prompt = f"""You are generating an evaluation scorecard for an AI developer replicating a {pattern_type} design pattern.
The target outcome reasoning is: {reasoning}

Here is the condensed RefactoringMiner output representing the original developer's actions:
```json
{rm_text}
```

Task:
Select the structural operations that form the core of the newly introduced pattern and return a structured list of RefactoringMinerChecks.
CRITICAL INSTRUCTION: To account for the AI agent using slightly different naming conventions than the original developer, rewrite the `description_regex` loosely based on the original `description`. 
Replace specific developer identifiers with wildcards `.*?` where appropriate, but try to strictly match the operation target/base intent. 
Assign a weight (0.5 to 3.0) based on how critical this operation is to the {pattern_type}.
"""
        structured_llm = self.llm.with_structured_output(RMCheckList)
        result = structured_llm.invoke(prompt)
        return result.checks if result else []

    def _extract_ast_context(self, commit_hash: str, parent_hash: str, file_checks: List[FilePresenceCheck], 
                             rm_output: List[refactoring_types.RefminerOut], verdict: GreenfieldVerdict, max_call_sites: int) -> List[Dict[str, str]]:
        """Selects 'Important Files' and extracts their Diff and Final State."""
        diff_index = self.repo.commit(parent_hash).diff(self.repo.commit(commit_hash))
        
        selected_files = set()
        
        # 1. Add files from FilePresence checks
        for req in file_checks:
            try:
                pattern = re.compile(req.file_regex)
            except re.error:
                continue # Skip invalid regexes generated by LLM
                
            for diff_obj in diff_index:
                path = diff_obj.b_path if diff_obj.b_path else diff_obj.a_path
                # Match against the basename to be consistent with how the evaluator works
                if path and pattern.search(path.split('/')[-1]): 
                    selected_files.add(path)
                    
        # 2. Add files from RM checks
        for rm in rm_output:
            for loc in rm.left_side_locations + rm.right_side_locations:
                if loc.file_path:
                    selected_files.add(loc.file_path)
            
        # 3. Add explicit call site files defined by the GreenfieldVerdict
        call_sites = verdict.modified_preexisting_files[:max_call_sites]
        for cf in call_sites:
            selected_files.add(cf)
            
        contexts = []
        for file_path in selected_files:
            # Get Context Diff
            diff_text = self.repo.git.diff(parent_hash, commit_hash, "--", file_path)
            
            # Get Post-refactoring content
            try:
                blob = self.repo.commit(commit_hash).tree / file_path
                content = blob.data_stream.read().decode('utf-8', errors='replace')
                if len(content) > 15000:
                    content = content[:15000] + "\n... [TRUNCATED CONTENT HEURISTIC] ..."
            except KeyError:
                content = "[File Deleted]"
                
            contexts.append({
                "target_file": file_path,
                "diff": diff_text,
                "content": content
            })
            
        return contexts

    def _generate_ast_checks(self, pattern_type: str, reasoning: str, ctx: Dict[str, str]) -> List[CheckItem]:
        prompt = f"""You are an evaluator assessing whether an agent successfully implemented a {pattern_type}.
Reasoning for the developer's original refactoring: {reasoning}

We are evaluating the following specific file: {ctx['target_file']}

What changed (Git Diff):
```diff
{ctx['diff']}
```

Final File Structure (Post-refactoring):
```java
{ctx['content']}
```

Task:
Return a list of parameterized structural constraints this file MUST meet to satisfy the design pattern integration (or the pattern itself).
Use predefined schemas like 'ImplementsInterfaceCheck', 'HasMethodCheck', 'InstantiatesClassCheck', or 'HasFieldCheck'. 
ONLY use 'CustomDynamicASTCheck' if the structural requirement is completely impossible to express natively.
Remember to aggressively use the `expected: false` parameter if the developer DELETED or REMOVED an old method, field, or constructor that the AI must also delete. 
Assign strict weights based on importance.
"""
        structured_llm = self.llm.with_structured_output(ASTCheckList)
        result = structured_llm.invoke(prompt)
        
        # Filter to make sure it only returns AST checks (the schema technically allows all checks)
        valid_checks = []
        if result:
            for check in result.checks:
                if check.type not in ["refactoring_miner", "file_presence"]:
                    valid_checks.append(check)
        return valid_checks

