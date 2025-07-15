import json
import os
import sys
import argparse
from dotenv import load_dotenv
from git_utils import get_repo_url, git_pull
from datetime import datetime
from collect_commits import get_commits_since_date, save_commits_to_file, process_commits_with_refactoringminer
from process_batch import collect_rename_refactorings, save_results_to_json, collect_rename_refactorings_count, process_and_save_commit_metadata
from plot_utils import create_weekly_plot, create_heatmap, load_and_enrich_data, create_comprehensive_developer_analysis
from raw_json_to_csv import convert_to_csv
import pandas as pd

load_dotenv()

# Default date filter - set to 2024-01-01 by default to exclude older data
DEFAULT_SINCE_DATE = "2024-01-01"

def get_since_date():
    """
    Get the date filter to use. Can be overridden by environment variable or config.
    Returns the date string in YYYY-MM-DD format.
    """
    # Allow override via environment variable
    env_date = os.environ.get('REFACTORING_SINCE_DATE')
    if env_date:
        print(f"Using date filter from environment variable: {env_date}")
        return env_date
    return DEFAULT_SINCE_DATE

def load_already_analyzed_repos(analyzed_repo_file='analyzed_repo.json'):
    """Load the list of already analyzed repositories from the JSON file"""
    analyzed_repos = set()
    
    if os.path.exists(analyzed_repo_file):
        try:
            with open(analyzed_repo_file, 'r', encoding='utf-8') as file:
                data = json.load(file)
                for entry in data:
                    if 'project' in entry:
                        analyzed_repos.add(entry['project'])
            print(f"Found {len(analyzed_repos)} already analyzed repositories in {analyzed_repo_file}")
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not read {analyzed_repo_file}: {e}")
    else:
        print(f"No existing {analyzed_repo_file} found - will process all repositories")
    
    return analyzed_repos

def check_batch_results_exist(batch_output_dir):
    """Check if batch results already exist in the output directory"""
    if not os.path.exists(batch_output_dir):
        return False
    
    # Check if there are any batch directories with JSON files
    batch_dirs = [d for d in os.listdir(batch_output_dir) 
                  if os.path.isdir(os.path.join(batch_output_dir, d)) and d.startswith('batch_')]
    
    if not batch_dirs:
        return False
    
    # Check if at least one batch directory contains JSON files
    for batch_dir in batch_dirs:
        batch_path = os.path.join(batch_output_dir, batch_dir)
        json_files = [f for f in os.listdir(batch_path) if f.endswith('.json')]
        if json_files:
            return True
    
    return False

def extract_unique_repos_from_jsonl(jsonl_files, force_reanalysis=False):
    """Extract unique repository information from JSONL files"""
    unique_repos = {}
    
    # Load already analyzed repositories (unless forcing reanalysis)
    analyzed_repos = set()
    if not force_reanalysis:
        analyzed_repos = load_already_analyzed_repos()
    else:
        print("Force reanalysis enabled - will process all repositories")
    
    for jsonl_file in jsonl_files:
        if not os.path.exists(jsonl_file):
            print(f"Warning: JSONL file '{jsonl_file}' not found. Skipping...")
            continue
            
        print(f"Processing JSONL file: {jsonl_file}")
        
        with open(jsonl_file, 'r', encoding='utf-8') as file:
            for line in file:
                if line.strip():  # skip empty lines
                    try:
                        loaded_json = json.loads(line)
                        project_name = loaded_json.get('project')
                        
                        if project_name and project_name not in unique_repos:
                            # Skip if already analyzed (unless forcing reanalysis)
                            if not force_reanalysis and project_name in analyzed_repos:
                                print(f"Skipping {project_name} - already analyzed")
                                continue
                            
                            # Get repository path
                            projects_base_path = os.getenv('PROJECTS_BASE_PATH')
                            if projects_base_path:
                                local_repo_path = os.path.join(projects_base_path, project_name)
                            else:
                                local_repo_path = loaded_json.get("repo_path", "")
                            
                            unique_repos[project_name] = {
                                'project': project_name,
                                'local_repo_path': local_repo_path,
                                'sample_data': loaded_json  # Keep one sample for reference
                            }
                    except json.JSONDecodeError as e:
                        print(f"Error parsing JSON line in {jsonl_file}: {e}")
                        continue
    
    return unique_repos

