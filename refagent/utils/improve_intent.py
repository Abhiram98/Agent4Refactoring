import argparse
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
import re


def get_project_root():
    current_file = os.path.abspath(__file__)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
    return project_root


def get_chat_grazie_client():
    """Initialize ChatGrazie client"""
    return ChatGrazie(
        grazie_jwt_token=SecretStr(os.getenv("GRAZIE_JWT_TOKEN")),
        client_auth_type=AuthType.APPLICATION,
        client_url=GrazieApiGatewayUrls.PRODUCTION,
        profile="openai-gpt-4o-mini",
        client_agent_name="fix-agent",
        client_agent_version="0.1",
        temperature=1,
    )


def get_chat_openai_client():
    return ChatOpenAI(model="gpt-4o-mini", temperature=1)


def _get_git_diff(project_name, file_path_1, file_path_2, v1_hash, v2_hash):
    project = EvalProject(project_name)
    return project.get_commit_diff(
        file_path_1=file_path_1,
        file_path_2=file_path_2,
        sha_1=v1_hash,
        sha_2=v2_hash,
        unified_context=1000,
    )


def create_hint(refactoring_type, change_description):
    old_name = ""
    new_name = ""

    if refactoring_type == "Rename Class":
        match = re.search(
            r"Rename Class .*\.([A-Za-z0-9_]+) renamed to .*\.([A-Za-z0-9_]+)",
            change_description,
        )
        if match:
            old_name = match.group(1)
            new_name = match.group(2)

    elif refactoring_type == "Rename Method":
        match = re.search(
            r"Rename Method .*? ([A-Za-z0-9_]+)\(.*?\)\s*:\s*.*? renamed to .*? ([A-Za-z0-9_]+)\(",
            change_description,
        )
        if match:
            old_name = match.group(1)
            new_name = match.group(2)

    elif refactoring_type == "Rename Variable":
        match = re.search(
            r"Rename Variable ([A-Za-z0-9_]+) ?: .*? to ([A-Za-z0-9_]+) ?: .*?",
            change_description,
        )
        if match:
            old_name = match.group(1)
            new_name = match.group(2)
    elif refactoring_type == "Rename Attribute":
        match = re.search(
            r"Rename Attribute ([A-Za-z0-9_]+) ?: .*? to ([A-Za-z0-9_]+) ?: .*? in class",
            change_description,
        )
        if match:
            old_name = match.group(1)
            new_name = match.group(2)
    elif refactoring_type == "Rename Parameter":
        match = re.search(
            r"Rename Parameter ([A-Za-z0-9_]+) ?: .*? to ([A-Za-z0-9_]+) ?: .*? in method",
            change_description,
        )
        if match:
            old_name = match.group(1)
            new_name = match.group(2)

    return f"{old_name} -> {new_name}" if old_name and new_name else None


