import os
from git_utils import git_pull, get_commit_author_info
from collect_commits import get_commits_since_date, save_commits_to_file, process_commits_with_refactoringminer, \
    get_commit_date
from process_batch import collect_rename_refactorings, save_results_to_json, collect_rename_refactorings_count, \
    process_and_save_commit_metadata
from raw_json_to_csv import convert_to_csv
from plot_utils import create_comprehensive_developer_analysis, create_weekly_plot, create_heatmap, create_json_analysis
from datetime import datetime, timedelta
import json
import re
import pandas as pd

RENAME_TYPES = {
    'Rename Class',
    'Rename Method',
    'Rename Variable',
    'Rename Parameter',
    'Rename Attribute',
    'Rename Package'
}


def load_as_df(output_dir):

    df = pd.read_csv(f"{output_dir}/rename_analysis_results_count.csv")
    return df, len(df)


def get_rename_elements(json_data):
    return [refactoring_change for refactoring_change in json_data['refactoring_changes'] if
            refactoring_change['type'] in RENAME_TYPES]


def get_renamed_attributes(json_data):
    codeElements = set()
    for refactoring_change in json_data['refactoring_changes']:
        codeElementType = refactoring_change['leftSideLocations'][0]['codeElementType']
        old_name = ''
        new_name = ''

        if refactoring_change['type'] == 'Rename Class':
            match = re.search(r"Rename Class .*\.([A-Za-z0-9_]+) renamed to .*\.([A-Za-z0-9_]+)",
                              refactoring_change['description'])
            if match:
                old_name = match.group(1)
                new_name = match.group(2)

        elif refactoring_change['type'] == 'Rename Method':
            match = re.search(r"Rename Method .*? ([A-Za-z0-9_]+)\(.*?\)\s*:\s*.*? renamed to .*? ([A-Za-z0-9_]+)\(",
                              refactoring_change['description'])
            if match:
                old_name = match.group(1)
                new_name = match.group(2)

        elif refactoring_change['type'] == 'Rename Variable':
            match = re.search(r"Rename Variable ([A-Za-z0-9_]+) ?: .*? to ([A-Za-z0-9_]+) ?: .*?",
                              refactoring_change['description'])
            if match:
                old_name = match.group(1)
                new_name = match.group(2)
        elif refactoring_change['type'] == 'Rename Attribute':
            match = re.search(r"Rename Attribute ([A-Za-z0-9_]+) ?: .*? to ([A-Za-z0-9_]+) ?: .*? in class",
                              refactoring_change['description'])
            if match:
                old_name = match.group(1)
                new_name = match.group(2)
        elif refactoring_change['type'] == 'Rename Parameter':
            match = re.search(r"Rename Parameter ([A-Za-z0-9_]+) ?: .*? to ([A-Za-z0-9_]+) ?: .*? in method",
                              refactoring_change['description'])
            if match:
                old_name = match.group(1)
                new_name = match.group(2)

        if old_name and new_name:
            codeElements.add((codeElementType.lower().replace('_', ' ').title(), f'{old_name} -> {new_name}'))
    return codeElements


def exclude_commits(local_repo_path, data):
    commit_date = get_commit_date(local_repo_path, data['v2_hash'])
    if commit_date:
        # Convert both dates to date-only objects for comparison
        commit_date_only = commit_date.date()
        two_days_ago = (datetime.now() - timedelta(days=7)).date()  # Changed from one day to two days
        print(f"commit date: {commit_date_only} and checking against: {two_days_ago}")
        if commit_date_only >= two_days_ago:  # Changed to > two_days_ago
            print(
                f"Processing: Commit {data['v2_hash']} is within last day (committed on {commit_date_only})")
            return False
        else:
            print(
                f"Skipped: Commit {data['v2_hash']} is older than two (committed on {commit_date_only})")
            return True
    else:
        print(f"Skipped: Could not get commit date for {data['v2_hash']}")
        return True


def developer_already_analyzed(local_repo_path, data, analyzed_repo_info, developer_name, developer_email):
    if developer_name is None or developer_email is None:
        print(f"Skipped: Could not get developer info")
        return False
    if analyzed_repo_info is None or 'mail_sent_to_developer' not in analyzed_repo_info:
        return False
    for developer in analyzed_repo_info['mail_sent_to_developer']:
        if developer_email.strip() == developer['developer_email'].strip():
            return True

    return False


def get_total_commits_count(file_path):
    with open(file_path, 'r') as f:
        line_count = sum(1 for line in f if line.strip())
    return line_count


