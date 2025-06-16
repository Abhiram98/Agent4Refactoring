import json
import re
from collect_commits import get_commits, process_commits_with_refactoringminer, save_commits_to_file, get_commits_since_date, filter_commits_by_date
from process_batch import collect_rename_refactorings, save_results_to_json, collect_rename_refactorings_count, process_and_save_commit_metadata
from plot_utils import create_weekly_plot, create_heatmap, load_and_enrich_data, create_comprehensive_developer_analysis, create_json_analysis
from git_utils import git_pull
from raw_json_to_csv import convert_to_csv
import pandas as pd
import os

# Default date filter - set to 2024-01-01 by default to exclude older data
DEFAULT_SINCE_DATE = "2024-01-01"

def get_since_date():
    """
    Get the date filter to use. Can be overridden by environment variable or config.
    Returns the date string in YYYY-MM-DD format.
    """
    import os
    # Allow override via environment variable
    env_date = os.environ.get('REFACTORING_SINCE_DATE')
    if env_date:
        print(f"Using date filter from environment variable: {env_date}")
        return env_date
    return DEFAULT_SINCE_DATE



def analyze_repo_with_new_commits(res, filepath_to_analyzed_repo):
    print(f"Analyzing repo with new commits: {res['local_repo_path']}")
    # Create JSON analysis (with optional commit hash analysis)
    print("\nCreating comprehensive JSON analysis...")
    developer_name = res['developer_name']
    # Handle names with various separators (spaces, dots, underscores, hyphens)
    # Split by common separators and take the first part
    output_dir = f'refactoring_results_{res["processed_project_info"]["project"]}'

    csv_file = f'{output_dir}/rename_analysis_results_count.csv'
    if not os.path.exists(csv_file):
        batch_output_dir = f'{output_dir}/batch_results'
        results, total_files_analyzed, count = collect_rename_refactorings(batch_output_dir)
        results, total_files_analyzed, count = collect_rename_refactorings_count(batch_output_dir)
        df, original_commit_count = process_and_save_commit_metadata(results, f'{output_dir}/rename_analysis_results_count.csv', res['local_repo_path']) 
    else: 
        df = pd.read_csv(csv_file)
    # df, original_commit_count = load_and_enrich_data(f'{output_dir}/rename_analysis_results_count.csv', res['local_repo_path'])
    first_name = re.split(r'[ .\-_]+', developer_name.strip())[0]
    
    # Get the date filter to use
    since_date = get_since_date()
    
    # Get the total commits found for this analysis
    total_commits_initial = get_commits_since_date(res['local_repo_path'], since_date=since_date)
    print(f"Initial commits found from git (since {since_date}): {len(total_commits_initial)}")
    
    # Double-check commit timestamps and filter
    # total_commits_found = filter_commits_by_date(total_commits_initial, res['local_repo_path'], since_date)
    total_commits_found = total_commits_initial
    total_commits_count = len(total_commits_found)
    print(f"Final commits after timestamp verification: {total_commits_count}")
    
    json_data = create_json_analysis(df, res['local_repo_path'], f'{output_dir}/developer_analysis', target_commit_hash=res['json_data_from_jsonl']['v2_hash'], project_name=res['json_data_from_jsonl']['project'], developer_name=first_name, original_commit_count=total_commits_count)

def analyze_repo_from_beginning(res, filepath_to_analyzed_repo):
    git_pull(res['local_repo_path'])
    print(f"Pulled repo: {res['local_repo_path']}")
    
    # Get the date filter to use
    since_date = get_since_date()
    print(f"Analyzing repo from {since_date} onwards...")
    
    # commits = get_commits(res['local_repo_path'], max_commits=20000)
    commits_initial = get_commits_since_date(res['local_repo_path'], since_date=since_date)
    print(f"Initial commits found from git (since {since_date}): {len(commits_initial)}")
    
    # Double-check commit timestamps and filter
    # commits = filter_commits_by_date(commits_initial, res['local_repo_path'], since_date)
    commits = commits_initial
    total_commits_count = len(commits)
    print(f"Final commits after timestamp verification: {total_commits_count}")
    
    output_dir = f'refactoring_results_{res["processed_project_info"]["project"]}'
    save_commits_to_file(commits, f'{output_dir}/commits.txt')
    batch_output_dir = f'{output_dir}/batch_results'
    actual_batch_count, successful_batches, failed_batches = process_commits_with_refactoringminer(
                repo_path=str(res['local_repo_path']),
                commits=commits,
                output_dir=batch_output_dir,
                max_batch_size=500
            )
    results, total_files_analyzed, count = collect_rename_refactorings(batch_output_dir)
    save_results_to_json(results, f'{output_dir}/rename_analysis_results.json')
    convert_to_csv(f'{output_dir}/rename_analysis_results.json', f'{output_dir}/rename_analysis_results.csv')

    results, total_files_analyzed, count = collect_rename_refactorings_count(batch_output_dir)

    print(f"Total Rename commit count: {count}")
    
    print("\nSaving results to CSV file...")
    df, original_commit_count = process_and_save_commit_metadata(results, f'{output_dir}/rename_analysis_results_count.csv', res['local_repo_path'])

    # df, original_commit_count = load_and_enrich_data(f'{output_dir}/rename_analysis_results_count.csv', res['local_repo_path'])

    # Create weekly plot
    print("\nCreating weekly time series plot...")
    weekly_csv_data, summary_data = create_weekly_plot(df, f'{output_dir}/plots', res['processed_project_info']['project'], since_date="2024-01-01")
        
    # Create heatmap
    print("\nCreating heatmap of rename activity...")
    heatmap_data = create_heatmap(df, f'{output_dir}/plots')

    # Create comprehensive developer analysis
    print("\nCreating comprehensive developer analysis for all commits...")
    comprehensive_stats, df_with_authors = create_comprehensive_developer_analysis(df, res['local_repo_path'], output_dir)
        
    # Create JSON analysis (with optional commit hash analysis)
    print("\nCreating comprehensive JSON analysis...")
    developer_name = res['processed_project_info']['mail_sent_to_developer'][0]['developer_name']
    # Handle names with various separators (spaces, dots, underscores, hyphens)
    # Split by common separators and take the first part
    first_name = re.split(r'[ .\-_]+', developer_name.strip())[0]
    json_data = create_json_analysis(df, res['local_repo_path'], f'{output_dir}/developer_analysis', target_commit_hash=res['json_data_from_jsonl']['v2_hash'], project_name=res['json_data_from_jsonl']['project'], developer_name=first_name, original_commit_count=total_commits_count)

    print(f"Actual batch count: {actual_batch_count}")
    print(f"Successful batches: {successful_batches}")
    print(f"Failed batches: {failed_batches}")

    # Read existing data first
    with open(filepath_to_analyzed_repo, 'r', encoding='utf-8') as file:
        data = json.load(file)
    
    # Update the entry
    for entry in data:
        if entry['project'] == res['processed_project_info']['project']:
            entry['batch_anlayzed'] = actual_batch_count
            entry['total_commits_found'] = total_commits_count
    
    # Write updated data back
    with open(filepath_to_analyzed_repo, 'w', encoding='utf-8') as file:
        json.dump(data, file, indent=4, ensure_ascii=False)