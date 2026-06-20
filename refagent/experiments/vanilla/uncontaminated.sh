for f in /Users/abhiram/Documents/TBE/RefactoringAgentProject/Agent4Refactoring/data/uncontaminated/*.json; do
  name=$(basename "$f")
  /Users/abhiram/Documents/TBE/RefactoringAgentProject/ref_venv/bin/python \
    /Users/abhiram/Documents/TBE/RefactoringAgentProject/Agent4Refactoring/refagent/experiments/vanilla/vanilla_LLM.py \
    --json-file "$f" \
    --output-file /Users/abhiram/Documents/TBE/RefactoringAgentProject/Agent4Refactoring/data/results/vanilla_llm_gpt5-jun-7/"$name" \
    --max-items 200
done
