import json
import os
import argparse
from typing import List, Dict, Optional, Set, Any

import refagent


from refagent.benchmark.design_patterns.task.schema import RefactoringTask, TaskPrompt, TaskTier
from refagent.utils.project_manager import EvalProject
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from pydantic import ValidationError

# Configuration
INPUT_FILE = str(refagent.data_folder.joinpath("design_patterns/aggregated_candidates.json"))
OUTPUT_FILE = str(refagent.data_folder.joinpath("design_patterns/tasks.json"))

class TaskGenerator:
    """Handles LLM-based prompt generation for different task tiers."""
    
    def __init__(self, model_name: str = "gpt-5-mini"):
        self.llm = ChatOpenAI(model=model_name, temperature=1)
        
    def generate_tier_1(self, diff: str, seed_file: str) -> str:
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are an expert Java developer. Based on the provided git diff, "
                       "generate direct, mechanical, step-by-step structural instructions "
                       "for a refactoring agent. Describe the high level goal (to apply a design pattern) and exactly how to do so. "
                       "Describe which classes to create, which methods to move/rename, and constructor changes. "
                       "Do not explain principles. Be concise. Limit to 3 sentences."),
            ("user", "Diff:\n{diff}\n\nSeed File: {seed_file}")
        ])
        chain = prompt | self.llm
        res = chain.invoke({"diff": diff[:10000], "seed_file": seed_file})
        return res.content

    def generate_tier_2(self, pattern: str, seed_file: str, reasoning: str) -> str:
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a software architect. Generate a high-level directive to "
                       "apply a specific design pattern to a codebase. "
                       "Specify the pattern and the target classes. "
                       "Focus on the architectural intent. "
                       "Do not include information about downstream classes/files "
                       "that need to be modified after changing the initial file to use the design pattern."
                       "Limit to 1 sentence."),
            ("user", "Pattern: {pattern}\nSeed File: {seed_file}\nReasoning: {reasoning}")
        ])
        chain = prompt | self.llm
        res = chain.invoke({"pattern": pattern, "seed_file": seed_file, "reasoning": reasoning})
        return res.content

    def generate_tier_3(self, pattern: str, reasoning: str) -> str:
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a Product Owner writing a Jira ticket. "
                       "Describe a technical debt issue as a goal-oriented complaint. "
                       "Focus on pain points (extensibility, maintenance) of the old design. "
                       "Do not mention the pattern name explicitly. "
                       "Use a Title and Description format. Limit to 2 sentences."),
            ("user", "Pattern Goal: {pattern}\nRefactoring Reasoning: {reasoning}")
        ])
        chain = prompt | self.llm
        res = chain.invoke({"pattern": pattern, "reasoning": reasoning})
        return res.content

    def generate_tier_4_data(self, after_code: str, pattern: str) -> Dict[str, str]:
        """Generates both the instruction and the failing test code for Tier 4."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a senior Java engineer. Your task is to help create a Test-Driven Development (TDD) task for a refactoring agent. \n"
                       "1. Write a brief instruction telling the agent that a senior engineer wrote a test case representing the desired new architecture, and they must refactor the code to make it pass. (1 sentence max)\n"
                       "2. Synthesize a failing JUnit test case (as a single @Test method) that captures this new design using the provided 'after-state' code.\n"
                       "Provide the output in JSON format with keys 'instruction' and 'test_code'."),
            ("user", "Pattern: {pattern}\nAfter-state Code Snippet:\n{after_code}")
        ])
        # Force JSON response if possible, or just parse carefully
        # For simplicity in this script, we'll just use a structured request
        chain = prompt | self.llm
        res = chain.invoke({"pattern": pattern, "after_code": after_code[:5000]})
        
        # Simple extraction if not using JSON mode
        content = res.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        try:
            return json.loads(content)
        except:
            # Fallback if LLM fails to provide JSON
            return {"instruction": "Refactor the codebase so that the provided test case compiles and passes.", "test_code": content}

class PipelineRunner:
    """Orchestrates the task generation pipeline."""
    
    def __init__(self, input_path: str, output_path: str, candidate_id: Optional[str] = None):
        self.input_path = input_path
        self.output_path = output_path
        self.candidate_id = candidate_id
        self.generator = TaskGenerator()
        self.tasks: List[Dict[str, Any]] = []
        self.processed_ids: Set[str] = set()
        
    def load_state(self):
        """Loads already processed tasks to support incremental runs."""
        if os.path.exists(self.output_path):
            with open(self.output_path, 'r') as f:
                try:
                    self.tasks = json.load(f)
                    self.processed_ids = {t['task_id'] for t in self.tasks}
                except json.JSONDecodeError:
                    print(f"Warning: Could not decode {self.output_path}, starting fresh.")
                    self.tasks = []
                    self.processed_ids = set()

    def get_eval_project(self, repo_path: str) -> EvalProject:
        """Initializes an EvalProject for the given repository path."""
        project_name = os.path.basename(repo_path)
        try:
            return EvalProject(project_name)
        except Exception:
            import pathlib
            import git
            eval_project = EvalProject.__new__(EvalProject)
            eval_project.project_name = project_name
            eval_project.git_repo = git.Repo(repo_path)
            eval_project.get_project_path = lambda: pathlib.Path(repo_path)
            return eval_project

    def get_git_context(self, project: EvalProject, seed_file: str, baseline: str, target: str) -> Optional[Dict[str, str]]:
        """Extracts diff and after-state code for a candidate."""
        try:
            diff = project.get_commit_diff(file_path_2=seed_file, sha_1=baseline, sha_2=target)
            after_code = project.get_file_content_by_sha(target, seed_file)
            return {"diff": diff, "after_code": after_code}
        except Exception as e:
            print(f"Error extracting git data: {e}")
            return None

    def save_incremental(self):
        """Saves current tasks list to the output file."""
        with open(self.output_path, 'w') as f:
            json.dump(self.tasks, f, indent=2)

    def run(self):
        """Main execution loop."""
        if not os.path.exists(self.input_path):
            print(f"Input file not found: {self.input_path}")
            return

        with open(self.input_path, 'r') as f:
            candidates = json.load(f)

        self.load_state()

        for cand in candidates:
            cand_id = cand.get('id')
            if not cand_id:
                print("Warning: Candidate missing 'id', skipping.")
                continue

            # filter by candidate_id if provided
            if self.candidate_id and cand_id != self.candidate_id:
                continue

            if cand_id in self.processed_ids:
                print(f"Skipping already processed candidate: {cand_id}")
                continue

            repo_path = cand.get('repo_path')
            seed_file = cand.get('pattern_file')
            baseline_sha = cand.get('parent_sha')
            target_sha = cand.get('birth_commit_sha')

            if not all([repo_path, seed_file, baseline_sha, target_sha]):
                print(f"Warning: Candidate {cand_id} missing critical git info, skipping.")
                continue

            print(f"Processing candidate: {cand_id} ({cand.get('pattern', 'Unknown')})")
            
            project = self.get_eval_project(repo_path)
            context = self.get_git_context(
                project, 
                seed_file, 
                baseline_sha, 
                target_sha
            )
            
            if not context:
                continue

            reasoning = cand.get('detection_reasoning') or cand.get('greenfield', {}).get('llm_reasoning', "")
            
            # Generate prompts using LLM
            p1 = self.generator.generate_tier_1(context['diff'], cand['pattern_file'])
            p2 = self.generator.generate_tier_2(cand['pattern'], cand['pattern_file'], reasoning)
            p3 = self.generator.generate_tier_3(cand['pattern'], reasoning)
            p4_data = self.generator.generate_tier_4_data(context['after_code'], cand['pattern'])
            
            prompts = {
                TaskTier.MECHANIC: TaskPrompt(prompt=p1),
                TaskTier.ARCHITECT: TaskPrompt(prompt=p2),
                TaskTier.PRODUCT_OWNER: TaskPrompt(prompt=p3),
                TaskTier.TDD: TaskPrompt(prompt=p4_data.get('instruction', ""), failing_test=p4_data.get('test_code'))
            }
            
            try:
                # Optimized task object: only unique generated data
                task_obj = RefactoringTask(
                    task_id=cand_id,
                    prompts=prompts
                )
                self.tasks.append(task_obj.dict())
                self.save_incremental()
                print(f"Successfully saved task {cand_id}")
            except ValidationError as e:
                print(f"Validation error for {cand_id}: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate design pattern refactoring tasks.")
    parser.add_argument("--candidate_id", type=str, help="Specific candidate ID to process.")
    args = parser.parse_args()

    runner = PipelineRunner(INPUT_FILE, OUTPUT_FILE, candidate_id=args.candidate_id)
    runner.run()
