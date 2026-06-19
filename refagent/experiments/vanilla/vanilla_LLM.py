import json
import os
import re
import argparse
from pathlib import Path
from pydantic.v1 import SecretStr
from grazie.api.client.endpoints import GrazieApiGatewayUrls
from grazie.api.client.gateway import AuthType
from grazie_langchain_utils.language_models.grazie import ChatGrazie
from langchain_openai import ChatOpenAI
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


def extract_token_usage(response):
    """Extract normalized token usage from a LangChain AIMessage."""
    usage = {
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
        "model_name": None,
    }

    usage_metadata = getattr(response, "usage_metadata", None)
    if usage_metadata:
        usage["prompt_tokens"] = usage_metadata.get("input_tokens")
        usage["completion_tokens"] = usage_metadata.get("output_tokens")
        usage["total_tokens"] = usage_metadata.get("total_tokens")

    response_metadata = getattr(response, "response_metadata", None) or {}
    token_usage = response_metadata.get("token_usage") or {}
    if usage["prompt_tokens"] is None:
        usage["prompt_tokens"] = token_usage.get("prompt_tokens")
    if usage["completion_tokens"] is None:
        usage["completion_tokens"] = token_usage.get("completion_tokens")
    if usage["total_tokens"] is None:
        usage["total_tokens"] = token_usage.get("total_tokens")
    usage["model_name"] = response_metadata.get("model_name")

    return usage


def create_llm_model(provider: str, model: str):
    """Create an LLM model for the given provider."""
    if provider == "grazie":
        grazie_token = os.getenv("GRAZIE_JWT_TOKEN")
        if not grazie_token:
            raise ValueError(
                "GRAZIE_JWT_TOKEN environment variable is required when using Grazie"
            )
        return ChatGrazie(
            grazie_jwt_token=SecretStr(grazie_token),
            client_auth_type=AuthType.APPLICATION,
            client_url=GrazieApiGatewayUrls.PRODUCTION,
            profile=model,
            client_agent_name="simple-rename-script",
            client_agent_version="0.1",
        )
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY") or refagent.OPENAI_KEY
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable is required when using OpenAI"
            )
        os.environ["OPENAI_API_KEY"] = api_key
        # LangChain defaults to 0.7, but o-series and many newer models only allow 1.
        return ChatOpenAI(model=model, temperature=1)
    raise ValueError(f"Unknown LLM provider: {provider}. Choose 'grazie' or 'openai'.")


def load_json_data(json_file_path):
    """Load JSON data from file."""
    with open(json_file_path, "r") as f:
        data = json.load(f)
    return data


def process_single_item(
    item_data, intellij_server, model, llm_provider: str, model_name: str
):
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
        intellij_server.open_project(project_path=project.get_project_path())
        intellij_server.reload_project()
        print("[Intellij] ✅ : Project opened and reloaded in IntelliJ")

    except Exception as e:
        print(f"[Intellij] ❌ : Error setting up project {project_name}: {e}")
        return False

    # Step 3: Open the file in IntelliJ and get its content
    try:
        intellij_server.open_file(rel_file_path=Path(starting_file))
        file_content = intellij_server.call_tool_get("get_source_code")

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
Please rename the variable '{old_name}' to '{new_name}' in the following code:

{file_content}