def process_rename_analysis_results(batch_output_dir, output_dir, local_repo_path):
    results, total_files_analyzed, count = collect_rename_refactorings(batch_output_dir)
    save_results_to_json(results, f'{output_dir}/rename_analysis_results.json')
    convert_to_csv(f'{output_dir}/rename_analysis_results.json', f'{output_dir}/rename_analysis_results.csv')

    # Collect rename refactorings with count
    results, total_files_analyzed, count = collect_rename_refactorings_count(batch_output_dir)
    print(f"Total Rename commit count: {count}")

    # Save results to CSV file
    print("Saving results to CSV file...")
    df, original_commit_count = process_and_save_commit_metadata(results,
                                                                 f'{output_dir}/rename_analysis_results_count.csv',
                                                                 local_repo_path)
    if 'timestamp' in df.columns:
        df['date'] = df['timestamp']

    print("Creating comprehensive developer analysis...")
    comprehensive_stats, df_with_authors = create_comprehensive_developer_analysis(df, local_repo_path, output_dir)

    return df


def create_plots(df, output_dir, project_name, since_date):
    """Create weekly plot and heatmap visualizations"""
    # Create weekly plot
    print("Creating weekly time series plot...")
    weekly_csv_data, summary_data = create_weekly_plot(df, f'{output_dir}/plots', project_name, since_date=since_date)

    # Create heatmap
    print("Creating heatmap of rename activity...")
    heatmap_data = create_heatmap(df, f'{output_dir}/plots')

    return weekly_csv_data, summary_data, heatmap_data


def create_summary_report(df, output_dir, project_name, total_commits_count, since_date):
    """Create a summary report for the repository analysis"""

    # Calculate statistics
    total_rename_commits = len(df) if not df.empty else 0
    total_renames = df['count'].sum() if not df.empty else 0

    if not df.empty:
        rename_counts = df['count']
        # Calculate co-rename statistics (commits with more than 1 rename)
        commits_with_more_than_1_rename = int((rename_counts > 1).sum())

        rename_stats = {
            'mean': float(rename_counts.mean()),
            'median': float(rename_counts.median()),
            'mode': int(rename_counts.mode().iloc[0]) if not rename_counts.mode().empty else 0,
            'max': int(rename_counts.max()),
            'min': int(rename_counts.min()),
            'std': float(rename_counts.std())
        }
    else:
        commits_with_more_than_1_rename = 0
        rename_stats = {
            'mean': 0, 'median': 0, 'mode': 0, 'max': 0, 'min': 0, 'std': 0
        }

    # Create summary data in the same format as original comprehensive analysis
    summary_data = {
        'dataset_statistics': {
            'total_analyzed_commit': total_commits_count,
            'total_rename_commit': total_rename_commits,
            'total_renames': int(total_renames),
            'total_co_rename_commit': commits_with_more_than_1_rename,
            'co_rename_precentage': round((commits_with_more_than_1_rename / total_rename_commits) * 100,
                                          2) if total_rename_commits > 0 else 0
        },
        'rename_statistics': {
            'mean': round(rename_stats['mean'], 2),
            'median': rename_stats['median'],
            'mode': rename_stats['mode'],
            'max': rename_stats['max']
        },
        'analysis_metadata': {
            'project_name': project_name,
            'analysis_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'cutoff_date': since_date
        }
    }

    # Add date range if data exists
    if not df.empty and 'timestamp' in df.columns:
        summary_data['analysis_metadata']['dataset_date_range'] = {
            'earliest_commit': pd.to_datetime(df['timestamp'].min()).strftime('%Y-%m-%d %H:%M:%S'),
            'latest_commit': pd.to_datetime(df['timestamp'].max()).strftime('%Y-%m-%d %H:%M:%S')
        }
    elif not df.empty and 'date' in df.columns:
        summary_data['analysis_metadata']['dataset_date_range'] = {
            'earliest_commit': str(df['date'].min()),
            'latest_commit': str(df['date'].max())
        }

    # Save summary report
    summary_file = f'{output_dir}/comprehensive_analysis_repository.json'
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary_data, f, indent=2, ensure_ascii=False)

    print(f"Comprehensive analysis saved to: {summary_file}")

    # Print summary to console
    print(f"\nRepository Analysis Summary:")
    print(f"  Total commits analyzed: {total_commits_count}")
    print(f"  Total rename commits: {total_rename_commits}")
    print(f"  Total renames: {total_renames}")
    print(f"  Co-rename commits (>1 rename): {summary_data['dataset_statistics']['total_co_rename_commit']}")
    print(f"  Co-rename percentage: {summary_data['dataset_statistics']['co_rename_precentage']:.2f}%")
    print(f"  Mean renames per commit: {summary_data['rename_statistics']['mean']}")
    print(f"  Median renames per commit: {summary_data['rename_statistics']['median']}")
    print(f"  Mode renames per commit: {summary_data['rename_statistics']['mode']}")
    print(f"  Max renames per commit: {summary_data['rename_statistics']['max']}")


