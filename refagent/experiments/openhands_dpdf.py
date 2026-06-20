import os
import refagent

from openhands.sdk import LLM, Agent, Conversation, Tool
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.task_tracker import TaskTrackerTool
from openhands.tools.terminal import TerminalTool
from openhands.tools.browser_use import BrowserToolSet


def run_openhands():

    llm = LLM(
        model=os.getenv("LLM_MODEL", "openai/gpt-5-mini"),
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("LLM_BASE_URL", None),
    )

    agent = Agent(
        llm=llm,
        tools=[
            Tool(name=TerminalTool.name),
            Tool(name=FileEditorTool.name),
            Tool(name=TaskTrackerTool.name),
            Tool(name=BrowserToolSet.name),
        ],
    )

    cwd = os.getcwd()
    conversation = Conversation(agent=agent, workspace=cwd)

    conversation.send_message("""Each file in /Users/abhiram/Documents/TBE/RefactoringAgentProject/Agent4Refactoring/data/design_patterns/split_files represents a github project. Find the url to the projects for me. Since there are so many, write a script to do so and get me the output of the script. 
                              """)
    conversation.run()
    print("All done!")

def processing():
    import pandas as pd
    import json

    # Load the CSV file
    csv_file_path = refagent.repo_root.joinpath('data/design_patterns/dpdf_dataset.csv')
    df = pd.read_csv(csv_file_path)

    # Drop the weight columns (assuming they start with 'w2v_')
    weight_columns = [col for col in df.columns if col.startswith('w2v_')]
    df = df.drop(columns=weight_columns)

    # Convert the DataFrame to a list of dictionaries
    data_json = df.to_dict(orient='records')

    # Write the JSON data to a file
    json_file_path = refagent.repo_root.joinpath('data/design_patterns/dpdf_dataset.json')
    with open(json_file_path, 'w') as json_file:
        json.dump(data_json, json_file, indent=4)

    print(f"Converted CSV to JSON and saved to {json_file_path}")

if __name__ == "__main__":
    run_openhands()
    # processing()