Return only the modified code with the variable renamed.
"""
        )

        # Get LLM response
        response = model.invoke([system_message, user_message])
        modified_code = response.content.strip()
        token_usage = extract_token_usage(response)

        print(f"[LLM] ✅ LLM successfully renamed '{old_name}' to '{new_name}'")
        print(
            f"[LLM] Token usage: prompt={token_usage['prompt_tokens']}, "
            f"completion={token_usage['completion_tokens']}, "
            f"total={token_usage['total_tokens']}"
        )

    except Exception as e:
        print(f" [LLM] ❌ : Error invoking LLM: {e}")
        return False

    # Step 5: Replace file contents using IntelliJ API
    try:
        replace_response = intellij_server.call_tool(
            "replace_file_contents", file_path=starting_file, new_content=modified_code
        )

        if replace_response and not replace_response.startswith("tool call failed"):
            print("[Intellij] ✅ : Successfully replaced file contents")
        else:
            print(
                f"[Intellij] ❌ : Failed to replace file contents: {replace_response}"
            )
            return False

    except Exception as e:
        print(f"[Intellij] ❌ : Error replacing file contents: {e}")
        return False

    # Step 6: Commit the changes
    try:
        commit_message = f"Rename {old_name} to {new_name} in {starting_file}"
        project.safe_add([starting_file])
        commit_hash = project.git_repo.index.commit(commit_message)

        print(f"[Git] ✅ : Successfully committed changes: {commit_hash}")

        # Step 7: Run RefactoringMiner on the new commit to analyze what was actually changed
        detected_refactorings = []
        recall = 0.0
        precision = 0.0
        true_positive_count = 0
        false_positive_count = 0

        try:
            print("[RefMiner] ⌛️ : Running RefactoringMiner on new commit...")
            all_refactorings = rminer.default_runner.run(
                project.get_project_path(), str(commit_hash)
            )

            # Filter for rename refactorings only
            detected_refactorings = [
                r for r in all_refactorings if r.type in RENAME_TYPES
            ]
            print(f"[RefMiner] 🔎️ : {len(detected_refactorings)} rename refactorings")

            # Get original refactoring changes (oracle)
            oracle_refactorings = item_data.get("refactoring_changes", [])
            oracle_renames = [
                r for r in oracle_refactorings if r.get("type") in RENAME_TYPES
            ]

            # Calculate recall and precision
            if oracle_renames or detected_refactorings:
                # Convert oracle refactorings to RefMiner objects for comparison
                oracle_objects = []
                for oracle_dict in oracle_renames:
                    try:
                        oracle_obj = refactoring_types.RefminerOut.load_from_dictionary(
                            oracle_dict
                        )
                        oracle_objects.append(oracle_obj)
                    except Exception as e:
                        print(
                            f"[RefMiner] ❌ : Error converting oracle refactoring: {e}"
                        )
                        continue

                # Find matches between oracle and detected refactorings
                true_positives = []
                for oracle in oracle_objects:
                    for detected in detected_refactorings:
                        if oracle == detected:  # Compare using the __eq__ method
                            if detected not in true_positives:
                                true_positives.append(detected)
                                break  # Found a match, move to next oracle

                false_positives = [
                    d for d in detected_refactorings if d not in true_positives
                ]
                true_positive_count = len(true_positives)
                false_positive_count = len(false_positives)

                recall = (
                    (true_positive_count - 1) / (len(oracle_objects) - 1)
                    if (len(oracle_objects) > 1 and true_positive_count > 1)
                    else 0.0
                )
                precision = (
                    (true_positive_count - 1) / (len(detected_refactorings) - 1)
                    if (len(detected_refactorings) > 1 and true_positive_count > 1)
                    else 0.0
                )

                print(
                    f"[Eval] ⌛️ : True positives: {true_positive_count}, "
                    f"False positives: {false_positive_count}"
                )
                print(
                    f"[Eval] ⌛️ : Oracle renames: {len(oracle_objects)}, Detected renames: {len(detected_refactorings)}"
                )
                print(f"[Eval] ⌛️ : Recall: {recall:.2f}, Precision: {precision:.2f}")
            else:
                print("[Data] ❌ : No oracle or detected refactorings to compare")

        except Exception as e:
            print(f"[RefMiner] ❌ : Error running RefactoringMiner: {e}")

        # Return the result data with RefactoringMiner analysis
        result_data = {
            "id": item_id,
            "v1_hash": v1_hash,
            "starting_file": starting_file,
            "refactoring_changes": item_data.get("refactoring_changes", []),
            "new_commit_hash": str(commit_hash),
            "detected_refactorings": [r.model_dump() for r in detected_refactorings],
            "recall": recall,
            "precision": precision,
            "true_positive_count": true_positive_count,
            "false_positive_count": false_positive_count,
            "token_usage": token_usage,
            "llm_provider": llm_provider,
            "model": model_name,
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
        "--ij-server-url",
        type=str,
        default=refagent.IJ_SERVER_URL or "http://localhost:8082",
        help="IntelliJ server URL (default: http://localhost:8082)",
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
    parser.add_argument(
        "--llm-provider",
        type=str,
        choices=["grazie", "openai"],
        default="grazie",
        help="LLM backend: grazie (default) or openai",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model name: Grazie profile (default: openai-gpt-5o) or OpenAI model (default: gpt-4o)",
    )

    args = parser.parse_args()

    # Configuration
    json_file_path = args.json_file
    ij_server_url = args.ij_server_url
    max_items = args.max_items
    output_file = args.output_file
    llm_provider = args.llm_provider
    model_name = args.model or (
        "openai-gpt-4o" if llm_provider == "grazie" else "gpt-4o"
    )

    # Initialize components
    print("Initializing components...")
    print(f"Reading JSON data from: {json_file_path}")
    print(f"IntelliJ server URL: {ij_server_url}")
    print(f"Max items to process: {max_items}")
    print(f"Output file: {output_file}")
    print(f"LLM provider: {llm_provider}, model: {model_name}")

    # Load JSON data directly (not using benchmark loader)
    json_data = load_json_data(json_file_path)

    model = create_llm_model(llm_provider, model_name)

    # Initialize IntelliJ server
    intellij_server = ij.IntellijServer(server_url=ij_server_url)

    # Process items (limit to specified max_items for testing)
    success_count = 0
    total_count = min(max_items, len(json_data))
    results = []  # Store successful results
    cumulative_tokens = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }

    for i, item in enumerate(json_data[:total_count]):
        print(f"\n--- Processing item {i + 1}/{total_count} ---")

        # Process the item
        result = process_single_item(
            item, intellij_server, model, llm_provider, model_name
        )
        if result:  # result is now a dict with commit data or False on failure
            success_count += 1
            results.append(result)
            usage = result.get("token_usage", {})
            for key in cumulative_tokens:
                if usage.get(key) is not None:
                    cumulative_tokens[key] += usage[key]
            print(f" ✅ Successfully processed item {item.get('id', 'unknown')}")
        else:
            print(f" ❌ Failed to process item {item.get('id', 'unknown')}")

    print("\n=== Summary ===")
    print(f"Successfully processed: {success_count}/{total_count} items")
    if success_count:
        print(
            f"Total token usage: prompt={cumulative_tokens['prompt_tokens']}, "
            f"completion={cumulative_tokens['completion_tokens']}, "
            f"total={cumulative_tokens['total_tokens']}"
        )

    # Create output JSON file with results
    # Output format: array of results with fields:
    # [
    #   {
    #     "id", "v1_hash", "starting_file", "refactoring_changes", "new_commit_hash",
    #     "detected_refactorings", "recall", "precision",
    #     "true_positive_count", "false_positive_count", "token_usage"
    #   },
    #   ...
    # ]
    if results:
        with open(output_file, "w") as f:
            json.dump(results, f, indent=4)
        print(f"Results saved to: {output_file}")
        print(f"Total results: {len(results)} items")
    else:
        print("No successful results to save.")


if __name__ == "__main__":
    main()