def analyze_repo_from_checkpoint(analyzed_repo_info, json_data_of_a_repo, local_repo_path, since_date, output_dir_base,
                                 skip_old_commits=True):
    print(f"Analyzing already existed repository at {local_repo_path}")
    git_pull(local_repo_path)
    print(f"Pulled repo: {local_repo_path} to get the latest commits")
    batch_output_dir = f'{output_dir_base}/batch_results'

    print("Start checking entry by entry to create meta data for emails")

    saved_developer_info = []
    analyzed_datapoints = []
    total_commits_count = len(get_commits_since_date(local_repo_path, since_date=since_date))
    df, df_length = load_as_df(output_dir_base)
    project_name = json_data_of_a_repo[0]['project']

    for data in json_data_of_a_repo:
        if skip_old_commits and exclude_commits(local_repo_path, data):
            continue
        developer_name, developer_email = get_commit_author_info(data["v2_hash"], local_repo_path)
        if developer_already_analyzed(local_repo_path, data, analyzed_repo_info, developer_name, developer_email):
            continue

        if len(get_rename_elements(data)) <= 3:
            print(
                f'Skipping {data["v2_hash"]} with {len(get_rename_elements(data))} rename elements as it is less than 4 renames.')
            continue

        json_data = create_json_analysis(df, local_repo_path,
                                         f'{output_dir_base}/{datetime.now().strftime("%Y-%m-%d")}/developer_analysis',
                                         target_commit_hash=data['v2_hash'],
                                         project_name=project_name,
                                         developer_name=developer_name,
                                         original_commit_count=total_commits_count,
                                         renamed_attributes=get_renamed_attributes(data))

        if json_data is not None:
            print(f"Created analysis data for developer: {developer_name}")
            saved_developer_info.append(json_data)
        else:
            print(f"Failed to create analysis data for developer: {developer_name}")
    save_analyzed_datapoint(analyzed_datapoints, project_name)
    update_analyzed_repo_info(project_name=project_name,
                              actual_batch_count= analyzed_repo_info[
                                  'batch_analyzed'],
                              total_commits_count=total_commits_count, saved_developer_info=saved_developer_info,
                              already_analyzed=True)


def analyze_repo_from_beginning(analyzed_repo_info, json_data_of_a_repo, local_repo_path, since_date, output_dir_base,
                                skip_old_commits=True):
    git_pull(local_repo_path)
    print(f"Pulled repo: {local_repo_path} to get the latest commits")
    os.makedirs(output_dir_base, exist_ok=True)

    print(f"Analyzing repo from {since_date} onwards...")
    commits = get_commits_since_date(local_repo_path, since_date=since_date)
    print(f"Initial commits found from git (since {since_date}): {len(commits)}")
    total_commits_count = len(commits)
    print(f"Final commits after timestamp verification: {total_commits_count}")

    save_commits_to_file(commits, f'{output_dir_base}/commits.txt')

    batch_output_dir = f'{output_dir_base}/batch_results'

    actual_batch_count, successful_batches, failed_batches = process_commits_with_refactoringminer(
        repo_path=str(local_repo_path),
        commits=commits,
        output_dir=batch_output_dir,
        max_batch_size=500,
        start_batch_index=0
    )

    print(f"Processed {actual_batch_count} batches")
    print(f"Successful batches: {successful_batches}")
    print(f"Failed batches: {failed_batches}")

    # Process rename analysis results
    print("Processing rename analysis results...")
    df = process_rename_analysis_results(batch_output_dir, output_dir_base, local_repo_path)

    project_name = json_data_of_a_repo[0]['project']
    # Create plots
    print("Creating visualizations...")
    create_plots(df, output_dir_base, project_name, since_date)

    # Create summary report
    create_summary_report(df, output_dir_base, project_name, total_commits_count, since_date)

    print(f"✓ Successfully analyzed repository: {project_name}")
    print(f"Results saved to: {output_dir_base}")
    print(f"Main analysis file: {output_dir_base}/comprehensive_analysis_repository.json")
    analyzed_repo_info = update_analyzed_repo_info(project_name=project_name, actual_batch_count=actual_batch_count, total_commits_count=total_commits_count, saved_developer_info= [])
    print("Start checking entry by entry to create meta data for emails")

    saved_developer_info = []
    analyzed_datapoints = []
    for data in json_data_of_a_repo:
        if skip_old_commits and exclude_commits(local_repo_path, data):
            continue
        developer_name, developer_email = get_commit_author_info(data["v2_hash"], local_repo_path)
        if developer_already_analyzed(local_repo_path, data, analyzed_repo_info, developer_name, developer_email):
            continue

        if len(get_rename_elements(data)) <= 3:
            print(
                f'Skipping {data["v2_hash"]} with {len(get_rename_elements(data))} rename elements as it is less than 4 renames.')
            continue

        json_data = create_json_analysis(df, local_repo_path,
                                         f'{output_dir_base}/{datetime.now().strftime("%Y-%m-%d")}/developer_analysis',
                                         target_commit_hash=data['v2_hash'],
                                         project_name=project_name,
                                         developer_name=developer_name,
                                         original_commit_count=total_commits_count,
                                         renamed_attributes=get_renamed_attributes(data))

        if json_data is not None:
            print(f"Created analysis data for developer: {developer_name}")
            saved_developer_info.append(json_data)
            analyzed_datapoints.append(json_data)
        else:
            print(f"Failed to create analysis data for developer: {developer_name}")
    save_analyzed_datapoint(analyzed_datapoints, project_name)
    update_analyzed_repo_info(project_name=project_name, actual_batch_count=actual_batch_count,
                              total_commits_count=total_commits_count, saved_developer_info=saved_developer_info)


