import csv
import re
from pathlib import Path
import json
from datetime import datetime
import os
import time
import tiktoken
from grazie.api.client.endpoints import GrazieApiGatewayUrls
from grazie.api.client.gateway import AuthType
from grazie_langchain_utils.language_models.grazie import ChatGrazie
from pydantic import SecretStr
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Constants
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GRAZIE_JWT_TOKEN = os.getenv("GRAZIE_JWT_TOKEN")
LLM_MODEL = "gpt-4o"

def get_pure_rename_pair(description):
    if not description:
        return None
    
    # Try to extract the type pattern: "varname : Type to newvarname : Type"
    pattern = r'(\w+)\s*:\s*(\S+)\s+to\s+(\w+)\s*:\s*(\S+)'
    match = re.search(pattern, description)
    
    if match:
        name_before, type_before, name_after, type_after = match.groups()
        # Check if it's a pure rename (same type)
        if type_before == type_after:
            return {
                'before': name_before,
                'after': name_after,
                'type': type_before
            }
    return None

def count_tokens_with_tiktoken(text: str, model_name: str = LLM_MODEL) -> int:
    """Count tokens accurately using tiktoken library."""
    try:
        encoding = tiktoken.encoding_for_model(model_name)
        return len(encoding.encode(text))
    except Exception as e:
        print(f"Warning: Error counting tokens with tiktoken for model {model_name}: {e}")
        # Fallback to rough estimation if tiktoken fails
        return len(text) // 4

def get_model_context_window(model_name: str = LLM_MODEL) -> int:
    """Get the context window size for a given model."""
    MODEL_CONTEXT_WINDOWS = {
        "gpt-4": 8192,
        "gpt-4-32k": 32768,
        "gpt-4o": 128000,
        "gpt-4o-mini": 128000,
        "gpt-3.5-turbo": 4096,
        "gpt-3.5-turbo-16k": 16384,
    }
    
    context_window = MODEL_CONTEXT_WINDOWS.get(model_name)
    if not context_window:
        print(f"Warning: Unknown model {model_name}, using conservative default of 8k tokens")
        context_window = 8192
    
    print(f"Model {model_name} context window size: {context_window} tokens")
    return context_window

def get_response_buffer_size(model_name: str = LLM_MODEL) -> int:
    """Calculate response buffer size based on model context window."""
    context_window = get_model_context_window(model_name)
    
    if context_window > 16384:  # >16k
        buffer_size = int(context_window * 0.15)  # 15% of context window
    else:  # ≤16k
        buffer_size = min(2000, int(context_window * 0.20))  # 20% or 2000, whichever is smaller
    
    print(f"Response buffer size for {model_name}: {buffer_size} tokens")
    return buffer_size

