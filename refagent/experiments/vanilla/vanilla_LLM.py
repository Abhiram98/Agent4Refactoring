import json
import os
import re
import argparse
from pathlib import Path
from pydantic.v1 import SecretStr
from grazie.api.client.endpoints import GrazieApiGatewayUrls
from grazie.api.client.gateway import AuthType
from grazie_langchain_utils.language_models.grazie import ChatGrazie
from langchain_core.messages import HumanMessage, SystemMessage


import refagent
import refagent.utils.intellij_server as ij
import refagent.utils.project_manager as pm
import refagent.utils.refminer_utils as rminer
import refagent.refactoring_types.refactorings as refactoring_types

# Define rename types for filtering RefactoringMiner output
RENAME_TYPES = {
    "Rename Class",
    "Rename Method",
    "Rename Variable",
    "Rename Parameter",
    "Rename Attribute",
    "Rename Package",
}


def parse_name(refactoring_change):
    old_name = ""
    new_name = ""

    if refactoring_change["type"] == "Rename Class":
        match = re.search(
            r"Rename Class .*\.([A-Za-z0-9_]+) renamed to .*\.([A-Za-z0-9_]+)",
            refactoring_change["description"],
        )
        if match:
            old_name = match.group(1)
            new_name = match.group(2)

    elif refactoring_change["type"] == "Rename Method":
        match = re.search(
            r"Rename Method .*? ([A-Za-z0-9_]+)\(.*?\)\s*:\s*.*? renamed to .*? ([A-Za-z0-9_]+)\(",
            refactoring_change["description"],
        )
        if match:
            old_name = match.group(1)
            new_name = match.group(2)

    elif refactoring_change["type"] == "Rename Variable":
        match = re.search(
            r"Rename Variable ([A-Za-z0-9_]+) ?: .*? to ([A-Za-z0-9_]+) ?: .*?",
            refactoring_change["description"],
        )
        if match:
            old_name = match.group(1)
            new_name = match.group(2)
    elif refactoring_change["type"] == "Rename Attribute":
        match = re.search(
            r"Rename Attribute ([A-Za-z0-9_]+) ?: .*? to ([A-Za-z0-9_]+) ?: .*? in class",
            refactoring_change["description"],
        )
        if match:
            old_name = match.group(1)
            new_name = match.group(2)
    elif refactoring_change["type"] == "Rename Parameter":
        match = re.search(
            r"Rename Parameter ([A-Za-z0-9_]+) ?: .*? to ([A-Za-z0-9_]+) ?: .*? in method",
            refactoring_change["description"],
        )
        if match:
            old_name = match.group(1)
            new_name = match.group(2)

    return old_name, new_name


def create_grazie_model():
    """Create a Grazie LLM model."""
    return ChatGrazie(
        grazie_jwt_token=SecretStr(os.getenv("GRAZIE_JWT_TOKEN")),
        client_auth_type=AuthType.APPLICATION,
        client_url=GrazieApiGatewayUrls.PRODUCTION,
        profile="openai-gpt-5",
        client_agent_name="simple-rename-script",
        client_agent_version="0.1",
    )


def load_json_data(json_file_path):
    """Load JSON data from file."""
    with open(json_file_path, "r") as f:
        data = json.load(f)
    return data


