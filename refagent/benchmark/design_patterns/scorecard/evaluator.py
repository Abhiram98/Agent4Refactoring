import re
from pathlib import Path
from typing import Dict, List, Any

from .schema import CandidateScorecard, RefactoringMinerCheck, FilePresenceCheck, ASTCheckBase


class ScorecardResult:
    """Stores the evaluation result of a single check."""
    def __init__(self, passed: bool, weight: float, message: str = ""):
        self.passed = passed
        self.weight = weight
        self.message = message


class ScorecardEvaluator:
    def __init__(self, scorecard: CandidateScorecard, repo_path: Path, rm_refactorings: List[Dict[str, Any]]):
        # TODO: Change this to take only the commit/branch as a param. Then run refactoring miner using refminer_utils.
        """
        :param scorecard: The loaded CandidateScorecard schema object.
        :param repo_path: The root path of the agent's modified repository.
        :param rm_refactorings: A list of refactoring dictionaries output by RefactoringMiner.
                                E.g., [{"type": "Extract Class", "description": "..."}]
        """
        self.scorecard = scorecard
        self.repo_path = Path(repo_path)
        self.rm_refactorings = rm_refactorings

    def evaluate(self) -> Dict[str, Any]:
        """Evaluates all checks and returns a summary of the results."""
        results = []
        total_weight = 0.0
        passed_weight = 0.0

        for check in self.scorecard.checks:
            if isinstance(check, RefactoringMinerCheck):
                result = self._evaluate_rm_check(check)
            elif isinstance(check, FilePresenceCheck):
                result = self._evaluate_file_check(check)
            elif isinstance(check, ASTCheckBase):
                result = self._evaluate_ast_check(check)
            else:
                raise ValueError(f"Unknown check type: {type(check)}")

            total_weight += check.weight
            if result.passed:
                passed_weight += check.weight

            results.append({
                "check_type": check.type,
                "passed": result.passed,
                "message": result.message,
                "weight": check.weight
            })

        recall_score = (passed_weight / total_weight) if total_weight > 0 else 0.0

        return {
            "candidate_id": self.scorecard.candidate_id,
            "overall_recall": recall_score,
            "total_passed": sum(1 for r in results if r["passed"]),
            "total_checks": len(self.scorecard.checks),
            "details": results
        }

    def _evaluate_rm_check(self, check: RefactoringMinerCheck) -> ScorecardResult:
        """Checks if the target RM operation and description regex match any RM output."""
        pattern = re.compile(check.description_regex)
        
        for rm_op in self.rm_refactorings:
            if rm_op.get("type", "") == check.operation_type:
                description = rm_op.get("description", "")
                if pattern.search(description):
                    return ScorecardResult(
                        passed=True, 
                        weight=check.weight, 
                        message=f"Matched operation '{check.operation_type}' and description regex."
                    )
        
        return ScorecardResult(
            passed=False, 
            weight=check.weight, 
            message=f"Failed to find RM operation '{check.operation_type}' matching regex '{check.description_regex}'."
        )

    def _evaluate_file_check(self, check: FilePresenceCheck) -> ScorecardResult:
        """Checks if a file matching the regex appears (or is absent) anywhere in the repo subtree."""
        import re
        pattern = re.compile(check.file_regex)
        
        file_exists = False
        for path in self.repo_path.rglob("*"):
            # Only match against the filename, not the full path, consistent with how the regex is prompted
            if path.is_file() and pattern.search(path.name):
                file_exists = True
                break

        if check.expected_state == "exists":
            if file_exists:
                return ScorecardResult(passed=True, weight=check.weight, message=f"Found file matching regex '{check.file_regex}'.")
            else:
                return ScorecardResult(passed=False, weight=check.weight, message=f"File matching '{check.file_regex}' was expected but not found.")
        elif check.expected_state == "absent":
            if file_exists:
                return ScorecardResult(passed=False, weight=check.weight, message=f"File matching '{check.file_regex}' is present, but should be absent.")
            else:
                return ScorecardResult(passed=True, weight=check.weight, message=f"File matching '{check.file_regex}' is correctly absent.")
        else:
            return ScorecardResult(passed=False, weight=check.weight, message=f"Invalid expected state: {check.expected_state}")

    def _evaluate_ast_check(self, check: ASTCheckBase) -> ScorecardResult:
        import refagent.benchmark.design_patterns.scorecard.ast_checks as ast_checks
        
        # Registry mapping schema types to Evaluator classes
        evaluator_map = {
            "implements_interface": ast_checks.ImplementsInterfaceCheckEvaluator,
            "has_method": ast_checks.HasMethodCheckEvaluator,
            # Additional maps can be easily added as the classes are written
        }
        
        if check.type in evaluator_map:
            eval_class = evaluator_map[check.type]
            evaluator = eval_class(check)
            
            # The evaluator logic handles the 'expected' condition internally
            passed = evaluator.evaluate(self.repo_path, check.target_file, getattr(check, 'target_class', None))
            
            if passed:
                return ScorecardResult(True, check.weight, f"AST check '{check.type}' passed.")
            else:
                return ScorecardResult(False, check.weight, f"AST check '{check.type}' failed.")
        else:
            return ScorecardResult(False, 0.0, f"Evaluator for AST check '{check.type}' not yet implemented.")
