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

def get_project_root():
    current_file = os.path.abspath(__file__)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
    return project_root

def get_chat_grazie_client():
    """Initialize ChatGrazie client"""
    return ChatGrazie(grazie_jwt_token=SecretStr(os.getenv("GRAZIE_JWT_TOKEN")),
                      client_auth_type=AuthType.APPLICATION,
                      client_url=GrazieApiGatewayUrls.STAGING,
                      profile="gpt-4o",
                      client_agent_name='fix-agent',
                      client_agent_version='0.1',
                      temperature=0.3)

def process_ratpack_json(json_file_path, project_name='ratpack'):
    
    project = EvalProject(project_name)
    chat_client = get_chat_grazie_client()
    
    with open(json_file_path, 'r') as f:
        data = json.load(f)
    
    updated = False
    for i, entry in enumerate(data):
        if 'v2_hash' in entry and 'starting_file' in entry:
            file_1 = None
            file_2 = None
            v1_hash = None
            v2_hash = None
            starting_file = entry['starting_file']

            rename_class_datapoint = None

            for refactoring_change in entry['refactoring_changes']:
                if refactoring_change['type'] == 'Rename Class' and refactoring_change['leftSideLocations'][0]['filePath'] == starting_file:
                    rename_class_datapoint = refactoring_change
                    break

            if rename_class_datapoint is not None:
                file_1 = rename_class_datapoint['leftSideLocations'][0]['filePath']
                file_2 = rename_class_datapoint['rightSideLocations'][0]['filePath']
                v1_hash = entry['v1_hash']
                v2_hash = entry['v2_hash']
            else:
                file_2 = starting_file
                v2_hash = entry['v2_hash']

            hint = entry['hints'][0]
            
            
            print(f"\n{'='*80}")
            print(f"Processing Entry {i+1}")
            print(f"{'='*80}")
            print(f"File 1: {file_1}")
            print(f"File 2: {file_2}")
            print(f"Hash 1: {v1_hash}")
            print(f"Hash 2: {v2_hash}")
            print(f"Hint: {hint}")
            
            try:
                diff_output = project.get_commit_diff(
                    file_path_1=file_1,
                    file_path_2=file_2,
                    sha_1=v1_hash,
                    sha_2=v2_hash,
                    unified_context=1000
                )

                if(diff_output == ""):
                    print(f"Diff Output is empty for entry {i+1}")
                    continue
                
                # prompt = construct_prompt(hint, diff_output)
                
                # print("\nSending prompt to LLM...")
                
                # response = chat_client.invoke(prompt)
                # llm_response = response.content

                # print(f"LLM Response: {llm_response}")

                
                # entry['change_summary'] = llm_response
                # updated = True
                
                # print(f"Updated change_summary for entry {i+1}")
                    
            except Exception as e:
                print(f"Error processing entry {i+1}: {e}")
        else:
            missing_fields = []
            if 'v2_hash' not in entry:
                missing_fields.append('v2_hash')
            if 'starting_file' not in entry:
                missing_fields.append('starting_file')
            if 'improved_commit_message' not in entry:
                missing_fields.append('improved_commit_message')
            print(f"Entry {i+1} missing required fields: {', '.join(missing_fields)}")
    
    # if updated:
    #     print(f"\n{'='*80}")
    #     print("Saving updated JSON...")
    #     with open(json_file_path, 'w') as f:
    #         json.dump(data, f, indent=2)
    #     print(f"Updated JSON saved to {json_file_path}")
    #     print(f"{'='*80}")
    # else:
    #     print("No updates made to JSON file.")

def construct_prompt(hint, git_diff):
    
    prompt = f"""
A developer renamed {hint} in this commit. Then, imagine a second developer needs to apply the same change elsewhere. Now think what are the steps they should follow to perform the rename consistently. Finally, provide a concise summary of the reasoning behind this rename based on the provided diff.

Git Diff:
{git_diff}

Write the summary in a couple of sentences, not more than 6 sentences. Include surrounding code context and concrete examples to illustrate the changes.
"""
    
    return prompt

def main():
    
    project_root = get_project_root()
    print(f"Project root directory: {project_root}")
    
    json_file_path = os.path.join(project_root, "data", "renas", "ratpack-600-650.json")
    
    if not os.path.exists(json_file_path):
        print(f"Error: {json_file_path} not found")
        return
    
    print(f"Processing {json_file_path}...")
    process_ratpack_json(json_file_path)

if __name__ == "__main__":
    main() 