import json
import re
from collect_commits import get_commits, process_commits_with_refactoringminer, save_commits_to_file, get_commits_since_date, filter_commits_by_date
from process_batch import collect_rename_refactorings, save_results_to_json, collect_rename_refactorings_count, process_and_save_commit_metadata
from plot_utils import create_weekly_plot, create_heatmap, load_and_enrich_data, create_comprehensive_developer_analysis, create_json_analysis
from git_utils import git_pull
from raw_json_to_csv import convert_to_csv
import pandas as pd
import os
from datetime import datetime

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


def analyze_repo_with_new_commits(res, filepath_to_analyzed_repo, renamed_attributes):
    print(f"Analyzing already existed repo")
    output_dir = f'refactoring_results_{res["processed_project_info"]["project"]}'
    batch_output_dir = f'{output_dir}/batch_results'

    if len(res['new_commits']) != 0:
        print(f"New commits found: {len(res['new_commits'])}")
        save_commits_to_file(res['new_commits'], f'{output_dir}/commits.txt')
        actual_batch_count, successful_batches, failed_batches = process_commits_with_refactoringminer(
                repo_path=str(res['local_repo_path']),
                commits=res['new_commits'],
                output_dir=batch_output_dir,
                max_batch_size=500, 
                start_batch_index=res['batch_anlayzed']
            )
        # Process rename analysis results
        df, original_commit_count = process_rename_analysis_results(batch_output_dir, output_dir, res)

        # Create plots
        weekly_csv_data, summary_data, heatmap_data = create_plots(df, output_dir, res['processed_project_info']['project'])
        
    # Create JSON analysis (with optional commit hash analysis)
    print("\nCreating comprehensive JSON analysis...")
    developer_name = res['developer_name']
    developer_email = res['developer_email']

    csv_file = f'{output_dir}/rename_analysis_results_count.csv'
    if not os.path.exists(csv_file):
        results, total_files_analyzed, count = collect_rename_refactorings(batch_output_dir)
        results, total_files_analyzed, count = collect_rename_refactorings_count(batch_output_dir)
        df, original_commit_count = process_and_save_commit_metadata(results, f'{output_dir}/rename_analysis_results_count.csv', res['local_repo_path']) 
    else: 
        df = pd.read_csv(csv_file)
    # df, original_commit_count = load_and_enrich_data(f'{output_dir}/rename_analysis_results_count.csv', res['local_repo_path'])
    first_name = re.split(r'[ .\-_]+', developer_name.strip())[0]
    
    # Get the total commits found for this analysis
    total_commits_initial = get_commits_since_date(res['local_repo_path'], since_date=get_since_date())
    print(f"Initial commits found from git (since {get_since_date()}): {len(total_commits_initial)}")
    
    total_commits_count = len(total_commits_initial)
    print(f"Final commits after timestamp verification: {total_commits_count}")
    
    json_data = create_json_analysis(df, res['local_repo_path'], f'{output_dir}/{datetime.now().strftime("%Y-%m-%d")}/developer_analysis', target_commit_hash=res['json_data_from_jsonl']['v2_hash'], project_name=res['json_data_from_jsonl']['project'], developer_name=first_name, original_commit_count=total_commits_count, renamed_attributes=renamed_attributes)

    if len(res['new_commits']) != 0:
        update_analyzed_repo_info(df, filepath_to_analyzed_repo, res, actual_batch_count, len(res['new_commits']), already_analyzed=True)