def create_rename_batches(name_pairs, max_tokens_per_batch=18000, min_pairs_per_batch=1, model_name=LLM_MODEL):
    """Create batches of rename pairs based on token counts."""
    batches = []
    current_batch = []
    current_token_count = 0
    
    # Calculate prompt template tokens
    template_text = """You are an expert in code naming conventions and refactoring. 
    Analyze the following variable name changes and identify patterns in naming conventions:

    For each pair, identify:
    1. The type of change (e.g., spelling correction, style change, semantic improvement)
    2. The naming convention being followed (e.g., camelCase, PascalCase, snake_case)
    3. The reason for the change (e.g., consistency, clarity, correctness)
    """
    template_tokens = count_tokens_with_tiktoken(template_text, model_name)
    response_buffer_tokens = get_response_buffer_size(model_name)
    
    # Calculate available tokens for pairs content
    available_tokens = max_tokens_per_batch - template_tokens - response_buffer_tokens
    
    print(f"\nCreating batches (max {max_tokens_per_batch} tokens per batch)...")
    print(f"Model: {model_name}")
    print(f"Template tokens: {template_tokens}")
    print(f"Response buffer tokens: {response_buffer_tokens}")
    print(f"Available tokens for pairs content: {available_tokens}")
    
    for pair in name_pairs:
        # Estimate tokens for this pair
        pair_text = json.dumps(pair)
        pair_tokens = count_tokens_with_tiktoken(pair_text, model_name)
        
        # If this pair alone exceeds available tokens, warn but include it in its own batch
        if pair_tokens > available_tokens:
            print(f"\nWarning: A pair requires {pair_tokens} tokens, which exceeds the available {available_tokens} tokens.")
            if not current_batch:  # If we have to start a new batch anyway
                print(f"Creating a separate batch for this large pair.")
                batches.append([pair])
                continue
        
        # If adding this pair would exceed the limit and we have minimum pairs
        if current_token_count + pair_tokens > available_tokens and len(current_batch) >= min_pairs_per_batch:
            # Add current batch to batches and start a new one
            batches.append(current_batch)
            current_batch = [pair]
            current_token_count = pair_tokens
        else:
            # Add pair to current batch
            current_batch.append(pair)
            current_token_count += pair_tokens
    
    # Add the final batch if it's not empty
    if current_batch:
        batches.append(current_batch)
    
    # Print batch information
    print(f"\nCreated {len(batches)} batches:")
    for i, batch in enumerate(batches):
        batch_text = json.dumps(batch)
        batch_tokens = count_tokens_with_tiktoken(batch_text, model_name)
        total_batch_tokens = batch_tokens + template_tokens + response_buffer_tokens
        print(f"  Batch {i+1}: {len(batch)} pairs")
        print(f"    - Content tokens: {batch_tokens}")
        print(f"    - Total tokens (with template): {total_batch_tokens}")
        # print(f"    - Utilization: {total_batch_tokens/int(get_model_context_window("gpt-4o-mini"))*100:.1f}% of context window")
    
    return batches

