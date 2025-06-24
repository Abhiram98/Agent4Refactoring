import json
import sys
import os

from dotenv import load_dotenv
load_dotenv()

from project_manager import EvalProject
from grazie_langchain_utils.language_models.grazie import ChatGrazie
from grazie.api.client.endpoints import GrazieApiGatewayUrls
from grazie.api.client.gateway import AuthType
from pydantic.v1 import SecretStr
from langchain_openai import ChatOpenAI

def get_project_root():
    current_file = os.path.abspath(__file__)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
    return project_root

def get_chat_grazie_client():
    """Initialize ChatGrazie client"""
    return ChatGrazie(grazie_jwt_token=SecretStr(os.getenv("GRAZIE_JWT_TOKEN")),
                      client_auth_type=AuthType.APPLICATION,
                      client_url=GrazieApiGatewayUrls.STAGING,
                      profile="openai-gpt-4o-mini",
                      client_agent_name='fix-agent',
                      client_agent_version='0.1',
                      temperature=1)
def get_chat_openai_client():
    return ChatOpenAI(model="gpt-4o-mini", temperature=1)


def process_flink_json(json_file_path, save_file_path):
    
    with open(json_file_path, 'r') as f:
        data = json.load(f)

    unique_sha = set()
    clean_data = []
    index = 200

    for i, entry in enumerate(data):
        updated_refactoring_changes = []

        if entry['v1_hash'] not in unique_sha:
            unique_sha.add(entry['v1_hash'])
        else:
            continue

        for refactoring_change in entry['refactoring_changes']:
            first_half =  refactoring_change['type'].split(' ')[0]
            if first_half == 'Rename':
                updated_refactoring_changes.append(refactoring_change)
            
        if len(updated_refactoring_changes) > 0:
            entry["id"] = index
            index += 1
            entry['refactoring_changes'] = updated_refactoring_changes
            entry['starting_file'] = updated_refactoring_changes[0]['leftSideLocations'][0]['filePath']
            clean_data.append(entry)

    print(f'{len(clean_data)} entries cleaned')
    
    with open(save_file_path, 'w') as f:
        json.dump(clean_data, f, indent=2)


def construct_prompt(hint, git_diff):
    
    prompt = f"""
A developer renamed {hint} in this commit. Then, imagine a second developer needs to apply the same change elsewhere. Now think what are the steps they should follow to perform the rename consistently. Finally, provide a concise summary of the reasoning behind this rename based on the provided diff.

Git Diff:
{git_diff}

Write the summary within 2 sentences. Include surrounding code context and concrete examples to illustrate the changes. Don't start with "The developer should" or "The developer should" or "In this commit" or "In this diff" etc. Just write the a concise summary of the reasoning behind this rename based on the provided diff.
"""
    
    return prompt

def main():
    
    project_root = get_project_root()
    print(f"Project root directory: {project_root}")
    
    json_file_path = os.path.join(project_root, "data", "ref_miner", "rename", "flink.json")
    save_file_path = os.path.join(project_root, "data", "ref_miner", "rename", "flink-clean.json")
    
    if not os.path.exists(json_file_path):
        print(f"Error: {json_file_path} not found")
        return
    
    print(f"Processing {json_file_path}...")
    process_flink_json(json_file_path, save_file_path)

if __name__ == "__main__":
    main() 