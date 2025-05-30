# Agent4Refactoring

A refactoring agent + a benchmark to evaluate agents design for refactoring software codbases.

# Installation & Setup

### Install package

Tested python version: 3.12. (It will probably _not_ work with other versions?! :/)

```shell
pip install -e . # this install the repository in edit mode (good for development) 
```

### Install grazie-langchain-utils

1. cd `path/to/grazie-langchain-utils`
2. run `pip install .`

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
GH_TOKEN='<GITHUB_API_TOKEN>'
```


# Usage

## Running the agent

WIP. Will include documentation soon!



### Benchmarking the performance of Simple Agents

Simple agents: LLM + basic tools (read_file, write_file, LS)

```shell
python refagent/experiments/run_agent.py
```

#### Using different Language models.
Change the LLM profile in `refagent/agents/simple_agent.py:41` 
```python
    model = ChatGrazie(grazie_jwt_token=SecretStr(os.getenv("GRAZIE_JWT_TOKEN")),
                       client_auth_type=AuthType.APPLICATION,
                       client_url=GrazieApiGatewayUrls.STAGING,
                       profile="openai-gpt-4o-mini", # CHANGE THIS to try a different model
                       client_agent_name='vanilla-ref-agent',
                       client_agent_version='0.1'
                       )
```