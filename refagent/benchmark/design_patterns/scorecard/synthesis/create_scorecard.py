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
    CheckItem,
    ImplementsInterfaceCheck,
    ExtendsClassCheck,
    HasMethodCheck,
    HasConstructorVisibilityCheck,
    HasFieldCheck,
    InstantiatesClassCheck
)
from refagent.benchmark.design_patterns.pattern_first.models import BirthInfo, GreenfieldVerdict
from refagent.utils.refminer_utils import default_runner
import refagent.refactoring_types.refactorings as refactoring_types

logger = logging.getLogger(__name__)


class ASTContext(BaseModel):
    target_file: str
    diff: str
    content: str


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
            logger.info(f"Running file checks for {candidate_id}...")
            added_diff_text = self._extract_diff_text(commit_hash, parent_hash, 'A')
            file_checks.extend(self._generate_file_checks(pattern_type, detection_reasoning, added_diff_text, "ADDED"))
            
            deleted_diff_text = self._extract_diff_text(commit_hash, parent_hash, 'D')
            file_checks.extend(self._generate_file_checks(pattern_type, detection_reasoning, deleted_diff_text, "DELETED"))

        # Step 2: RM Checks
        rm_checks = []
        rm_output = default_runner.run(project_path=self.repo.working_dir, commit_hash=commit_hash)
        logger.info(f"Found {len(rm_output)} refactoring changes in the commit.")

        if run_rm_checks:
            logger.info("Running RM checks...")
            rm_checks = self._generate_rm_checks(pattern_type, detection_reasoning, rm_output)

        # Step 3: AST Checks
        ast_checks = []
        if run_ast_checks:
            ast_contexts = self._extract_ast_context(commit_hash, parent_hash, file_checks, rm_output, verdict, max_call_sites)
            for ctx in ast_contexts:
                logger.info(f"Generating AST context for {ctx.target_file}")
                res = self._generate_ast_checks(pattern_type, detection_reasoning, ctx)
                ast_checks.extend(res)

        # Combine
        return CandidateScorecard(
            candidate_id=candidate_id,
            checks=self.adjust_checks(
                file_checks + rm_checks + ast_checks,
                commit_hash,
                parent_hash
            )
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
        rm_text = "\n".join([f"refactoring number {i}: {r.type}- {r.description}." for i, r in enumerate(rm_output)])

        prompt = f"""You are generating an evaluation scorecard for an developer aiming to introduce a design pattern to existing code. 
        In this case, the developer would like to introduce the {pattern_type} design pattern.
        The golden commit performed the following changes: {reasoning}.

Here is the condensed RefactoringMiner output representing the original developer's actions (golden commit):
```json
{rm_text}
```

Task:
Select the structural operations that form the core of the newly introduced pattern and return 
a list of JSON Objects with the following keys - "refactoring_number", "description_regex", and "weight".
CRITICAL INSTRUCTION: To account for the AI agent using slightly different naming conventions than the original developer, 
write the `description_regex` loosely based on the original `description`. 
Replace specific developer identifiers with wildcards `.*?` where appropriate, but try to strictly match the operation target/base intent. 
Assign a weight (0.5 to 3.0) based on how critical this operation is to the {pattern_type}.
"""
        result = self.llm.invoke(prompt)
        checks = []
        for i in json.loads(result.content):
            weight = i['weight']
            description_regex = i['description_regex']
            refactoring_number = int(i['refactoring_number'])
            refminer_operation = rm_output[refactoring_number]
            checks.append(
                RefactoringMinerCheck(
                    weight=weight,
                    description_regex=description_regex,
                    operation_type=refminer_operation.type,
                    ref_operation=refminer_operation,
                    type="refactoring_miner"
                )
            )

        return checks


    def _extract_ast_context(self, commit_hash: str, parent_hash: str, file_checks: List[FilePresenceCheck], 
                             rm_output: List[refactoring_types.RefminerOut], verdict: GreenfieldVerdict, max_call_sites: int) -> List[ASTContext]:
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
            for loc in rm.leftSideLocations + rm.rightSideLocations:
                if loc.filePath:
                    selected_files.add(loc.filePath)
            
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
                
            contexts.append(ASTContext(
                target_file=file_path,
                diff=diff_text,
                content=content
            ))
            
        return contexts

    def _generate_ast_checks(self, pattern_type: str, reasoning: str, ctx: ASTContext) -> List[CheckItem]:
        prompt = f"""You are an evaluator assessing whether an agent successfully implemented a {pattern_type} design pattern.
Reasoning for the developer's original refactoring: {reasoning}

We are evaluating the following specific file: {ctx.target_file}

What changed (Git Diff):
```diff
{ctx.diff}
```

Task:
Call the provided tools to emit the parameterized structural constraints this file MUST meet to satisfy the design pattern integration (or the pattern itself).
Remember to aggressively use the `expected=False` parameter if the developer DELETED or REMOVED an old method, field, or constructor that the AI must also delete. 
Assign strict weights (0.5 to 3.0) based on importance.
"""
        
        tools_to_bind = [
            ImplementsInterfaceCheck, ExtendsClassCheck, HasMethodCheck,
            HasConstructorVisibilityCheck, HasFieldCheck, InstantiatesClassCheck
        ]
        
        llm_with_tools = self.llm.bind_tools(tools_to_bind)
        result = llm_with_tools.invoke(prompt)
        
        valid_checks = []
        target_file_basename = ctx.target_file.split('/')[-1]
        
        tool_mapping = {
            "ImplementsInterfaceCheck": ImplementsInterfaceCheck,
            "ExtendsClassCheck": ExtendsClassCheck,
            "HasMethodCheck": HasMethodCheck,
            "HasConstructorVisibilityCheck": HasConstructorVisibilityCheck,
            "HasFieldCheck": HasFieldCheck,
            "InstantiatesClassCheck": InstantiatesClassCheck
        }
        
        type_mapping = {
            "ImplementsInterfaceCheck": "implements_interface",
            "ExtendsClassCheck": "extends_class",
            "HasMethodCheck": "has_method",
            "HasConstructorVisibilityCheck": "has_constructor_visibility",
            "HasFieldCheck": "has_field",
            "InstantiatesClassCheck": "instantiates_class"
        }
        
        # Parse the tool calls and instantiate the actual schema objects
        for tool_call in result.tool_calls:
            name = tool_call.get("name")
            args = tool_call.get("args", {})
            
            # Manually inject fields the LLM might mess up or shouldn't be fully trusted on
            args["target_file"] = target_file_basename
            
            if name in tool_mapping:
                args["type"] = type_mapping[name]
                try:
                    valid_checks.append(tool_mapping[name](**args))
                except Exception as e:
                    logger.error(f"Failed to instantiate check from tool call {name}: {e}")
                    
        return valid_checks

    def adjust_checks(self, checks: List[CheckItem],
                      commit_hash: str, parent_hash: str) -> List[CheckItem]:
        # Run the check against the previous commit and the gold commit.
        #  Note the status. Possible status are:
        #  Pass -> Fail. Fail -> Pass. Pass -> Pass. Fail -> Fail.
        #  Changing status should impact the recall. i.e., `check.impacts_recall = True`.
        #  For Pass -> Fail, check.expected should be inverted.
        #  For Fail -> Fail, check.expected should be inverted.
        #  Same status checks should be used to compute precision. i.e., `check.impacts_recall = False`

        final_checks = []
        gold_rminer = default_runner.run(project_path=self.repo, commit_hash=commit_hash)
        parent_rminer = []
        adjusted_count = 0
        check_failed_count = 0

        for check in checks:
            try:
                parent_status = check.check(commit_hash=parent_hash,
                                            project_path=self.repo,
                                            rm_refactorings=parent_rminer)
            except Exception as e:
                logger.error(f"Failed to evaluate check {check.name}: {e}")
                check_failed_count += 1
                continue

            try:
                gold_status = check.check(commit_hash=commit_hash,
                                          project_path=self.repo,
                                          rm_refactorings=gold_rminer)
            except Exception as e:
                logger.error(f"Failed to evaluate check {check.name}: {e}")
                check_failed_count += 1
                continue

            # If the status of the check changes, then it impacts recall.
            # Else, it impacts precision -- these are likely code components that developer chose not to change.
            check.impacts_recall = parent_status != gold_status

            if ((parent_status == True and gold_status == False)
                    or (parent_status == False and gold_status == False)):
                # Invert the expected status.
                adjusted_count += 1
                check.expected = not check.expected

            final_checks.append(check)

        logger.info(f"{adjusted_count} checks were adjusted.")
        logger.info(f"{check_failed_count} checks threw an exception.")
        return final_checks

