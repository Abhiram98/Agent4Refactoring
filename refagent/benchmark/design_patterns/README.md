# Design Pattern Refactoring Benchmark

This module provides tools for detecting design pattern refactorings in Java repositories and evaluating them using a scorecard-based approach.

## Goals

1.  **Detection**: Automatically identify commits where code has been refactored to incorporate a design pattern.
2.  **Evaluation**: Build and execute a scorecard to verify if a refactoring commit correctly implements the intended pattern and addresses the relevant code smells.

---

## Data Storage

By default, all data related to the design pattern benchmark is stored in the `data/design_patterns/` directory.

- **Individual Project Results**: `data/design_patterns/miner/` (contains JSON files for each mined repository).
- **Aggregated Candidates**: `data/design_patterns/aggregated_candidates.json` (the unified dataset created by the aggregation script).
- **Scorecards**: `data/design_patterns/scorecard.jsonl` (generated evaluation scorecards).
- **Tasks**: `data/design_patterns/tasks.json` (generated benchmark tasks).

---

## 1. Mining and Detection Pipeline

There are two primary approaches to mining refactoring candidates: **Pattern-First** and **Commit-First**.

### A. Pattern-First Approach
This approach starts by detecting existing pattern instances in the *latest* version of the code and then traces them back to their "birth commit" to see if they were introduced via refactoring.

*   **Full Pipeline (Phases 1 → 3)**
    ```bash
    python -m refagent.benchmark.design_patterns.pattern_first.mine_from_pattern \
        --repos /path/to/repo \
        --filter-greenfield \
        --output data/design_patterns/pf_candidates.json
    ```
    Executes detection, birth discovery, and greenfield filtering.
    - **Phase 1**: Detects patterns (via heuristics and **LLM by default**; use `--disable-llm-detector` to skip LLM).
    - **Phase 2**: Finds the birth commit of each pattern instance.
    - **Phase 3**: Filters out "greenfield" additions (**using LLM by default**; use `--disable-llm-filter` to skip LLM) to keep only genuine refactorings.

*   **Seeding from Dataset**
    You can skip Phase 1 and use known instances from the `dpdf` dataset:
    ```bash
    python -m refagent.benchmark.design_patterns.pattern_first.mine_from_pattern \
        --repos /path/to/repo \
        --dpdf-dataset data/design_patterns/dpdf_dataset_filtered.json \
        --dpdf-project <project-name> \
        --output data/design_patterns/pf_candidates.json
    ```

*   **Aggregation**
    ```bash
    python -m refagent.benchmark.design_patterns.pattern_first.aggregate_miner_data
    ```
    Combines multiple mining outputs into a single `aggregated_candidates.json` file with unique, deterministic IDs.

### B. Commit-First Approach
This approach starts by scanning all commits in a repository and looks for signals (keywords in messages or RefactoringMiner output) indicating a design pattern might have been introduced.

*   **Full Pipeline (Stages 1 → 3)**
    ```bash
    python -m refagent.benchmark.design_patterns.commit_first.pipeline \
        --since 2024-01-01 \
        --max-repos 10 \
        --output data/design_patterns/dp_introductions.json
    ```
    Orchestrates repo discovery (Stage 1), commit mining (Stage 2), and validation (Stage 3).

*   **Stage 2: Mining Only**
    ```bash
    python -m refagent.benchmark.design_patterns.commit_first.mine \
        --repos /path/to/repo \
        --output data/design_patterns/candidates.json
    ```
    Mines local repositories for commits suspected of introducing GoF design patterns.

*   **Stage 3: Validation Only**
    ```bash
    python -m refagent.benchmark.design_patterns.commit_first.validate \
        --candidates data/design_patterns/candidates.json \
        --output data/design_patterns/dp_introductions.json
    ```
    Scores and filters candidates based on heuristic evidence. High-confidence records are separated from those needing manual review.

---

## 2. Scorecard Generation and Evaluation

Once candidates are identified, you can generate scorecards to evaluate how well an agent (or a human) performs the same refactoring.

*   **Generate Scorecard**
    ```bash
    python -m refagent.benchmark.design_patterns.scorecard.synthesis.cli \
        --candidate-id <ID> \
        --aggregated-json data/design_patterns/aggregated_candidates.json \
        --output data/design_patterns/scorecard.jsonl
    ```
    Uses an LLM to synthesize AST-based checks and file-presence constraints for a specific refactoring instance.

*   **Adjust Scorecards**
    ```bash
    python -m refagent.benchmark.design_patterns.scorecard.synthesis.adjust_scorecard_cli \
        --input data/design_patterns/scorecard.jsonl
    ```
    Refines existing scorecards by checking them against the "gold" (ground truth) commit and its parent to ensure they are reasonably achievable.

*   **Run Evaluation**
    ```bash
    python -m refagent.benchmark.design_patterns.scorecard.evaluator_cli \
        --candidate-id <ID> \
        --commit-hash <SHA>
    ```
    Evaluates a specific commit against the generated scorecard. It calculates precision and recall based on structural AST checks.

---

## 3. Task Generation

For benchmarking agents, you can convert candidates into structured tasks with different levels of guidance.

*   **Generate Tasks**
    ```bash
    python -m refagent.benchmark.design_patterns.task.generate_tasks \
        --candidate_id <ID>
    ```
    Generates four tiers of tasks for a candidate:
    1.  **Mechanic**: Detailed step-by-step instructions.
    2.  **Architect**: High-level architectural directive.
    3.  **Product Owner**: Goal-oriented "Jira ticket" (pattern name hidden).
    4.  **TDD**: A failing JUnit test case that the agent must make pass.

---

## Directory Structure
- `pattern_first/`: Logic for pattern-based mining and greenfield filtering.
- `commit_first/`: Logic for commit-based mining.
- `scorecard/`: Schema and logic for synthesizing and evaluating refactoring scorecards.
- `task/`: Tools for generating benchmark tasks from candidates.
- `models.py`: Shared Pydantic models for patterns, repos, and candidates.