def analyze_repository_by_cutoff(repo_info, cutoff_date=None, force_reanalysis=False):
    """Analyze a repository by cutoff date without individual developer analysis"""
    project_name = repo_info['project']
    local_repo_path = repo_info['local_repo_path']
    
    print(f"\n{'='*60}")
    print(f"Analyzing repository: {project_name}")
    print(f"Local path: {local_repo_path}")
    print(f"{'='*60}")
    
    # Check if repository exists locally
    if not os.path.exists(local_repo_path):
        print(f"Error: Repository not found locally: {local_repo_path}")
        return False
    
    # Get remote URL to verify it's a valid git repo
    remote_repo_url = get_repo_url(local_repo_path)
    if remote_repo_url is None:
        print(f"Error: Not a valid git repository or no remote URL found: {local_repo_path}")
        return False
    
    try:
        # Pull latest changes
        print("Pulling latest changes...")
        git_pull(local_repo_path)
        
        # Get the date filter to use
        since_date = cutoff_date or get_since_date()
        print(f"Analyzing commits since: {since_date}")
        
        # Get commits since the cutoff date
        commits = get_commits_since_date(local_repo_path, since_date=since_date)
        total_commits_count = len(commits)
        print(f"Found {total_commits_count} commits since {since_date}")
        
        if total_commits_count == 0:
            print(f"No commits found since {since_date}. Skipping analysis.")
            return True
        
        # Create output directory
        output_dir = f'refactoring_results_{project_name}'
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(f'{output_dir}/batch_results', exist_ok=True)
        os.makedirs(f'{output_dir}/plots', exist_ok=True)
        
        # Save commits to file
        save_commits_to_file(commits, f'{output_dir}/commits.txt')
        
        # Check if batch results already exist
        batch_output_dir = f'{output_dir}/batch_results'
        batch_files_exist = check_batch_results_exist(batch_output_dir) and not force_reanalysis
        
        if batch_files_exist:
            print("Batch results already exist, skipping RefactoringMiner processing...")
            print("Use --force to regenerate batch results if needed")
            actual_batch_count = len([d for d in os.listdir(batch_output_dir) if os.path.isdir(os.path.join(batch_output_dir, d)) and d.startswith('batch_')])
            successful_batches = actual_batch_count
            failed_batches = 0
        else:
            # Process commits with RefactoringMiner
            if force_reanalysis and check_batch_results_exist(batch_output_dir):
                print("Force reanalysis enabled - regenerating batch results...")
            else:
                print("Processing commits with RefactoringMiner...")
            
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
        df = process_rename_analysis_results(batch_output_dir, output_dir, local_repo_path)
        
        # Create plots
        print("Creating visualizations...")
        create_plots(df, output_dir, project_name, since_date)
        
        # Create summary report
        create_summary_report(df, output_dir, project_name, total_commits_count, since_date)
        
        print(f"✓ Successfully analyzed repository: {project_name}")
        print(f"Results saved to: {output_dir}")
        print(f"Main analysis file: {output_dir}/comprehensive_analysis_repository.json")
        
        return True
        
    except Exception as e:
        print(f"Error analyzing repository {project_name}: {str(e)}")
        return False

def process_rename_analysis_results(batch_output_dir, output_dir, local_repo_path):
    """Process rename analysis results and save to various formats"""
    # Collect rename refactorings
    results, total_files_analyzed, count = collect_rename_refactorings(batch_output_dir)
    save_results_to_json(results, f'{output_dir}/rename_analysis_results.json')
    convert_to_csv(f'{output_dir}/rename_analysis_results.json', f'{output_dir}/rename_analysis_results.csv')

    # Collect rename refactorings with count
    results, total_files_analyzed, count = collect_rename_refactorings_count(batch_output_dir)
    print(f"Total Rename commit count: {count}")
    
    # Save results to CSV file
    print("Saving results to CSV file...")
    df, original_commit_count = process_and_save_commit_metadata(results, f'{output_dir}/rename_analysis_results_count.csv', local_repo_path)
    
    # Ensure timestamp column is properly named for consistency
    if 'timestamp' in df.columns:
        df['date'] = df['timestamp']  # Also create a 'date' column for backward compatibility

    # Create comprehensive developer analysis (without individual targeting)
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
            'co_rename_precentage': round((commits_with_more_than_1_rename / total_rename_commits) * 100, 2) if total_rename_commits > 0 else 0
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

def main():
    parser = argparse.ArgumentParser(description="Analyze repositories from JSONL files by cutoff date")
    parser.add_argument("jsonl_files", nargs='+', help="Path(s) to JSONL files to process")
    parser.add_argument("--cutoff-date", help="Cutoff date for analysis (YYYY-MM-DD). If not provided, uses default or environment variable.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be processed without actually running analysis")
    parser.add_argument("--force", action="store_true", help="Force reanalysis of already analyzed repositories")
    
    args = parser.parse_args()
    
    # Extract unique repositories from JSONL files
    print("Extracting unique repositories from JSONL files...")
    unique_repos = extract_unique_repos_from_jsonl(args.jsonl_files, force_reanalysis=args.force)
    
    # Load already analyzed repos to show summary (only if not forcing)
    if not args.force:
        analyzed_repos = load_already_analyzed_repos()
    else:
        analyzed_repos = set()
    
    if not unique_repos:
        if args.force:
            print("No repositories found in the provided JSONL files.")
        else:
            print("No new repositories to analyze (all repositories have already been analyzed or no repositories found).")
        sys.exit(1)
    
    print(f"\nRepositories to analyze: {len(unique_repos)}")
    for project_name in sorted(unique_repos.keys()):
        print(f"  - {project_name}")
    
    if not args.force and len(analyzed_repos) > 0:
        print(f"\nAlready analyzed repositories (skipped): {len(analyzed_repos)}")
    
    if args.dry_run:
        print("\nDry run mode - no analysis will be performed.")
        sys.exit(0)
    
    # Analyze each repository
    print(f"\nStarting analysis of {len(unique_repos)} repositories...")
    successful_analyses = 0
    failed_analyses = 0
    
    for project_name, repo_info in unique_repos.items():
        try:
            if analyze_repository_by_cutoff(repo_info, args.cutoff_date, args.force):
                successful_analyses += 1
            else:
                failed_analyses += 1
        except Exception as e:
            print(f"Unexpected error analyzing {project_name}: {str(e)}")
            failed_analyses += 1
    
    # Final summary
    print(f"\n{'='*60}")
    print(f"ANALYSIS COMPLETE")
    print(f"{'='*60}")
    print(f"Total repositories: {len(unique_repos)}")
    print(f"Successfully analyzed: {successful_analyses}")
    print(f"Failed analyses: {failed_analyses}")
    
    if failed_analyses > 0:
        sys.exit(1)
    else:
        print("All repositories analyzed successfully!")

if __name__ == "__main__":
    main() 