def process_json(json_file_path, project_name, selected_ids):
    project = EvalProject(project_name)
    chat_client = get_chat_grazie_client()
    # chat_client = get_chat_openai_client()

    with open(json_file_path, "r") as f:
        data = json.load(f)

    updated = False
    for i, entry in enumerate(data):
        if selected_ids is not None and entry["id"] not in selected_ids:
            continue

        if "v2_hash" in entry and "starting_file" in entry:
            file_1 = entry["starting_file"]
            file_2 = entry["starting_file"]
            v1_hash = entry["v1_hash"]
            v2_hash = entry["v2_hash"]

            hint = entry["hints"][0]
            print(f"\n{'=' * 80}")
            print(f"Processing Entry {i + 1}")
            print(f"{'=' * 80}")

            try:
                diff_output = _get_git_diff(
                    project_name, file_1, file_2, v1_hash, v2_hash
                )
                ex_left = hint.split(" -> ")[0]
                ex_right = hint.split(" -> ")[1]

                refactoring_type_in_start_file = None
                for refactoring_change in entry["refactoring_changes"]:
                    if refactoring_change["leftSideLocations"][0]["filePath"] == file_1:
                        refactoring_type_in_start_file = refactoring_change["type"]
                        break

                # print(f"type in start file: {refactoring_type_in_start_file}")
                # print(f"diff output: {diff_output}")

                # if "deleted file mode" in diff_output or refactoring_type_in_start_file == 'Rename Class':
                #     for refactoring_change in entry['refactoring_changes']:
                #         if refactoring_change['type'] != 'Rename Class':
                #             file_1 = refactoring_change['leftSideLocations'][0]['filePath']
                #             file_2 = refactoring_change['rightSideLocations'][0]['filePath']
                #             v1_hash = entry['v1_hash']
                #             v2_hash = entry['v2_hash']
                #             if create_hint(refactoring_change['type'], refactoring_change['description']) is not None:
                #                 hint = create_hint(refactoring_change['type'], refactoring_change['description'])
                #                 entry['hints'].append(hint)
                #                 entry['hints'] = list(reversed(entry['hints']))
                #                 print(f"Hint: {hint} changed for datapoint {entry['id']}")
                #             diff_output = _get_git_diff(project_name, file_1, file_2, v1_hash, v2_hash)
                #             if "deleted file mode" not in diff_output:
                #                 entry['starting_file'] = file_1
                #                 break

                if "deleted file mode" in diff_output:
                    for refactoring_change in entry["refactoring_changes"]:
                        file_1 = refactoring_change["leftSideLocations"][0]["filePath"]
                        file_2 = refactoring_change["rightSideLocations"][0]["filePath"]
                        v1_hash = entry["v1_hash"]
                        v2_hash = entry["v2_hash"]
                        if (
                            create_hint(
                                refactoring_change["type"],
                                refactoring_change["description"],
                            )
                            is not None
                        ):
                            hint = create_hint(
                                refactoring_change["type"],
                                refactoring_change["description"],
                            )
                            entry["hints"].append(hint)
                            entry["hints"] = list(reversed(entry["hints"]))
                            print(f"Hint: {hint} changed for datapoint {entry['id']}")
                        diff_output = _get_git_diff(
                            project_name, file_1, file_2, v1_hash, v2_hash
                        )
                        if "deleted file mode" not in diff_output:
                            entry["starting_file"] = file_1
                            break

                prompt = construct_prompt(hint, diff_output)

                print("\nSending prompt to LLM...")
                response = chat_client.invoke(prompt)
                llm_response = response.content

                print(f"LLM Response: {llm_response}")

                # first_sentence = llm_response.split('.')[0].strip() + '.'
                # entry['change_summary'] = first_sentence
                entry["change_summary"] = llm_response
                updated = True

                print(f"Updated change_summary for entry {i + 1}")

            except Exception as e:
                print(f"Error processing entry {i + 1}: {e}")
        else:
            missing_fields = []
            if "v2_hash" not in entry:
                missing_fields.append("v2_hash")
            if "starting_file" not in entry:
                missing_fields.append("starting_file")
            if "improved_commit_message" not in entry:
                missing_fields.append("improved_commit_message")
            print(f"Entry {i + 1} missing required fields: {', '.join(missing_fields)}")

    if updated:
        print(f"\n{'=' * 80}")
        print("Saving updated JSON...")
        with open(json_file_path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Updated JSON saved to {json_file_path}")
        print(f"{'=' * 80}")
    else:
        print("No updates made to JSON file.")


def construct_prompt(hint, git_diff):
    # prompt = f"""
    # A developer renamed the identifier {hint} in this commit. Another developer now needs to perform a similar rename elsewhere. Think carefully about what naming convention or reasoning may have motivated this change. Then, summarize the rationale behind the rename in two sentences.

    # Do not comment on type changes or type correctness. Focus only on the identifier rename, its meaning, and the role it plays in the code. Include surrounding code context and concrete examples if relevant.

    # Git Diff:
    # {git_diff}

    # Write a concise summary within 2 sentences of the reasoning behind this identifier rename. Focus only on the identifier change—not the type. Do not mention type names or type correctness. Preserve the exact letter casing of the identifiers as shown in the hint: {hint}. Avoid phrases like "In this commit" or "The developer should."
    # """

    #     prompt = f"""
    # A developer renamed {hint} in this commit. Then, imagine a second developer needs to apply the same change elsewhere. Now think what are the steps they should follow to perform the rename consistently. Finally, provide a concise summary of the reasoning behind this rename based on the provided diff.
    #
    # Git Diff:
    # {git_diff}
    #
    # Write the summary within 2 sentences. Include surrounding code context and concrete examples to illustrate the changes. Don't start with "The developer should" or "The developer should" or "In this commit" or "In this diff" etc. Just write the a concise summary of the reasoning behind this rename based on the provided diff.
    # """

    old_name, new_name = hint.split(" -> ")
    prompt = f"""
Analyze this identifier transformation: {old_name} → {new_name}

Git Diff:
{git_diff}

Create actionable transformation instructions by completing this template:

"Transform identifiers that [PATTERN TO MATCH] by [TRANSFORMATION RULE]. Apply this to [SCOPE/CONTEXT]."

Guidelines:
- [PATTERN TO MATCH]: Describe what identifiers to look for
- [TRANSFORMATION RULE]: Specify how to change them  
- [SCOPE/CONTEXT]: Define the type of code context where this applies using code element terms - avoid specific class or method names

Write exactly 1-2 sentences using this template structure. Focus on what to change, not why it was changed. Use action verbs and be specific about the pattern. Make the rule generalizable across similar code contexts.
"""

    return prompt


def main():
    parser = argparse.ArgumentParser(description="Improve intent")
    parser.add_argument("--project_name", type=str, required=True, help="Project name")
    parser.add_argument(
        "--json_file_path", type=str, required=True, help="Path to JSON file"
    )
    parser.add_argument(
        "-run_selected",
        type=str,
        help="IDs to run the agent on. "
        "To be called as a comma separated values."
        'e.g "1,2,3,4"',
    )
    args = parser.parse_args()

    selected_ref_ids = (
        [int(i) for i in args.run_selected.split(",")]
        if args.run_selected is not None
        else None
    )
    project_root = get_project_root()
    print(f"Project root directory: {project_root}")

    # json_file_path = os.path.join(project_root, "data", "renas", "ratpack-600-620.json")
    # json_file_path = args.json_file_path

    if not os.path.exists(args.json_file_path):
        print(f"Error: {args.json_file_path} not found")
        return

    print(f"Processing {args.json_file_path}...")
    process_json(
        args.json_file_path,
        project_name=args.project_name,
        selected_ids=selected_ref_ids,
    )


if __name__ == "__main__":
    main()
