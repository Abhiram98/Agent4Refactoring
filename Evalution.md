# Evaluation Setup

This document describes the evalution setup for our agent in various settings: offline (datasets) 
and online (patch creation)


## Offline evaluation

### With seed example

### With Intent

### With both Seed example and intent


## Online evaluation

Here we describe the process we used to submit patches. We have a monitoring script 
[monitor_projects.py](refagent/benchmark/creation/monitor_projects.py), which pulls a given projects contents (performs git pull), 
and looks for newly performed renames in commits. 
Everytime a rename is triggered, an entry is made into the following jsonl file - [monitor_results.jsonl](data/monitoring/monitor_results.jsonl).

Then, there is a script to locate fresh commits `suitable` to our agent on. 
See [curate_possible_patches.py](refagent/benchmark/creation/curate_possible_patches.py). It saves output to [for_patches.json](data/monitoring/for_patches.json). 
These are cases where we could run our agent.
We define commits suitable for patches in the following way:
1. There are between 1-2 renames performed in the commit. Reasoning: It is more likely that the developer missed something when they did only 1-2 renames, rather than 10 renames.
2. There are no type changes in the rename. Reason: These point to some semantic changes in the code. Submitting a patch in this case would not be appropriate

The [curate_possible_patches.py](refagent/benchmark/creation/curate_possible_patches.py) also saves some intermediate files to the following path: [patches-june-9](data/results/patches-june-9)
This is so that the agent doesn't have to start from scratch, but can pick up from where the developer left off.

### Running the agent

1. Run the planning phase. This will generate an `intent` based on the seed example. [run_planning.py](refagent/experiments/run_planning.py)
    ```python run_planning.py --benchmark_file="data/monitoring/for_patches.json" -run_identifier="patches-june-9"```
2. RUn the agent . Use [run_agent.py](refagent/experiments/run_agent.py), to trigger the agent on the necessary commit.
    ```-ref_ids="11198" --replication="True" --benchmark_file="data/monitoring/for_patches.json" -run_identifier="patches-june-9" -planning_results_file="results/patches-june-9/planning.json"```

This only runs the replication (post the developers changes.)


### Submitting a patch
1. Take a look at the agent's output. ex: [post-replication.json](data/results/patches-june-9/post-replication.json)
    Under "results.internal_commits", checkout the last commit.
2. Create a new branch from this commit. Merge the master branch into the new branch. resolve conflicts.
3. Submit a PR. As a reference checkout this PR: https://github.com/liferay/liferay-portal/pull/6296