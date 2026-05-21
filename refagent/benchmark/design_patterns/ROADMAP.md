# Design Pattern Refactoring Roadmap

This document outlines the strategic phases and detailed task lists for the Design Pattern Refactoring Benchmark project. The project is divided into several "Stories" that represent major architectural components.

## Story 1: Pattern Discovery Mining Pipeline
**Goal**: Automate the identification of design pattern refactorings in large-scale Java repositories.

- [x] **Phase 1: Pattern-First Mining**
  - [x] Implement NameHeuristicDetector for 23 GoF patterns
  - [x] Integrate LLM-based verification to reduce false positives
  - [x] Implement Birth Discovery logic using git blame/log
- [x] **Phase 2: Commit-First Mining**
  - [x] Integrate RefactoringMiner for structural signal detection
  - [x] Implement keyword-based commit message analysis
- [x] **Phase 3: Aggregation & Filtering**
  - [x] Build GreenfieldFilter to exclude initial code additions
  - [x] Create deterministic ID generation for candidates
  - [x] Aggregate diverse mining results into `aggregated_candidates.json`

## Story 2: Manual Validation & Dataset Curation
**Goal**: Establish a "gold standard" ground truth dataset through human-in-the-loop validation.

- [x] **Validation UI**
  - [x] Build React-based validation dashboard
  - [x] Display remote GitHub diffs and local AST context
  - [x] Implement "Refactoring" vs "Pattern" reasoning display
- [x] **Dataset Refinement**
  - [x] Validate 200+ candidates across 10 major Java projects
  - [x] Export validated high-confidence records to `dpdf_dataset_filtered.json`
  - [x] Inject human reasoning labels back into mining prompts

## Story 3: Verification & Scorecard Engine
**Goal**: Build a robust, automated system to evaluate the correctness of a refactoring attempt.

- [x] **AST-Based Verification**
  - [x] Implement `ExtendsSuperclassCheck`, `ImplementsInterfaceCheck`, and `MethodAddedCheck`
  - [x] Create LLM-based `ScoreCardCreator` to synthesize checks from diffs
- [x] **Scorecard Synthesis Adjustment**
  - [x] Build CLI to verify scorecards against "Gold" (ground truth) commits
  - [x] Implement logic to adjust `impacts_recall` and `expected` status based on parent state
- [ ] **Advanced Checks (Pending)**
  - [ ] Implement `CallSiteUpdateCheck` (verifying usage of the new pattern)
  - [ ] Implement `LogicMigrationCheck` (ensuring core logic moved to the new structure)

## Story 4: Evaluation Sandboxes (Dockerization)
**Goal**: Ensure safe, reproducible, and fast execution environments for refactoring agents.

- [x] **Project Standardization**
  - [x] Create Dockerfiles for Axon, Flink, HBase, Kafka, etc.
  - [x] Standardize `run_build.sh` and `run_test.sh` interfaces
  - [ ] Test the docker containers actually build and compile. 
  - [ ]
- [x] **Agent Injection Scripts**
  - [x] Implement `apply_patch.sh` for atomic change application
  - [x] Implement `verify_patch.sh` for build/test cycle within the container
- [x] **Optimization**
  - [x] Pre-warm dependency caches in Docker images to reduce build times

## Story 5: Undo Pattern Refactoring (The "Reverse" Benchmark)
**Goal**: Evaluate agents on their ability to simplify code by removing unnecessary design pattern complexity.

- [/] **Undo Logic Implementation**
  - [x] Define `UndoVariant` registry for various pattern removals (e.g., Factory -> Simple Constructor)
  - [x] Build `UndoPatternPipeline` for automated OpenHands dispatch
- [/] **Execution & Data Capture**
  - [/] Execute "Undo" runs across 10 projects
  - [x] Capture results as versioned `.patch` files
  - [ ] Generate comprehensive "Undo" scorecard metrics

## Story 6: Agent Benchmarking & Metrics
**Goal**: Run evaluation cycles and generate the final leaderboard for refactoring agents.

- [/] **Benchmark Execution**
  - [x] Implement 4-tier task generation (Mechanic, Architect, PO, TDD)
  - [x] Set up Headless OpenHands execution harness
- [ ] **Leaderboard & Analysis**
  - [ ] Calculate Precision/Recall/Blast-Radius for multiple LLMs (Gemini, GPT-4, Claude)
  - [ ] Generate comparative reports on "Architectural Reasoning" vs "Code Mechanics"
  - [ ] Finalize the "Design Pattern Benchmark" paper/report
