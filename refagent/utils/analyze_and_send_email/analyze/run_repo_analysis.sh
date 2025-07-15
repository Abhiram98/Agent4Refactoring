#!/bin/bash

# Shell script to run analyze_repos_by_cutoff.py with multiple JSONL files
# Usage: ./run_repo_analysis.sh [OPTIONS] [file1.jsonl file2.jsonl ...]

set -e  # Exit on any error

# Configuration
CONDA_ENV="myenv"
WORK_DIR="/Users/moul7361/Desktop/AI-Agents/Agent4Refactoring/refagent/utils/analyze_and_send_email/analyze"
PYTHON_SCRIPT="analyze_repos_by_cutoff.py"

# Default list of JSONL files (modify as needed)
#DEFAULT_FILES=(
#  "projects/temp_kafka.jsonl"
#  "projects/temp_flink.jsonl"
#  "projects/temp_spring-integration.jsonl"
#  "projects/temp_liferay-portal.jsonl"
#  "projects/temp_jetbrainsruntime.jsonl"
#  "projects/temp_intellij-community.jsonl"
#  "projects/temp_camunda.jsonl"
#  "projects/temp_jans.jsonl"
#  "projects/temp_eo.jsonl"
#  "projects/temp_osmand.jsonl"
#  "projects/temp_mekhq.jsonl"
#  "projects/temp_quarkus.jsonl"
#  "projects/temp_vespa.jsonl"
#  "projects/temp_dataease.jsonl"
#  "projects/temp_graal.jsonl"
#  "projects/temp_spring-boot.jsonl"
#  "projects/temp_google-api-java-client-services.jsonl"
#  "projects/temp_bytechef.jsonl"
#  "projects/temp_megamek.jsonl"
#  "projects/temp_thingsboard.jsonl"
#  "projects/temp_loom.jsonl"
#  "projects/temp_datahub.jsonl"
#  "projects/temp_midpoint.jsonl"
#  "projects/temp_theworldavatar.jsonl"
#  "projects/temp_keycloak.jsonl"
#  "projects/temp_opentripplanner.jsonl"
#  "projects/temp_azure-sdk-for-java.jsonl"
#  "projects/temp_openolat.jsonl"
#  "projects/temp_dataverse.jsonl"
#  "projects/temp_corretto-jdk.jsonl"
#  "projects/temp_mage.jsonl"
#  "projects/temp_shardingsphere.jsonl"
#  "projects/temp_bazel.jsonl"
#  "projects/temp_gt5-unofficial.jsonl"
#  "projects/temp_jmri.jsonl"
#  "projects/temp_valhalla.jsonl"
#  "projects/temp_forge.jsonl"
#  "projects/temp_languagetool.jsonl"
#  "projects/temp_cas.jsonl"
#  "projects/temp_product-is.jsonl"
#  "projects/temp_tutorials.jsonl"
#  "projects/temp_gravitee-api-management.jsonl"
#  "projects/temp_metersphere.jsonl"
#)

DEFAULT_FILES=(
  "projects/temp_valhalla.jsonl"

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

# Function to check if Python script exists
check_python_script() {
    if [ ! -f "$PYTHON_SCRIPT" ]; then
        echo "✗ Python script not found: $PYTHON_SCRIPT"
        exit 1
    else
        echo "✓ Found Python script: $PYTHON_SCRIPT"
    fi
}

# Function to run repository analysis
run_repo_analysis() {
    local cutoff_date=""
    local dry_run=""
    local force=""
    local files_to_process=()
    
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --cutoff-date)
                cutoff_date="$2"
                shift 2
                ;;
            --dry-run)
                dry_run="--dry-run"
                shift
                ;;
            --force)
                force="--force"
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *.jsonl)
                files_to_process+=("$1")
                shift
                ;;
            *)
                echo "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    # Use default files if none provided
    if [ ${#files_to_process[@]} -eq 0 ]; then
        echo "No JSONL files provided, using default list..."
        files_to_process=("${DEFAULT_FILES[@]}")
    fi
    
    # Build command
    local cmd="python $PYTHON_SCRIPT"
    
    if [ -n "$cutoff_date" ]; then
        cmd="$cmd --cutoff-date $cutoff_date"
    fi
    
    if [ -n "$dry_run" ]; then
        cmd="$cmd $dry_run"
    fi
    
    if [ -n "$force" ]; then
        cmd="$cmd $force"
    fi
    
    # Add files to command
    for file in "${files_to_process[@]}"; do
        cmd="$cmd $file"
    done
    
    echo "Running command: $cmd"
    echo ""
    
    # Execute the command
    eval "$cmd"
}

# Help function
show_help() {
    echo "Usage: $0 [OPTIONS] [file1.jsonl file2.jsonl ...]"
    echo ""
    echo "Run repository analysis by cutoff date using multiple JSONL files"
    echo ""
    echo "OPTIONS:"
    echo "  --cutoff-date DATE    Cutoff date for analysis (YYYY-MM-DD)"
    echo "                        If not provided, uses default (2024-01-01) or environment variable"
    echo "  --dry-run             Show what would be processed without actually running analysis"
    echo "  --force               Force reanalysis of already analyzed repositories and regenerate batch results"
    echo "  -h, --help            Show this help message"
    echo ""
    echo "EXAMPLES:"
    echo "  $0                                                    # Use default files and cutoff date"
    echo "  $0 --cutoff-date 2024-06-01                         # Use default files with custom cutoff date"
    echo "  $0 --dry-run                                         # Show what would be processed"
    echo "  $0 --force                                           # Force reanalysis of all repositories"
    echo "  $0 projects/temp_kafka.jsonl projects/temp_flink.jsonl  # Process specific files"
    echo "  $0 --cutoff-date 2024-06-01 projects/temp_*.jsonl   # Custom date with specific files"
    echo "  $0 --force --cutoff-date 2024-06-01 projects/temp_kafka.jsonl  # Force reanalysis with custom date"
    echo ""
    echo "CONFIGURATION:"
    echo "  Conda Environment: $CONDA_ENV"
    echo "  Working Directory: $WORK_DIR"
    echo "  Python Script: $PYTHON_SCRIPT"
    echo ""
    echo "ENVIRONMENT VARIABLES:"
    echo "  REFACTORING_SINCE_DATE    Override default cutoff date"
    echo "  PROJECTS_BASE_PATH        Base path for repository projects"
}

# Function to validate date format
validate_date() {
    local date_str="$1"
    if [[ ! "$date_str" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
        echo "✗ Invalid date format: $date_str"
        echo "Please use YYYY-MM-DD format (e.g., 2024-01-01)"
        exit 1
    fi
}

# Main execution
main() {
    echo "Starting repository analysis workflow..."
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
    
    # Check if Python script exists
    check_python_script
    
    # Validate cutoff date if provided
    for arg in "$@"; do
        case $arg in
            --cutoff-date)
                shift
                validate_date "$1"
                break
                ;;
        esac
    done
    
    # Run repository analysis
    run_repo_analysis "$@"
}

# Check for help flag first
if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    show_help
    exit 0
fi

# Run main function
main "$@" 