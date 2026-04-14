import argparse
import json
from pathlib import Path
from langchain_openai import ChatOpenAI
from refagent.benchmark.design_patterns.scorecard.synthesis.create_scorecard import ScoreCardCreator
from refagent.benchmark.design_patterns.pattern_first.mine_from_pattern import _from_output_record

def main():
    parser = argparse.ArgumentParser(description="Generate an Evaluation Scorecard for a Design Pattern Refactoring")
    parser.add_argument("--repo-path", type=str, required=True, help="Path to the local git repository")
    parser.add_argument("--candidate-id", type=str, required=True, help="Unique ID for the scorecard candidate")
    parser.add_argument("--aggregated-json", type=str, required=True, help="Path to aggregated_candidates.json file")
    
    parser.add_argument("--rm-json", type=str, required=True, help="Path to json file containing RefactoringMiner output array")
    
    parser.add_argument("--output", type=str, default="scorecard.json", help="Path to save the generated scorecard")
    parser.add_argument("--model", type=str, default="gpt-4o-mini", help="LangChain LLM model string to use")
    
    parser.add_argument("--max-call-sites", type=int, default=3, help="Max call-site files to sample for AST integration checks")
    
    parser.add_argument("--disable-file-checks", action="store_true", help="Disable generating File Presence checks")
    parser.add_argument("--disable-rm-checks", action="store_true", help="Disable generating Refactoring Miner checks")
    parser.add_argument("--disable-ast-checks", action="store_true", help="Disable generating AST structural checks")

    args = parser.parse_args()

    # Load RM Output
    with open(args.rm_json, "r") as f:
        rm_output = json.load(f)

    # Load aggregated candidates and find our target
    with open(args.aggregated_json, "r") as f:
        candidates = json.load(f)
        
    target_record = next((c for c in candidates if c["id"] == args.candidate_id), None)
    if not target_record:
        print(f"Error: Candidate ID {args.candidate_id} not found in {args.aggregated_json}")
        exit(1)

    # Reconstruct BirthInfo and GreenfieldVerdict through the parser
    # We pass target_record directly to _from_output_record
    parsed_repo_path, birth_info, verdict = _from_output_record(target_record)

    # Init LLM
    print(f"Initializing ChatOpenAI with model {args.model}")
    llm = ChatOpenAI(model=args.model, temperature=0.0)
    
    repo_path = Path(args.repo_path)
    if not repo_path.exists():
        print(f"Error: Repository path {repo_path} does not exist.")
        exit(1)
        
    creator = ScoreCardCreator(repo_path, llm)

    print(f"\nGenerataing Scorecard for Candidate [{args.candidate_id}]...")
    scorecard = creator.create_scorecard(
        candidate_id=args.candidate_id,
        birth_info=birth_info,
        verdict=verdict,
        rm_output=rm_output,
        max_call_sites=args.max_call_sites,
        run_file_checks=not args.disable_file_checks,
        run_rm_checks=not args.disable_rm_checks,
        run_ast_checks=not args.disable_ast_checks
    )

    # Save Data
    out_path = Path(args.output)
    out_path.write_text(scorecard.model_dump_json(indent=2))
    
    print("\n--- Summary ---")
    print(f"Total Checks Generated: {len(scorecard.checks)}")
    print(f"Scorecard JSON saved to: {out_path.absolute()}")

if __name__ == "__main__":
    main()
