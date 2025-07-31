#!/bin/bash

# Shell script to download JSONL file, filter by project, and clone repositories
# Usage: ./clone_repo.sh

set -e  # Exit on any error

# Configuration - use environment variables with fallbacks
CONDA_ENV="${ANALYSIS_CONDA_ENV:-myenv}"
WORK_DIR="${ANALYSIS_WORK_DIR:-$(cd "$(dirname "$0")" && pwd)}"
FILTER_SCRIPT="filter_jsonl_by_project.py"
CLONE_SCRIPT="clone_repo.py"

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

# Main execution
main() {
    echo "Starting repository cloning workflow..."
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
    
    # Check if filter script exists
    if ! check_file_exists "$FILTER_SCRIPT"; then
        echo "✗ Filter script not found: $FILTER_SCRIPT"
        exit 1
    fi
    
    # Check if clone script exists
    if ! check_file_exists "$CLONE_SCRIPT"; then
        echo "✗ Clone script not found: $CLONE_SCRIPT"
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
    
    # Clone repositories based on the filtered projects
    echo ""
    echo "================================================"
    echo "Cloning repositories"
    echo "================================================"
    
    echo "Running: python $CLONE_SCRIPT"
    if python "$CLONE_SCRIPT"; then
        echo "✓ Successfully completed repository cloning process"
    else
        echo "✗ Repository cloning process failed"
        exit 1
    fi
    
    # Summary
    echo ""
    echo "================================================"
    echo "WORKFLOW SUMMARY"
    echo "================================================"
    echo "✓ Downloaded JSONL file from server"
    echo "✓ Filtered file by project"  
    echo "✓ Cloned repositories"
    echo ""
    echo "Files processed:"
    if [ -f "$DEFAULT_FILES_LIST" ]; then
        local project_count=$(wc -l < "$DEFAULT_FILES_LIST" 2>/dev/null || echo "0")
        echo "  - $project_count project files created"
        echo "  - Repository cloning completed"
    fi
    
    echo ""
    echo "✓ Repository cloning workflow completed successfully!"
}

# Help function
show_help() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Download JSONL file, filter by project, and clone repositories"
    echo ""
    echo "WORKFLOW:"
    echo "  1. Download JSONL file from server using SCP"
    echo "  2. Filter downloaded file by project (creates temp_*.jsonl files)"
    echo "  3. Clone repositories based on filtered projects"
    echo ""
    echo "OPTIONS:"
    echo "  -h, --help    Show this help message"
    echo ""
    echo "EXAMPLES:"
    echo "  $0                                    # Run complete workflow"
    echo ""
    echo "  # Using environment variables:"
    echo "  ANALYSIS_CONDA_ENV=production $0     # Use 'production' conda env"
    echo "  ANALYSIS_WORK_DIR=/custom/path $0    # Use custom working directory"
    echo "  SCP_PEM_FILE=my_key.pem $0          # Use different PEM file"
    echo "  SCP_SERVER_HOST=user@server.com $0  # Use different server"
    echo "  PROJECTS_BASE_PATH=/repos $0         # Set clone destination"
    echo ""
    echo "CONFIGURATION:"
    echo "  Conda Environment: $CONDA_ENV"
    echo "  Working Directory: $WORK_DIR"
    echo "  Filter Script: $FILTER_SCRIPT"
    echo "  Clone Script: $CLONE_SCRIPT"
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
    echo "  PROJECTS_BASE_PATH    Base directory for cloning repositories (required for clone_repo.py)"
}

# Check for help flag
if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    show_help
    exit 0
fi

# Run main function
main "$@" 