def analyze_naming_patterns_with_grazie(name_pairs):
    """Analyze naming patterns using Grazie LLM"""
    # Initialize Grazie model
    model = ChatGrazie(
        grazie_jwt_token=SecretStr(os.getenv("GRAZIE_JWT_TOKEN")),
        client_auth_type=AuthType.APPLICATION,
        client_url=GrazieApiGatewayUrls.STAGING,
        profile="openai-gpt-4o-mini",  # Using GPT-4o mini model
        client_agent_name='naming-patterns-agent',
        client_agent_version='0.1'
    )

    # Get model context window and create batches
    model_context_window = get_model_context_window("gpt-4o-mini")
    max_batch_tokens = int(model_context_window * 0.75)  # Use 75% of context window
    batches = create_rename_batches(name_pairs, max_tokens_per_batch=max_batch_tokens)
    
    # Process each batch
    batch_results = []
    for i, batch in enumerate(batches):
        batch_name = f"Batch-{i+1}"
        print(f"\nProcessing {batch_name} ({len(batch)} pairs)...")
        
        # Create prompt for this batch
        prompt = f"""You are an expert in code naming conventions and refactoring. 
        You are given a list of variable name changes from commits. Analyze the following variable name changes and identify patterns in naming conventions:

        {json.dumps(batch, indent=2)}

        For the given list of variable name changes, you need to extract some rules that are applicable to the project and later develoer can follow those rules to maintain consistency.
        You keep in mind the following points to make the rules:
        1. Common patterns in naming conventions.
        2. Common style changes in naming conventions.
        3. Frequently prefix, suffix, infix, abbreviations, acronyms, etc.
        Return a JSON object in the following structure:
        {{
             "rules": [
                {{
                    "rule": "rule_description",
                    "example_names": [List of variable names as before -> after]
                }}
            ]
        }}
        Make sure the rules are applicable to the project and are not too general. Write at least 10 rules. Don't put same name as before -> after in example_names.
        Some of the pairs may be wrong and never used in the code and got rejected by the developer. So try to understand the majority of the pairs and common patterns and make rules accordingly. Don't include incorrect pairs in the rules.
        """

        try:
            response = model.invoke(prompt)
            
            response_text = response.content
            json_match = re.search(r'```json\n(.*?)\n```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = response_text
            
            # Clean up the JSON string
            json_str = re.sub(r'```.*?```', '', json_str, flags=re.DOTALL)
            
            # Parse the response
            result = json.loads(json_str)
            
            # Add metadata
            result["metadata"] = {
                "batch": batch_name,
                "pairs_in_batch": len(batch),
                "timestamp": datetime.now().isoformat()
            }
            
            batch_results.append(result)
            
            # Add a small delay between batches
            if i < len(batches) - 1:
                time.sleep(2)  # To avoid rate limiting
            
        except Exception as e:
            print(f"Error processing {batch_name}: {str(e)}")
            batch_results.append({
                "error": str(e),
                "metadata": {
                    "batch": batch_name,
                    "pairs_in_batch": len(batch),
                    "timestamp": datetime.now().isoformat()
                }
            })
    
    return batch_results

def aggregate_batch_results(batch_results):
    """Aggregate results from multiple batches into a single analysis."""
    aggregated = {
        "rules": [],
        "metadata": {
            "total_pairs_analyzed": 0,
            "batches": [],
            "timestamp": datetime.now().isoformat()
        }
    }
    
    # Track unique rules to avoid duplicates
    unique_rules = set()
    
    # Process each batch result
    for batch_result in batch_results:
        if "error" in batch_result:
            continue
            
        # Add unique rules
        for rule_entry in batch_result.get("rules", []):
            rule_text = rule_entry.get("rule", "")
            if rule_text and rule_text not in unique_rules:
                unique_rules.add(rule_text)
                aggregated["rules"].append(rule_entry)
        
        # Add batch metadata
        aggregated["metadata"]["batches"].append(batch_result["metadata"])
        aggregated["metadata"]["total_pairs_analyzed"] += batch_result["metadata"]["pairs_in_batch"]
    
    return aggregated

def main():
    base_dir = Path.cwd()
    input_file = base_dir / "rename_analysis_results" / "pure_rename_variables.csv"
    output_dir = base_dir / "commit_analysis_results"
    
    # Create output directory if it doesn't exist
    output_dir.mkdir(exist_ok=True)
    
    # Read the CSV file and extract rename pairs
    name_pairs = []
    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            description = row.get('Description', '')
            rename_pair = get_pure_rename_pair(description)
            if rename_pair:
                name_pairs.append(rename_pair)  # Only include the rename pair without description
    
    print(f"Found {len(name_pairs)} pure rename variable pairs")
    print("\nFirst 10 rename pairs:")
    for i, pair in enumerate(name_pairs[:10]):
        print(f"{i+1}. {pair['before']} -> {pair['after']} (type: {pair['type']})")
    print()
    
    # Analyze naming patterns using Grazie LLM
    batch_results = analyze_naming_patterns_with_grazie(name_pairs)
    
    # Aggregate results
    aggregated_results = aggregate_batch_results(batch_results)
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save aggregated results
    aggregated_file = output_dir / f"naming_patterns_analysis_{timestamp}.json"
    with open(aggregated_file, 'w', encoding='utf-8') as f:
        json.dump(aggregated_results, f, indent=2, ensure_ascii=False)
    print(f"\nAggregated results saved to {aggregated_file}")
    
    # Save batch results
    batch_file = output_dir / f"naming_patterns_batches_{timestamp}.json"
    with open(batch_file, 'w', encoding='utf-8') as f:
        json.dump(batch_results, f, indent=2, ensure_ascii=False)
    print(f"Batch results saved to {batch_file}")
    
    # Print summary
    print("\nAnalysis Summary:")
    print(f"- Total pairs analyzed: {aggregated_results['metadata']['total_pairs_analyzed']}")
    print(f"- Total batches processed: {len(batch_results)}")
    print(f"- Total unique rules extracted: {len(aggregated_results['rules'])}")

if __name__ == "__main__":
    main() 