import argparse
import json
import logging
import traceback
from pathlib import Path
from pprint import pprint

import refagent
from refagent.benchmark.design_patterns.scorecard.schema import CandidateScorecard
from refagent.benchmark.design_patterns.scorecard.evaluator import ScorecardEvaluator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_repo_path(candidate_id: str, candidates_file: Path) -> Path:
    """Finds the repository path for a given candidate ID."""
    if not candidates_file.exists():
        raise FileNotFoundError(f"Candidates file not found: {candidates_file}")
    
    with open(candidates_file, "r") as f:
        candidates = json.load(f)
    
    for candidate in candidates:
        if candidate.get("id") == candidate_id:
            return Path(candidate["repo_path"])
    
    raise ValueError(f"Candidate ID {candidate_id} not found in {candidates_file}")

def load_scorecard(candidate_id: str, scorecard_file: Path) -> CandidateScorecard:
    """Finds and loads the CandidateScorecard for a given ID."""
    if not scorecard_file.exists():
        raise FileNotFoundError(f"Scorecard file not found: {scorecard_file}")
    
    with open(scorecard_file, "r") as f:
        for line in f.readlines():
            data = json.loads(line)
            if data.get("candidate_id") == candidate_id:
                return CandidateScorecard.model_validate(data)
    
    raise ValueError(f"Scorecard for Candidate ID {candidate_id} not found in {scorecard_file}")

def main():
    parser = argparse.ArgumentParser(description="Evaluate a Design Pattern Refactoring Scorecard")
    parser.add_argument("--candidate-id", type=str, required=True, help="ID of the candidate to evaluate")
    parser.add_argument("--commit-hash", type=str, required=True, help="The commit SHA to inspect")
    parser.add_argument("--weight-threshold", type=float, required=False, help="The minimum weight for which checks should even run.", default=0.0)
    # parser.add_argument("--scorecard-file", type=str, default="data/design_patterns/scorecard.jsonl", help="Path to scorecard.jsonl")
    # parser.add_argument("--candidates-file", type=str, default="data/design_patterns/aggregated_candidates.json", help="Path to aggregated_candidates.json")
    
    args = parser.parse_args()

    candidates_file = refagent.data_folder.joinpath("design_patterns/aggregated_candidates.json")
    scorecard_file = refagent.data_folder.joinpath("design_patterns/scorecard.jsonl")
    try:
        # 1. Resolve Repo Path
        repo_path = load_repo_path(args.candidate_id, candidates_file)
        logger.info(f"Resolved Repository: {repo_path}")
        
        # 2. Load Scorecard
        scorecard = load_scorecard(args.candidate_id, scorecard_file)
        logger.info(f"Loaded Scorecard with {len(scorecard.checks)} checks")
        
        # 3. run Evaluation
        evaluator = ScorecardEvaluator(
            scorecard=scorecard,
            repo_path=repo_path,
            commit_hash=args.commit_hash,
            weight_threshold=args.weight_threshold
        )
        
        print(f"\nEvaluating Candidate [{args.candidate_id}] on commit [{args.commit_hash}]...\n")
        results = evaluator.evaluate()
        
        # 4. Print Results
        print("="*40)
        print(" EVALUATION RESULTS")
        print("="*40)
        print(f"Overall Recall:    {results['overall_recall']:.2%}")
        print(f"Overall Precision: {results['overall_precision']:.2%}")
        print(f"Total Passed:      {results['total_passed']} / {results['total_checks']}")
        print("-"*40)
        print(" DETAILS:")
        
        for i, detail in enumerate(results['details'], 1):
            status = "[PASS]" if detail['passed'] else "[FAIL]"
            impact = "Recall" if detail['impacts_recall'] else "Precision"
            print(f"{i:2}. {status} {detail['check'].type} (Weight: {detail['weight']}, Impact: {impact})")
            pprint(detail['check'])
        print("="*40)
        
    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        traceback.print_exc()
        exit(1)

if __name__ == "__main__":
    main()
