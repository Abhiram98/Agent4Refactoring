OUTPUT_DIR=vanilla_llm_o4-mini-jun-20
for f in /Users/abhiram/Documents/TBE/RefactoringAgentProject/Agent4Refactoring/data/uncontaminated/*.json; do
  name=$(basename "$f")
  /Users/abhiram/Documents/TBE/RefactoringAgentProject/ref_venv/bin/python \
    /Users/abhiram/Documents/TBE/RefactoringAgentProject/Agent4Refactoring/refagent/experiments/vanilla/vanilla_LLM.py \
    --json-file "$f" \
    --output-file /Users/abhiram/Documents/TBE/RefactoringAgentProject/Agent4Refactoring/data/results/"$OUTPUT_DIR"/"$name" \
    --max-items 200
done
