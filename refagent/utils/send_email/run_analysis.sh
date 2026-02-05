#!/bin/bash

# Shell script to download, filter, analyze JSONL files, generate emails, and collect them
# Usage: ./run_analysis.sh [file1.jsonl file2.jsonl ...] or ./run_analysis.sh (uses default list)

# set -e  # Exit on any error

# Configuration - use environment variables with fallbacks
CONDA_ENV="${ANALYSIS_CONDA_ENV:-myenv}"
WORK_DIR="${ANALYSIS_WORK_DIR:-$(cd "$(dirname "$0")" && pwd)}"
ANALYZED_REPO_FILE="analyzed_repo.json"
PYTHON_SCRIPT="analyze_repos_by_cutoff_date.py"
FILTER_SCRIPT="filter_jsonl_by_project.py"
EMAIL_SCRIPT="generate_all_emails.py"
COLLECT_EMAILS_SCRIPT="collect_emails.py"

# File containing list of JSONL files to process
DEFAULT_FILES_LIST="projects/created_files.txt"

# SCP Download configuration
PEM_FILE="${SCP_PEM_FILE:-analysis_result/key.pem}"
SERVER_HOST="${SCP_SERVER_HOST:-azureuser@172.210.10.30}"
REMOTE_FILE_PATH="${SCP_REMOTE_PATH:-/home/azureuser/Agent4Refactoring/data/monitoring/monitor_results.jsonl}"
LOCAL_FILE_NAME="${SCP_LOCAL_FILE:-monitor_results.jsonl}"
DOWNLOAD_DIR="analysis_result"  # Downloads to $WORK_DIR/analysis_result

# Function to download file from server using SCP
download_server_file() {
    local pem_file="$1"
    local server_host="$2"
    local remote_path="$3"
    local local_file="$4"
    local download_dir="$5"
    
    echo ""
    echo "================================================"
    echo "Downloading file from server"
    echo "================================================"
    
    # Create download directory if it doesn't exist
    if [ ! -d "$download_dir" ]; then
        echo "Creating download directory: $download_dir"
        mkdir -p "$download_dir"
    fi
    
    # Check if PEM file exists
    if [ ! -f "$pem_file" ]; then
        echo "✗ PEM file not found: $pem_file"
        echo "  Please ensure the PEM file exists in the analysis_result directory"
        return 1
    fi
    
    # Set proper permissions for PEM file
    chmod 600 "$pem_file"
    
    local local_path="$download_dir/$local_file"
    local full_local_path="$(pwd)/$local_path"
    
    echo "PEM file: $pem_file"
    echo "Server: $server_host"
    echo "Remote path: $remote_path"
    echo "Local path: $local_path"
    echo "Full path: $full_local_path"
    echo ""
    
    echo "Running: scp -i $pem_file $server_host:$remote_path $local_path"
    
    if scp -i "$pem_file" "$server_host:$remote_path" "$local_path"; then
        echo "✓ Successfully downloaded file to: $local_path"
        
        # Check if file was actually downloaded and has content
        if [ -s "$local_path" ]; then
            local file_size=$(stat -f%z "$local_path" 2>/dev/null || stat -c%s "$local_path" 2>/dev/null || echo "unknown")
            echo "  File size: $file_size bytes"
            return 0
        else
            echo "✗ Downloaded file is empty: $local_path"
            return 1
        fi
    else
        echo "✗ Failed to download file from server"
        echo "  Check network connectivity, server access, and file paths"
        return 1
    fi
}