def update_analyzed_repo_info(project_name, actual_batch_count, total_commits_count, saved_developer_info,
                              already_analyzed=False, filepath_to_analyzed_repo="analyzed_repo.json"):
    """Update the analyzed repo information in the JSON file"""
    # Read existing data first
    with open(filepath_to_analyzed_repo, 'r', encoding='utf-8') as file:
        data = json.load(file)

    isNewProject = True
    # Update the entry
    for entry in data:
        if entry['project'] == project_name:
            isNewProject = False
            # entry['batch_analyzed'] = actual_batch_count if not already_analyzed else entry[
            #                                                                               'batch_analyzed'] + actual_batch_count
            # entry['total_commits_found'] = total_commits_count if not already_analyzed else entry[
            #                                                                                     'total_commits_found'] + total_commits_count
            # entry['last_analyzed_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if already_analyzed else entry[
            #     'last_analyzed_time']

            email_sent_to_developer = entry.get('mail_sent_to_developer', [])

            for developer_info in saved_developer_info:
                if developer_info is None:
                    continue
                if 'target_commit_analysis' not in developer_info or developer_info['target_commit_analysis'] is None:
                    continue
                temp = {
                    "developer_name": developer_info['target_commit_analysis']['author_info']['name'] ,
                    "developer_email": developer_info['target_commit_analysis']['author_info']['email'],
                    "mail_sent_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "v2_hash": developer_info['target_commit_analysis']['commit_hash'],
                    "total_renames_count": developer_info['target_commit_analysis']['target_commit_info'][
                        'total_rename_in_author_commit']
                }
                email_sent_to_developer.append(temp)

            entry['mail_sent_to_developer'] = email_sent_to_developer

    if isNewProject:
        email_sent_to_developer = []
        for developer_info in saved_developer_info:
            if developer_info is None:
                continue
            if 'target_commit_analysis' not in developer_info or developer_info['target_commit_analysis'] is None:
                continue
            temp = {
                "developer_name": developer_info['target_commit_analysis']['author_info']['name'],
                "developer_email": developer_info['target_commit_analysis']['author_info']['email'],
                "mail_sent_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "v2_hash": developer_info['target_commit_analysis']['commit_hash'],
                "total_renames_count": developer_info['target_commit_analysis']['target_commit_info'][
                    'total_rename_in_author_commit']
            }
            email_sent_to_developer.append(temp)
        new_project_info = {
            "project": project_name,
            "total_commits_found": total_commits_count,
            "batch_analyzed": actual_batch_count,
            "last_analyzed_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "repo_url": "",
            "mail_sent_to_developer": email_sent_to_developer,
        }
        data.append(new_project_info)

    # Write updated data back
    with open(filepath_to_analyzed_repo, 'w', encoding='utf-8') as file:
        json.dump(data, file, indent=4, ensure_ascii=False)

    return data

def save_analyzed_datapoint(analyzed_datapoints, project_name):
    """Save analyzed datapoints to analysis_result directory, appending if file exists"""
    if not analyzed_datapoints:
        print("No analyzed datapoints to save")
        return

    # Create analysis_result/saved_datapoints directory if it doesn't exist
    analysis_result_dir = "analysis_result/saved_datapoints"
    os.makedirs(analysis_result_dir, exist_ok=True)

    filename = f"{analysis_result_dir}/{project_name}_analyzed_datapoints.json"

    existing_data = []

    # Load existing data if file exists
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
            print(f"Loaded {len(existing_data)} existing datapoints from {filename}")
        except (json.JSONDecodeError, FileNotFoundError):
            print(f"Could not load existing data from {filename}, starting fresh")
            existing_data = []

    # Append new datapoints to existing data
    existing_data.extend(analyzed_datapoints)

    # Save all data back to file
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(existing_data, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(analyzed_datapoints)} new datapoints to {filename}")