def process_single_item(item_data, model):
    """Process a single item from the JSON data."""

    # Step 1: Extract required fields
    item_id = item_data.get("id", "unknown")
    project_name = item_data.get("project")
    v1_hash = item_data.get("v1_hash")
    starting_file = item_data.get("starting_file")
    hints = item_data.get("hints", [])
    seed_example = item_data.get("seed_example")

    if seed_example["type"] == "Rename Class":
        starting_file = seed_example["leftSideLocations"][0]["filePath"]
        print(
            f"[Setup] ✅ : Rename class is seed -> changed starting_file -> {starting_file}"
        )

    if not project_name:
        print(f"[Setup] ❌ : No project name found in item {item_id}")
        return False

    if not v1_hash:
        print(f"[Setup] ❌ : No v1_hash found in item {item_id}")
        return False

    if not starting_file:
        print(f"[Setup] ❌ : No starting_file found in item {item_id}")
        return False

    # if not hints:
    #     print(f"[Setup] ❌ : No hints found in item {item_id}")
    #     return False

    # first_hint = hints[0]
    print(f"Processing item {item_id}")
    print(f"Project: {project_name}")
    print(f"V1 Hash: {v1_hash}")
    print(f"Starting file: {starting_file}")
    # print(f"First hint: {first_hint}")

    # Step 2: Setup project and checkout to v1_hash
    try:
        project = pm.EvalProject(project_name)
        project.checkout(v1_hash, force=True)
        print(f"[Git] ✅ : Successfully checked out to {v1_hash}")

        # Open project in IntelliJ
        print("[Intellij] ✅ : Project opened and reloaded in IntelliJ")

    except Exception as e:
        print(f"[Intellij] ❌ : Error setting up project {project_name}: {e}")
        return False

    # Step 3: Open the file in IntelliJ and get its content
    try:
        with open(project.get_project_path().joinpath(starting_file), "r") as f:
            file_content = f.read()

        if not file_content or file_content.startswith("tool call failed"):
            print(f"[Intellij] ❌ : Failed to get file content: {file_content}")
            return False

        print(
            f"[Intellij] ✅ : Successfully retrieved file content ({len(file_content)} characters)"
        )

    except Exception as e:
        print(f"[Intellij] ❌ : Error opening file {starting_file}: {e}")
        return False

    # Step 4: Invoke LLM to rename variables based on the hint
    try:
        # Parse the hint to extract old and new variable names
        # if " -> " in first_hint:
        #     old_name, new_name = first_hint.split(" -> ", 1)
        #     old_name = old_name.strip()
        #     new_name = new_name.strip()
        # else:
        #     print(f"Invalid hint format: {first_hint}")
        #     return False

        old_name, new_name = parse_name(seed_example)
        print(f"[Seed Example] ⌛️ : Running on {old_name} -> {new_name}")

        # Create prompt for LLM
        system_message = SystemMessage(
            content="""
            You are a code refactoring assistant. Your task is to rename variables in the given code.
            You will be given the path to the current code and instructions to rename a specific variable.
            Apply the changes directly to the files.

            Use the provided rename as a seed to infer the broader naming concept being changed.
            Rename ALL occurrences that share the same concept consistently.
            Finally, output the entire code.
            """
        )

        user_message = HumanMessage(
            content=f"""
Please rename the variable '{old_name}' to '{new_name}' in the following code. Rename all conceptually related identifiers:

{file_content} 

Finally, output the entire code with renames applied.
"""
        )

        # Get LLM response
        response = model.invoke([system_message, user_message])
        modified_code = response.content.strip()

        print(f"[LLM] ✅ LLM successfully renamed '{old_name}' to '{new_name}'")

    except Exception as e:
        print(f" [LLM] ❌ : Error invoking LLM: {e}")
        return False

    # Step 5: Replace file contents using IntelliJ API
    try:

        with open(project.get_project_path().joinpath(starting_file), "w") as f:
            f.write(modified_code)

    except Exception as e:
        print(f"[Intellij] ❌ : Error replacing file contents: {e}")
        return False

    # Step 6: Commit the changes
    try:
        commit_message = f"Rename {old_name} to {new_name} in {starting_file}"
        project.safe_add([starting_file])
        commit_hash = project.git_repo.index.commit(commit_message)

        print(f"[Git] ✅ : Successfully committed changes: {commit_hash}")


        # Return the result data with RefactoringMiner analysis
        result_data = {
            "id": item_id,
            "response": {"commit_hash": str(commit_hash)},
        }
        return result_data

    except Exception as e:
        print(f"[Git] ❌ : Error committing changes: {e}")
        return False


def main():

    parser = argparse.ArgumentParser(
        description="Process JSON data to rename variables using LLM and analyze with RefactoringMiner",
        add_help=True,
    )
    parser.add_argument(
        "--json-file",
        type=str,
        default=str(refagent.benchmark_lite_file),
        help="Path to the JSON file to process (default: benchmark_lite_file)",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=5,
        help="Maximum number of items to process (default: 5)",
    )
    parser.add_argument(
        "--output-file",
        type=str,
        default="refactoring_results.json",
        help="Output JSON file to save results with RefactoringMiner analysis (default: refactoring_results.json)",
    )

    args = parser.parse_args()

    # Configuration
    json_file_path = args.json_file
    max_items = args.max_items
    output_file = args.output_file

    # Initialize components
    print("Initializing components...")
    print(f"Reading JSON data from: {json_file_path}")
    print(f"Max items to process: {max_items}")
    print(f"Output file: {output_file}")

    # Load JSON data directly (not using benchmark loader)
    json_data = load_json_data(json_file_path)
    try:
        cached_ids = [i['id'] for i in load_json_data(output_file)]
    except FileNotFoundError:
        cached_ids = []

    # Create Grazie model
    model = create_grazie_model()

    # Initialize IntelliJ server

    # Process items (limit to specified max_items for testing)
    success_count = 0
    total_count = min(max_items, len(json_data))
    results = [] if len(cached_ids) == 0  else load_json_data(output_file) # Store successful results

    for i, item in enumerate(json_data[:total_count]):
        print(f"\n--- Processing item {i + 1}/{total_count} ---")

        # Process the item
        ref_id = item.get('id', 'unknown')
        if ref_id in cached_ids:
            print(f"Skipping {ref_id} because it is already processed.")
            continue
        result = process_single_item(item, model)
        if result:  # result is now a dict with commit data or False on failure
            success_count += 1
            results.append(result)
            print(f" ✅ Successfully processed item {ref_id}")
        else:
            print(f" ❌ Failed to process item {ref_id}")

    print("\n=== Summary ===")
    print(f"Successfully processed: {success_count}/{total_count} items")

    if results:
        with open(output_file, "w") as f:
            json.dump(results, f, indent=4)
        print(f"Results saved to: {output_file}")
        print(f"Total results: {len(results)} items")
    else:
        print("No successful results to save.")


if __name__ == "__main__":
    main()
