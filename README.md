# Agent4Refactoring

A refactoring agent + a benchmark to evaluate agents design for refactoring software codbases.

# Installation & Setup

### Install package

Tested python version: 3.10. (It will probably work with other versions?!)

```shell
pip install -e . # this install the repository in edit mode (good for development) 
```

### Download evaluation projects
`git clone` these projects in a specific folder (`EVALUATION_PROJECTS_PATH`):

```
apache/flink
NationalSecurityAgency/ghidra
```

e.g: `git clone https://www.github.com/apache/flink`

### Download and install RefactoringMiner

Install refactoring miner by following the instructions [here](https://github.com/tsantalis/RefactoringMiner)

Follow the instructions to [How to run RefactoringMiner from the command line](https://github.com/tsantalis/RefactoringMiner?tab=readme-ov-file#how-to-run-refactoringminer-from-the-command-line). You will need to build the project. 

Finally, note the path to refactoring miner's executable binary. Usually, it is something like:

`REFMINER_PATH=RefactoringMiner/build/distributions/RefactoringMiner-<VERSION>`


### Setup Grazie, OpenAI key
Create a `.env` file at the root of the project, with the following contents:
```
OPENAI_API_KEY='<API_KEY_HERE>'
REFMINER_PATH='<REFMINER_PATH>'
PROJECTS_BASE_PATH='<EVALUATION_PROJECTS_PATH>'
GRAZIE_JWT_TOKEN='<GRAZIE_KEY_HERE>'
```

### Download other repositories.



# Usage

## Running the agent

WIP. Will include documentation soon!



### Benchmarking the performance of Simple Agents

Simple agents: LLM + basic tools (read_file, write_file, LS)

```shell
python refagent/experiments/run_agent.py
```

