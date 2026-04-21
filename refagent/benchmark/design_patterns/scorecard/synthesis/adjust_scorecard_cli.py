import argparse
import json
import logging
import os
from pathlib import Path
from typing import List

import refagent
from refagent.benchmark.design_patterns.scorecard.synthesis.create_scorecard import ScoreCardCreator
from refagent.benchmark.design_patterns.pattern_first.mine_from_pattern import _from_output_record
from refagent.benchmark.design_patterns.scorecard.schema import CandidateScorecard

logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="Adjust existing scorecards using gold and parent commits.")
    parser.add_argument("--input", type=str, required=False, help="Path to the scorecard JSONL file",
                        default=refagent.data_folder.joinpath("design_patterns/scorecard.jsonl"))
    parser.add_argument("--aggregated-json", type=str, required=False,
                        help="Path to aggregated_candidates.json",
                        default=refagent.data_folder.joinpath("design_patterns/aggregated_candidates.json"))
    parser.add_argument("--log-level", type=str, default="INFO", help="Logging level")

    args = parser.parse_args()
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)-8s %(message)s")

    input_path = Path(args.input)
    if not input_path.exists():
        logger.error(f"Input file {args.input} does not exist.")
        exit(1)

    aggregated_path = Path(args.aggregated_json)
    if not aggregated_path.exists():
        logger.error(f"Aggregated JSON file {args.aggregated_json} does not exist.")
        exit(1)

    with open(aggregated_path, "r") as f:
        candidates = json.load(f)
    
    # Create a map for quick lookup. IDs might be ints or strings in the JSON.
    candidate_map = {str(c["id"]): c for c in candidates}

    scorecards: List[CandidateScorecard] = []
    logger.info(f"Reading scorecards from {input_path}...")
    with open(input_path, "r") as f:
        for line_num, line in enumerate(f, 1):
            if line.strip():
                try:
                    scorecards.append(CandidateScorecard.model_validate_json(line))
                except Exception as e:
                    logger.error(f"Failed to parse line {line_num}: {e}")

    logger.info(f"Found {len(scorecards)} scorecards to process.")

    adjusted_scorecards: List[CandidateScorecard] = []
    for scorecard in scorecards:
        candidate_id = str(scorecard.candidate_id)
        if candidate_id not in candidate_map:
            logger.warning(f"Candidate ID {candidate_id} not found in aggregated JSON. Skipping adjustment.")
            adjusted_scorecards.append(scorecard)
            continue

        logger.info(f"Adjusting scorecard for candidate: {candidate_id}")
        record = candidate_map[candidate_id]
        
        try:
            # Reconstruct repo_path, birth_info, and verdict.
            # Note: _from_output_record returns (Path, BirthInfo, GreenfieldVerdict)
            repo_path, birth_info, verdict = _from_output_record(record)
        except Exception as e:
            logger.error(f"Failed to parse candidate record for {candidate_id}: {e}")
            adjusted_scorecards.append(scorecard)
            continue

        if not repo_path.exists():
            logger.error(f"Repo path {repo_path} does not exist for candidate {candidate_id}. Skipping.")
            adjusted_scorecards.append(scorecard)
            continue

        # ScoreCardCreator needs an LLM in __init__, but adjust_checks doesn't use it.
        # We pass None here.
        creator = ScoreCardCreator(repo_path, None) # type: ignore
        
        try:
            # Gold commit is the birth commit, parent is its parent.
            adjusted_checks = creator.adjust_checks(
                scorecard.checks,
                birth_info.birth_commit_sha,
                birth_info.parent_sha
            )
            scorecard.checks = adjusted_checks
            adjusted_scorecards.append(scorecard)
            logger.info(f"Successfully adjusted candidate {candidate_id}.")
        except Exception as e:
            logger.error(f"Failed to adjust checks for {candidate_id}: {e}")
            adjusted_scorecards.append(scorecard)

    # Overwrite the input file with adjusted scorecards
    logger.info(f"Saving adjusted scorecards back to {input_path}...")
    with open(input_path, "w") as f:
        for sc in adjusted_scorecards:
            f.write(sc.model_dump_json() + "\n")

    logger.info(f"Done. Processed {len(adjusted_scorecards)} scorecards.")

if __name__ == "__main__":
    main()
