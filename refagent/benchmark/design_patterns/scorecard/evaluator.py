import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

from .schema import CandidateScorecard

logger = logging.getLogger(__name__)


class ScorecardEvaluator:
    def __init__(
        self,
        scorecard: CandidateScorecard,
        repo_path: Path,
        commit_hash: str,
        rm_refactorings: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        :param scorecard:        The loaded CandidateScorecard schema object.
        :param repo_path:        The root path of the local git repository.
        :param commit_hash:      The commit SHA to evaluate against.
        :param rm_refactorings:  Optional pre-run RefactoringMiner output.
                                 When None, any RefactoringMinerCheck will run
                                 RM internally on the first call.
        """
        self.scorecard = scorecard
        self.repo_path = Path(repo_path)
        self.commit_hash = commit_hash
        self.rm_refactorings = rm_refactorings

    def evaluate(self) -> Dict[str, Any]:
        """
        Evaluates all checks and returns a summary of the results.

        Each check's .check() method is called with the commit hash, repo path,
        and optional pre-run RM output.  Recall and precision scores are computed
        separately based on each check's impacts_recall flag.
        """
        results = []
        recall_total = 0.0
        recall_passed = 0.0
        precision_total = 0.0
        precision_passed = 0.0

        for check in self.scorecard.checks:
            try:
                passed = check.check(self.commit_hash, self.repo_path, self.rm_refactorings)
            except NotImplementedError:
                logger.warning(f"Check '{check.type}' is not yet implemented; skipping.")
                passed = False
            except Exception as e:
                logger.error(f"Check '{check.type}' raised an unexpected error: {e}")
                passed = False

            if check.impacts_recall:
                recall_total += check.weight
                if passed:
                    recall_passed += check.weight
            else:
                precision_total += check.weight
                if passed:
                    precision_passed += check.weight

            results.append({
                "check_type": check.type,
                "passed": passed,
                "weight": check.weight,
                "impacts_recall": check.impacts_recall,
            })

        recall_score = (recall_passed / recall_total) if recall_total > 0 else 0.0
        precision_score = (precision_passed / precision_total) if precision_total > 0 else 0.0

        return {
            "candidate_id": self.scorecard.candidate_id,
            "overall_recall": recall_score,
            "overall_precision": precision_score,
            "total_passed": sum(1 for r in results if r["passed"]),
            "total_checks": len(results),
            "details": results,
        }
