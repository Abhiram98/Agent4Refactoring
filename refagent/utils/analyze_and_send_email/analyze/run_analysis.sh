#!/bin/bash

# Shell script to run check_entry_from_jsonl.py with multiple JSONL files
# Usage: ./run_analysis.sh [file1.jsonl file2.jsonl ...] or ./run_analysis.sh (uses default list)

set -e  # Exit on any error

# Configuration
CONDA_ENV="myenv"
WORK_DIR="/Users/moul7361/Desktop/AI-Agents/Agent4Refactoring/refagent/utils/analyze_and_send_email/analyze"
ANALYZED_REPO_FILE="analyzed_repo.json"
PYTHON_SCRIPT="check_entry_from_jsonl.py"

# Default list of JSONL files (modify as needed)
DEFAULT_FILES=(
    "temp_azure-sdk-for-java.jsonl"
    "temp_camunda.jsonl"
    "temp_datahub.jsonl"
    "temp_eo.jsonl"
    "temp_forge.jsonl"
    "temp_graal.jsonl"
    "temp_keycloak.jsonl"
    # Add more files here as needed
)

# Function to activate conda environment
activate_conda() {
    echo "Activating conda environment: $CONDA_ENV"
    
    # Initialize conda for bash (required for conda activate to work in scripts)
    eval "$(conda shell.bash hook)"
    
    # Activate the environment
    conda activate "$CONDA_ENV"
    
    if [ $? -eq 0 ]; then
        echo "✓ Successfully activated conda environment: $CONDA_ENV"
    else
        echo "✗ Failed to activate conda environment: $CONDA_ENV"
        exit 1
    fi
}

# Function to check if file exists
check_file_exists() {
    local file="$1"
    if [ ! -f "$file" ]; then
        echo "✗ File not found: $file"
        return 1
    else
        echo "✓ Found file: $file"
        return 0
    fi
}

# Function to run analysis on a single file
run_analysis() {
    local jsonl_file="$1"
    
    echo ""
    echo "================================================"
    echo "Processing: $jsonl_file"
    echo "================================================"
    
    if check_file_exists "$jsonl_file"; then
        echo "Running: python $PYTHON_SCRIPT $jsonl_file $ANALYZED_REPO_FILE"
        
        if python "$PYTHON_SCRIPT" "$jsonl_file" "$ANALYZED_REPO_FILE"; then
            echo "✓ Successfully processed: $jsonl_file"
        else
            echo "✗ Failed to process: $jsonl_file"
            return 1
        fi
    else
        echo "✗ Skipping $jsonl_file (file not found)"
        return 1
    fi
}

# Main execution
main() {
    echo "Starting analysis workflow..."
    echo "Working directory: $WORK_DIR"
    
    # Activate conda environment
    activate_conda
    
    # Change to working directory
    echo "Changing to directory: $WORK_DIR"
    cd "$WORK_DIR"
    
    if [ $? -ne 0 ]; then
        echo "✗ Failed to change to directory: $WORK_DIR"
        exit 1
    fi
    
    # Check if analyzed_repo.json exists
    if ! check_file_exists "$ANALYZED_REPO_FILE"; then
        echo "✗ Required file not found: $ANALYZED_REPO_FILE"
        exit 1
    fi
    
    # Check if Python script exists
    if ! check_file_exists "$PYTHON_SCRIPT"; then
        echo "✗ Python script not found: $PYTHON_SCRIPT"
        exit 1
    fi
    
    # Determine which files to process
    local files_to_process=()
    
    if [ $# -gt 0 ]; then
        # Use command line arguments
        echo "Using files from command line arguments:"
        files_to_process=("$@")
    else
        # Use default list
        echo "Using default file list:"
        files_to_process=("${DEFAULT_FILES[@]}")
    fi
    
    # Display files to be processed
    echo "Files to process:"
    printf '  - %s\n' "${files_to_process[@]}"
    echo ""
    
    # Process each file
    local success_count=0
    local total_count=${#files_to_process[@]}
    
    for file in "${files_to_process[@]}"; do
        if run_analysis "$file"; then
            ((success_count++))
        fi
    done
    
    # Summary
    echo ""
    echo "================================================"
    echo "SUMMARY"
    echo "================================================"
    echo "Total files processed: $total_count"
    echo "Successfully processed: $success_count"
    echo "Failed: $((total_count - success_count))"
    
    if [ $success_count -eq $total_count ]; then
        echo "✓ All files processed successfully!"
        exit 0
    else
        echo "✗ Some files failed to process"
        exit 1
    fi
}

# Help function
show_help() {
    echo "Usage: $0 [OPTIONS] [file1.jsonl file2.jsonl ...]"
    echo ""
    echo "Run check_entry_from_jsonl.py analysis on multiple JSONL files"
    echo ""
    echo "OPTIONS:"
    echo "  -h, --help    Show this help message"
    echo ""
    echo "EXAMPLES:"
    echo "  $0                                    # Use default file list"
    echo "  $0 temp_eo.jsonl temp_mekhq.jsonl   # Process specific files"
    echo "  $0 temp_*.jsonl                     # Process all temp_*.jsonl files"
    echo ""
    echo "CONFIGURATION:"
    echo "  Conda Environment: $CONDA_ENV"
    echo "  Working Directory: $WORK_DIR"
    echo "  Analyzed Repo File: $ANALYZED_REPO_FILE"
}

# Check for help flag
if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    show_help
    exit 0
fi

# Run main function
main "$@" 