def analyze_repo_from_beginning(res, filepath_to_analyzed_repo, renamed_attributes):
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
                max_batch_size=500, 
                start_batch_index=0
            )
    
    # Process rename analysis results
    df, original_commit_count = process_rename_analysis_results(batch_output_dir, output_dir, res)

    # Create plots
    weekly_csv_data, summary_data, heatmap_data = create_plots(df, output_dir, res['processed_project_info']['project'])
        
    # Create JSON analysis (with optional commit hash analysis)
    print("\nCreating comprehensive JSON analysis...")
    developer_name = res['developer_name']
    developer_email = res['developer_email']
    # Handle names with various separators (spaces, dots, underscores, hyphens)
    # Split by common separators and take the first part
    first_name = re.split(r'[ .\-_]+', developer_name.strip())[0]
    json_data = create_json_analysis(df, res['local_repo_path'], f'{output_dir}/{datetime.now().strftime("%Y-%m-%d")}/developer_analysis', target_commit_hash=res['json_data_from_jsonl']['v2_hash'], project_name=res['json_data_from_jsonl']['project'], developer_name=first_name, original_commit_count=total_commits_count, renamed_attributes=renamed_attributes)

    print(f"Actual batch count: {actual_batch_count}")
    print(f"Successful batches: {successful_batches}")
    print(f"Failed batches: {failed_batches}")

    # Update analyzed repo information
    update_analyzed_repo_info(df, filepath_to_analyzed_repo, res, actual_batch_count, total_commits_count, developer_email=developer_email)



def update_analyzed_repo_info(df, filepath_to_analyzed_repo, res, actual_batch_count, total_commits_count,  already_analyzed = False, developer_email=None):
    """Update the analyzed repo information in the JSON file"""
    # Read existing data first
    with open(filepath_to_analyzed_repo, 'r', encoding='utf-8') as file:
        data = json.load(file)
    
    # Update the entry
    for entry in data:
        if entry['project'] == res['processed_project_info']['project']:
            entry['batch_anlayzed'] = actual_batch_count if not already_analyzed else entry['batch_anlayzed'] + actual_batch_count
            entry['total_commits_found'] = total_commits_count if not already_analyzed else entry['total_commits_found'] + total_commits_count
            entry['last_analyzed_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if already_analyzed else entry['last_analyzed_time']
            # for developer in entry['mail_sent_to_developer']:
            #     if developer['developer_email'] == developer_email:
            #         developer['mail_sent_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            #         developer['total_renames_count'] = df.loc[df['commit'] == res['json_data_from_jsonl']['v2_hash'], 'count'].iloc[0] if not df.empty else 0
            #         break
    
    # Write updated data back
    with open(filepath_to_analyzed_repo, 'w', encoding='utf-8') as file:
        json.dump(data, file, indent=4, ensure_ascii=False)



def process_rename_analysis_results(batch_output_dir, output_dir, res):
    """Process rename analysis results and save to various formats"""
    results, total_files_analyzed, count = collect_rename_refactorings(batch_output_dir)
    save_results_to_json(results, f'{output_dir}/rename_analysis_results.json')
    convert_to_csv(f'{output_dir}/rename_analysis_results.json', f'{output_dir}/rename_analysis_results.csv')

    results, total_files_analyzed, count = collect_rename_refactorings_count(batch_output_dir)

    print(f"Total Rename commit count: {count}")
    
    print("\nSaving results to CSV file...")
    df, original_commit_count = process_and_save_commit_metadata(results, f'{output_dir}/rename_analysis_results_count.csv', res['local_repo_path'])

    # Create comprehensive developer analysis
    print("\nCreating comprehensive developer analysis for all commits...")
    comprehensive_stats, df_with_authors = create_comprehensive_developer_analysis(df, res['local_repo_path'], output_dir)
    
    return df, original_commit_count

def create_plots(df, output_dir, project_name):
    """Create weekly plot and heatmap visualizations"""
    # Create weekly plot
    print("\nCreating weekly time series plot...")
    weekly_csv_data, summary_data = create_weekly_plot(df, f'{output_dir}/plots', project_name, since_date=get_since_date())
        
    # Create heatmap
    print("\nCreating heatmap of rename activity...")
    heatmap_data = create_heatmap(df, f'{output_dir}/plots')
    
    return weekly_csv_data, summary_data, heatmap_data