# Function to load default files from the file list
load_default_files() {
    local files_list_path="$1"
    local default_files=()
    
    if [ ! -f "$files_list_path" ]; then
        echo "✗ Default files list not found: $files_list_path"
        echo "  Please ensure the file exists or provide files as command line arguments"
        return 1
    fi
    
    echo "Loading default files from: $files_list_path"
    
    # Read file line by line, filtering out empty lines and comments
    while IFS= read -r line || [ -n "$line" ]; do
        # Skip empty lines and lines starting with #
        if [[ -n "$line" && ! "$line" =~ ^[[:space:]]*# ]]; then
            # Trim whitespace
            line=$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
            if [ -n "$line" ]; then
                default_files+=("$line")
            fi
        fi
    done < "$files_list_path"
    
    if [ ${#default_files[@]} -eq 0 ]; then
        echo "✗ No valid files found in: $files_list_path"
        return 1
    fi
    
    echo "✓ Loaded ${#default_files[@]} files from list"
    
    # Return the array by printing it (will be captured by caller)
    printf '%s\n' "${default_files[@]}"
    return 0
}

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
        echo "Running: python $PYTHON_SCRIPT \"$jsonl_file\" --analyzed-repo-file \"$ANALYZED_REPO_FILE\""
        
        if python "$PYTHON_SCRIPT" "$jsonl_file" --analyzed-repo-file "$ANALYZED_REPO_FILE"; then
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
    echo "Resolved configuration:"
    echo "  Conda environment: $CONDA_ENV"
    echo "  Working directory: $WORK_DIR"
    echo "  PEM file: $PEM_FILE"
    echo "  Server host: $SERVER_HOST"
    echo "  Remote file: $REMOTE_FILE_PATH"
    echo "  Local file: $DOWNLOAD_DIR/$LOCAL_FILE_NAME"
    
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
    
    # Check if filter script exists
    if ! check_file_exists "$FILTER_SCRIPT"; then
        echo "✗ Filter script not found: $FILTER_SCRIPT"
        exit 1
    fi
    
    # Check if email generation script exists
    if ! check_file_exists "$EMAIL_SCRIPT"; then
        echo "✗ Email generation script not found: $EMAIL_SCRIPT"
        exit 1
    fi
    
    # Check if email collection script exists
    if ! check_file_exists "$COLLECT_EMAILS_SCRIPT"; then
        echo "✗ Email collection script not found: $COLLECT_EMAILS_SCRIPT"
        exit 1
    fi
    
    # Download required file from server
    echo "Downloading required file from server..."
    if ! download_server_file "$PEM_FILE" "$SERVER_HOST" "$REMOTE_FILE_PATH" "$LOCAL_FILE_NAME" "$DOWNLOAD_DIR"; then
        echo "✗ Failed to download required file from server"
        exit 1
    fi
    
    # Filter the downloaded JSONL file by project to generate individual project files
    local downloaded_file="$DOWNLOAD_DIR/$LOCAL_FILE_NAME"
    echo ""
    echo "================================================"
    echo "Filtering JSONL file by project"
    echo "================================================"
    echo "Processing downloaded file: $downloaded_file"
    
    if [ ! -f "$downloaded_file" ]; then
        echo "✗ Downloaded file not found: $downloaded_file"
        exit 1
    fi
    
    # Quick validation of the downloaded JSONL file
    echo "Validating downloaded JSONL file..."
    local line_count=$(wc -l < "$downloaded_file" 2>/dev/null || echo "0")
    echo "File contains $line_count lines"
    
    # Show first few characters of first line for debugging
    if [ -s "$downloaded_file" ]; then
        local first_line=$(head -n 1 "$downloaded_file")
        if [ ${#first_line} -gt 100 ]; then
            echo "First line preview: ${first_line:0:100}..."
        else
            echo "First line preview: $first_line"
        fi
    fi
    
    echo "Running: python $FILTER_SCRIPT $downloaded_file"
    if python "$FILTER_SCRIPT" "$downloaded_file"; then
        echo "✓ Successfully filtered JSONL file by project"
        
        # Verify that created_files.txt was generated
        if [ -f "$DEFAULT_FILES_LIST" ]; then
            local file_count=$(wc -l < "$DEFAULT_FILES_LIST" 2>/dev/null || echo "0")
            echo "✓ Generated $file_count project files listed in $DEFAULT_FILES_LIST"
        else
            echo "⚠ Warning: $DEFAULT_FILES_LIST was not created"
        fi
    else
        echo "✗ Failed to filter JSONL file by project"
        exit 1
    fi
    
    # Determine which files to process
    local files_to_process=()
    
    if [ $# -gt 0 ]; then
        # Use command line arguments
        echo "Using files from command line arguments:"
        files_to_process=("$@")
    else
        # Load default list from file
        echo "Using default file list from: $DEFAULT_FILES_LIST"
        
        # Load files from the list file
        local loaded_files
        if loaded_files=$(load_default_files "$DEFAULT_FILES_LIST"); then
            # Convert the output to an array (compatible with older shells)
            files_to_process=()
            while IFS= read -r line; do
                [ -n "$line" ] && files_to_process+=("$line")
            done <<< "$loaded_files"
        else
            echo "✗ Failed to load default files list"
            exit 1
        fi
        
        # For testing: use just one file (COMMENTED OUT - RESTORED FULL PROCESSING)
        # echo "Using test file: projects/temp_flink.jsonl"
        # files_to_process=("projects/temp_flink.jsonl")
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
    
    # Generate emails for all projects after analysis is complete
    if [ $success_count -gt 0 ]; then
        echo ""
        echo "================================================"
        echo "Generating emails for analyzed projects"
        echo "================================================"
        
        echo "Running: python $EMAIL_SCRIPT $DOWNLOAD_DIR --analyzed-repo-file $ANALYZED_REPO_FILE"
        if python "$EMAIL_SCRIPT" "$DOWNLOAD_DIR" --analyzed-repo-file "$ANALYZED_REPO_FILE"; then
            echo "✓ Successfully generated emails for all projects"
            
            # Collect all generated emails into a centralized directory
            echo ""
            echo "================================================"
            echo "Collecting emails from all projects"
            echo "================================================"
            
            echo "Running: python $COLLECT_EMAILS_SCRIPT $DOWNLOAD_DIR"
            if python "$COLLECT_EMAILS_SCRIPT" "$DOWNLOAD_DIR"; then
                echo "✓ Successfully collected all email files"
            else
                echo "⚠ Warning: Email collection failed, but emails were generated successfully"
            fi
        else
            echo "⚠ Warning: Email generation failed, but analysis completed successfully"
        fi
    fi
    
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
    echo "Download server file, filter by project, run analysis, generate emails, and collect them"
    echo ""
    echo "WORKFLOW:"
    echo "  1. Download JSONL file from server using SCP"
    echo "  2. Filter downloaded file by project (creates temp_*.jsonl files)"
    echo "  3. Run analysis on each project file"
    echo "  4. Generate emails for all analyzed projects"
    echo "  5. Collect all emails into a centralized directory"
    echo ""
    echo "OPTIONS:"
    echo "  -h, --help    Show this help message"
    echo ""
    echo "EXAMPLES:"
    echo "  $0                                    # Use default file list from $DEFAULT_FILES_LIST"
    echo "  $0 temp_eo.jsonl temp_mekhq.jsonl   # Process specific files"
    echo "  $0 temp_*.jsonl                     # Process all temp_*.jsonl files"
    echo ""
    echo "  # Using environment variables:"
    echo "  ANALYSIS_CONDA_ENV=production $0     # Use 'production' conda env"
    echo "  ANALYSIS_WORK_DIR=/custom/path $0    # Use custom working directory"
    echo "  SCP_PEM_FILE=my_key.pem $0          # Use different PEM file"
    echo "  SCP_SERVER_HOST=user@server.com $0  # Use different server"
    echo ""
    echo "CONFIGURATION:"
    echo "  Conda Environment: $CONDA_ENV"
    echo "  Working Directory: $WORK_DIR"
    echo "  Analyzed Repo File: $ANALYZED_REPO_FILE"
    echo "  Python Script: $PYTHON_SCRIPT"
    echo "  Filter Script: $FILTER_SCRIPT"
    echo "  Email Script: $EMAIL_SCRIPT"
    echo "  Collect Emails Script: $COLLECT_EMAILS_SCRIPT"
    echo "  Default Files List: $DEFAULT_FILES_LIST"
    echo "  PEM File: $PEM_FILE"
    echo "  Server Host: $SERVER_HOST"
    echo "  Remote File Path: $REMOTE_FILE_PATH"
    echo "  Local File Name: $LOCAL_FILE_NAME"
    echo ""
    echo "ENVIRONMENT VARIABLES:"
    echo "  ANALYSIS_CONDA_ENV    Override conda environment (default: myenv)"
    echo "  ANALYSIS_WORK_DIR     Override working directory (default: relative to script)"
    echo "  SCP_PEM_FILE          Path to PEM file for server access (default: analysis_result/key.pem)"
    echo "  SCP_SERVER_HOST       Server host for SCP download (default: azureuser@172.210.10.30)"
    echo "  SCP_REMOTE_PATH       Remote file path to download (default: /home/azureuser/Agent4Refactoring/data/monitoring/monitor_results.jsonl)"
    echo "  SCP_LOCAL_FILE        Local filename for downloaded file (default: monitor_results.jsonl)"
}

# Check for help flag
if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    show_help
    exit 0
fi

# Run main function
main "$@" 
