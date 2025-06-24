import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import subprocess
from pathlib import Path
import argparse
import warnings
import numpy as np
import json
from scipy import stats
from datetime import datetime, date
from matplotlib.patches import Patch
from collect_commits import process_single_commit_with_refactoringminer
warnings.filterwarnings('ignore')

# Set style for plots
plt.style.use('default')


RENAME_TYPES = {
    'Rename Class',
    'Rename Method',
    'Rename Variable',
    'Rename Parameter',
    'Rename Attribute',
    'Rename Package'
}

def get_rename_instance_count(refactoring_changes):
    count = 0
    for refactoring_change in refactoring_changes:
        if refactoring_change['type'] in RENAME_TYPES:
            count += 1
    return count

def get_commit_timestamp(commit_sha, repo_path):
    """Get the timestamp of a commit"""
    try:
        original_dir = os.getcwd()
        os.chdir(repo_path)
        
        # Get commit timestamp in ISO format
        cmd = f"git show -s --format=%ci {commit_sha}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        os.chdir(original_dir)
        
        if result.returncode == 0:
            timestamp_str = result.stdout.strip()
            # Parse the timestamp
            timestamp = pd.to_datetime(timestamp_str)
            return timestamp
        else:
            print(f"Error getting timestamp for commit {commit_sha}: {result.stderr}")
            return None
    except Exception as e:
        print(f"Error processing commit {commit_sha}: {e}")
        return None

def get_commit_author_info(commit_sha, repo_path):
    """Get the author name and email of a commit"""
    try:
        original_dir = os.getcwd()
        os.chdir(repo_path)
        
        # Get commit author name and email
        cmd_name = f"git show -s --format=%an {commit_sha}"
        cmd_email = f"git show -s --format=%ae {commit_sha}"
        
        result_name = subprocess.run(cmd_name, shell=True, capture_output=True, text=True)
        result_email = subprocess.run(cmd_email, shell=True, capture_output=True, text=True)
        
        os.chdir(original_dir)
        
        if result_name.returncode == 0 and result_email.returncode == 0:
            author_name = result_name.stdout.strip()
            author_email = result_email.stdout.strip()
            return author_name, author_email
        else:
            print(f"Error getting author info for commit {commit_sha}")
            return None, None
    except Exception as e:
        print(f"Error processing commit {commit_sha}: {e}")
        return None, None

def get_commit_author(commit_sha, repo_path):
    """Get the author of a commit (backward compatibility)"""
    name, email = get_commit_author_info(commit_sha, repo_path)
    return name

def load_and_enrich_data(csv_file, repo_path):
    """Load CSV data and enrich with commit timestamps"""
    print(f"Loading data from {csv_file}...")
    df = pd.read_csv(csv_file)
    
    initial_count = len(df)
    print(f"Found {initial_count} commits in CSV file")
    
    # Remove duplicate commits, keeping the first occurrence
    df_deduplicated = df.drop_duplicates(subset=['commit'], keep='first')
    final_count = len(df_deduplicated)
    
    duplicates_removed = initial_count - final_count
    if duplicates_removed > 0:
        print(f"Removed {duplicates_removed} duplicate commits")
        print(f"Processing {final_count} unique commits")
    else:
        print("No duplicate commits found")
    
    print("Fetching commit timestamps from git repository...")
    
    # Get timestamps for all unique commits
    timestamps = []
    for i, commit_sha in enumerate(df_deduplicated['commit']):
        if i % 10 == 0:
            print(f"Processing commit {i+1}/{len(df_deduplicated)}: {commit_sha[:8]}")
        timestamp = get_commit_timestamp(commit_sha, repo_path)
        timestamps.append(timestamp)
    
    df_deduplicated['timestamp'] = timestamps
    
    # Ensure timestamp column is properly converted to datetime
    df_deduplicated['timestamp'] = pd.to_datetime(df_deduplicated['timestamp'], utc=True)
    
    # Convert to timezone-naive datetimes for easier processing
    df_deduplicated['timestamp'] = df_deduplicated['timestamp'].dt.tz_localize(None)
    
    # Remove rows where we couldn't get timestamps
    initial_with_timestamps = len(df_deduplicated)
    df_final = df_deduplicated.dropna(subset=['timestamp'])
    final_with_timestamps = len(df_final)
    
    if initial_with_timestamps != final_with_timestamps:
        print(f"Warning: Could not get timestamps for {initial_with_timestamps - final_with_timestamps} commits")
    
    # Sort by timestamp (oldest to newest)
    df_final = df_final.sort_values('timestamp').reset_index(drop=True)
    
    print(f"Successfully processed {len(df_final)} commits with timestamps")
    return df_final, final_count

def create_weekly_plot(df, output_dir, project_name=None, since_date="2024-01-01"):
    """Create weekly time series plot similar to the example image"""
    
    # Convert output_dir to Path object if it's a string
    if isinstance(output_dir, str):
        output_dir = Path(output_dir)
    
    # Create the output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Filter data based on since_date
    since_date = pd.to_datetime(since_date)
    df = df[df['timestamp'] >= since_date].copy()
    
    if len(df) == 0:
        print(f"Warning: No data found after {since_date}")
        return None, None
    
    # Group by week and sum the counts
    df['week'] = df['timestamp'].dt.to_period('W-MON')  # Week starting on Monday
    weekly_stats = df.groupby('week').agg({
        'count': 'sum',
        'commit': 'count'  # Count of commits per week
    }).reset_index()
    
    # Rename columns for clarity
    weekly_stats.columns = ['week', 'total_renames', 'commit_count']
    
    # Convert week periods to datetime for plotting
    weekly_stats['week_date'] = weekly_stats['week'].dt.start_time
    
    # Create simplified CSV data - one row per commit with weekly grouping info
    csv_data = []
    for _, row in df.iterrows():
        week_start = pd.to_datetime(row['timestamp']).to_period('W-MON').start_time
        week_end = pd.to_datetime(row['timestamp']).to_period('W-MON').end_time
        
        csv_data.append({
            'commit_id': row['commit'],
            'commit_timestamp': pd.to_datetime(row['timestamp']).strftime('%Y-%m-%d %H:%M:%S'),
            'renames_count': row['count'],
            'week_group': str(row['week']),
            'week_start': week_start.strftime('%Y-%m-%d'),
            'week_end': week_end.strftime('%Y-%m-%d')
        })
    
    # Save simplified CSV data
    csv_df = pd.DataFrame(csv_data)
    csv_file = output_dir / 'weekly_grouped_data.csv'
    csv_df.to_csv(csv_file, index=False)
    print(f"Weekly grouped data saved to: {csv_file}")
    
    # Also create a summary CSV with just weekly totals
    summary_data = []
    for _, row in weekly_stats.iterrows():
        summary_data.append({
            'week_group': str(row['week']),
            'week_start': row['week_date'].strftime('%Y-%m-%d'),
            'total_renames': row['total_renames'],
            'commit_count': row['commit_count']
        })
    
    summary_df = pd.DataFrame(summary_data)
    summary_file = output_dir / 'weekly_summary.csv'
    summary_df.to_csv(summary_file, index=False)
    print(f"Weekly summary saved to: {summary_file}")
    
    # Create the plot
    plt.figure(figsize=(14, 8))
    
    # Plot line with markers (similar to example image)
    plt.plot(weekly_stats['week_date'], weekly_stats['total_renames'], 
             marker='o', linewidth=2, markersize=6, color='#FF8C00')  # Orange color similar to example
    
    # Customize the plot - removed title
    plt.xlabel('Week', fontsize=24)
    plt.ylabel('Total Renames', fontsize=24)
    
    # Add project name label in top right corner inside a box with bigger font
    project_label = f"{project_name if project_name else 'Unknown Project'}: Rename Activity on a Weekly basis"
    plt.text(0.98, 0.95, project_label, transform=plt.gca().transAxes, 
             bbox=dict(boxstyle="round,pad=0.5", facecolor="white", alpha=0.9, edgecolor='black'),
             fontsize=24, verticalalignment='top', horizontalalignment='right',
             fontweight='bold')
    
    # Add grid
    plt.grid(True, alpha=0.3)
    
    # Format x-axis with bigger font
    plt.xticks(rotation=45, fontsize=24)
    plt.yticks(fontsize=24)
    
    # Adjust layout to prevent label cutoff
    plt.tight_layout()
    
    # Save the plot
    plt.savefig(output_dir / 'weekly_rename_activity.png', dpi=300, bbox_inches='tight')
    print(f"Weekly plot saved to: {output_dir / 'weekly_rename_activity.png'}")
    
    # Only show plot if running interactively (comment out to prevent terminal blocking)
    # plt.show()
    plt.close()  # Close the figure to free memory
    
    # Print some summary statistics
    print(f"\nWeekly Summary:")
    print(f"Total weeks analyzed: {len(weekly_stats)}")
    print(f"Average renames per week: {weekly_stats['total_renames'].mean():.1f}")
    print(f"Peak week: {weekly_stats.loc[weekly_stats['total_renames'].idxmax(), 'week']} ({weekly_stats['total_renames'].max()} renames)")
    print(f"Average commits per week: {weekly_stats['commit_count'].mean():.1f}")
    
    return csv_df, summary_df

def create_heatmap(df, output_dir):
    """Create a heatmap of rename activity by week of month and month"""
    # Convert output_dir to Path object if it's a string
    if isinstance(output_dir, str):
        output_dir = Path(output_dir)
    
    # Create a copy to avoid modifying original data
    heatmap_df = df.copy()
    
    # Extract month and week of month
    heatmap_df['month'] = heatmap_df['timestamp'].dt.month
    heatmap_df['year'] = heatmap_df['timestamp'].dt.year
    
    # Calculate week of month (1-5, where week 1 starts on the 1st)
    heatmap_df['day'] = heatmap_df['timestamp'].dt.day
    heatmap_df['week_of_month'] = ((heatmap_df['day'] - 1) // 7) + 1
    
    # Group by month and week of month, sum the rename counts
    heatmap_data = heatmap_df.groupby(['month', 'week_of_month'])['count'].sum().reset_index()
    
    # Create a pivot table for the heatmap
    heatmap_pivot = heatmap_data.pivot(index='month', columns='week_of_month', values='count')
    
    # Fill NaN values with 0
    heatmap_pivot = heatmap_pivot.fillna(0)
    
    # Ensure we have all months (1-12) and weeks (1-5)
    all_months = range(1, 13)
    all_weeks = range(1, 6)
    heatmap_pivot = heatmap_pivot.reindex(index=all_months, columns=all_weeks, fill_value=0)
    
    # Create the heatmap
    plt.figure(figsize=(10, 8))
    
    # Create heatmap with custom colormap similar to the example
    sns.heatmap(heatmap_pivot, 
                annot=True, 
                fmt='g', 
                cmap='YlOrRd',  # Yellow to Orange to Red colormap
                cbar_kws={'label': 'Number of Renames'},
                linewidths=0.5,
                linecolor='white',
                annot_kws={'size': 16})  # Increased annotation font size
    
    plt.title('Heatmap of Rename Activity by Week and Month', fontsize=24, fontweight='bold', pad=20)
    plt.xlabel('Week of Month', fontsize=20)
    plt.ylabel('Month', fontsize=20)
    
    # Customize y-axis labels to show month names with bigger font
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    plt.yticks(range(12), [f"{i+1} - {month_names[i]}" for i in range(12)], rotation=0, fontsize=18)
    plt.xticks(fontsize=18)
    
    plt.tight_layout()
    
    # Save the heatmap
    plt.savefig(output_dir / 'rename_activity_heatmap.png', dpi=300, bbox_inches='tight')
    print(f"Heatmap saved to: {output_dir / 'rename_activity_heatmap.png'}")
    
    plt.close()  # Close the figure to free memory
    
    # Print heatmap statistics
    print(f"\nHeatmap Summary:")
    print(f"Peak activity: {heatmap_pivot.max().max():.0f} renames")
    max_month, max_week = np.unravel_index(heatmap_pivot.values.argmax(), heatmap_pivot.shape)
    print(f"Peak period: Month {max_month + 1} ({month_names[max_month]}), Week {heatmap_pivot.columns[max_week]}")
    print(f"Total months with activity: {(heatmap_pivot.sum(axis=1) > 0).sum()}")
    
    return heatmap_pivot

def create_day_heatmap(df, output_dir):
    """Create a heatmap of rename activity by day of month and month"""
    # Convert output_dir to Path object if it's a string
    if isinstance(output_dir, str):
        output_dir = Path(output_dir)
    
    # Create a copy to avoid modifying original data
    heatmap_df = df.copy()
    
    # Extract month and day of month
    heatmap_df['month'] = heatmap_df['timestamp'].dt.month
    heatmap_df['day_of_month'] = heatmap_df['timestamp'].dt.day
    
    # Group by month and day of month, sum the rename counts
    heatmap_data = heatmap_df.groupby(['month', 'day_of_month'])['count'].sum().reset_index()
    
    # Create a pivot table for the heatmap
    heatmap_pivot = heatmap_data.pivot(index='month', columns='day_of_month', values='count')
    
    # Fill NaN values with 0
    heatmap_pivot = heatmap_pivot.fillna(0)
    
    # Ensure we have all months (1-12) and days (1-31)
    all_months = range(1, 13)
    all_days = range(1, 32)
    heatmap_pivot = heatmap_pivot.reindex(index=all_months, columns=all_days, fill_value=0)
    
    # Create the heatmap
    plt.figure(figsize=(16, 8))
    
    # Create heatmap with custom colormap similar to the example
    sns.heatmap(heatmap_pivot, 
                annot=True, 
                fmt='g', 
                cmap='YlOrRd',  # Yellow to Orange to Red colormap
                cbar_kws={'label': 'Number of Renames'},
                linewidths=0.5,
                linecolor='white',
                annot_kws={'size': 12})  # Increased annotation font size but smaller due to more cells
    
    plt.title('Heatmap of Rename Activity by Day and Month', fontsize=24, fontweight='bold', pad=20)
    plt.xlabel('Day of Month', fontsize=20)
    plt.ylabel('Month', fontsize=20)
    
    # Customize y-axis labels to show month names with bigger font
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    plt.yticks(range(12), [f"{i+1} - {month_names[i]}" for i in range(12)], rotation=0, fontsize=18)
    plt.xticks(fontsize=18)
    
    plt.tight_layout()
    
    # Save the heatmap
    plt.savefig(output_dir / 'rename_activity_day_heatmap.png', dpi=300, bbox_inches='tight')
    print(f"Day heatmap saved to: {output_dir / 'rename_activity_day_heatmap.png'}")
    
    plt.close()  # Close the figure to free memory
    
    # Print heatmap statistics
    print(f"\nDay Heatmap Summary:")
    print(f"Peak activity: {heatmap_pivot.max().max():.0f} renames")
    max_month, max_day = np.unravel_index(heatmap_pivot.values.argmax(), heatmap_pivot.shape)
    print(f"Peak period: Month {max_month + 1} ({month_names[max_month]}), Day {heatmap_pivot.columns[max_day]}")
    print(f"Total days with activity: {(heatmap_pivot > 0).sum().sum()}")
    
    return heatmap_pivot

def create_histogram(df, output_dir):
    """Create a histogram of rename counts per commit"""
    # Convert output_dir to Path object if it's a string
    if isinstance(output_dir, str):
        output_dir = Path(output_dir)
    
    plt.figure(figsize=(12, 8))  # Adjusted height for horizontal layout
    
    # Get value counts for the histogram data
    value_counts = df['count'].value_counts().sort_index()
    rename_counts = value_counts.index.tolist()
    commit_frequencies = value_counts.values.tolist()
    
    # Create horizontal bar chart (flipped histogram)
    bars = plt.barh(rename_counts, commit_frequencies,
                    color='#FFA500',  # Orange color similar to example
                    edgecolor='black',
                    alpha=0.8)
    
    # Customize the plot
    plt.title('Distribution of Rename Counts Per Commit', fontsize=24, fontweight='bold', pad=20)
    plt.xlabel('Number of Commits', fontsize=20)  # Flipped: now x-axis shows commit counts
    plt.ylabel('Number of Renames in a Commit', fontsize=20)  # Flipped: now y-axis shows rename counts
    
    # Add grid for better readability
    plt.grid(True, alpha=0.3, axis='x')  # Changed to x-axis grid
    
    # Set y-axis to show integer values with bigger font
    plt.yticks(range(0, df['count'].max() + 1, max(1, df['count'].max() // 20)), fontsize=18)
    plt.xticks(fontsize=18)
    
    # Add some statistics as text on the plot with bigger font
    mean_renames = df['count'].mean()
    median_renames = df['count'].median()
    max_renames = df['count'].max()
    
    stats_text = f"Mean: {mean_renames:.1f}\nMedian: {median_renames:.1f}\nMax: {max_renames}"
    plt.text(0.7, 0.8, stats_text, transform=plt.gca().transAxes, 
             bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8),
             fontsize=16, verticalalignment='top')
    
    plt.tight_layout()
    
    # Save the histogram
    plt.savefig(output_dir / 'rename_distribution_histogram.png', dpi=300, bbox_inches='tight')
    print(f"Histogram saved to: {output_dir / 'rename_distribution_histogram.png'}")
    
    plt.close()  # Close the figure to free memory
    
    # Print distribution statistics
    print(f"\nHistogram Summary:")
    print(f"Total commits: {len(df)}")
    print(f"Commits with 0 renames: {(df['count'] == 0).sum()}")
    print(f"Commits with 1 rename: {(df['count'] == 1).sum()}")
    print(f"Commits with 2+ renames: {(df['count'] >= 2).sum()}")
    print(f"Most renames in single commit: {max_renames}")
    print(f"Average renames per commit: {mean_renames:.2f}")
    
    # Show top rename counts
    value_counts = df['count'].value_counts().sort_index()
    print(f"\nTop rename count frequencies:")
    for count, frequency in value_counts.head(10).items():
        print(f"  {count} renames: {frequency} commits")
    
    return value_counts

def create_json_analysis(df, repo_path, output_dir, target_commit_hash=None, project_name=None, developer_name=None, original_commit_count=None, renamed_attributes=None):
    """Create a comprehensive JSON analysis of the dataset with optional author analysis"""
    # Convert output_dir to Path object if it's a string
    if isinstance(output_dir, str):
        output_dir = Path(output_dir)
    
    # Create the output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)
    
    
    # Basic statistics
    rename_counts = df['count']
    
    # Calculate statistics
    mean_renames = float(rename_counts.mean())
    median_renames = float(rename_counts.median())
    max_renames = int(rename_counts.max())
    
    # Calculate mode (most frequent value)
    mode_result = stats.mode(rename_counts, keepdims=True)
    mode_renames = int(mode_result.mode[0])
    
    # Dataset statistics
    total_commits = len(df)
    commits_with_more_than_1_rename = int((rename_counts > 1).sum())
    total_renames = int(rename_counts.sum())
    
    # Prepare JSON data
    json_data = {
        "dataset_statistics": {
            "total_analyzed_commit": original_commit_count if original_commit_count is not None else total_commits,
            "total_rename_commit": total_commits,
            "total_renames": total_renames,
            "total_co_rename_commit": commits_with_more_than_1_rename,
            "co_rename_precentage": round((commits_with_more_than_1_rename / total_commits) * 100, 2)
        },
        "rename_statistics": {
            "mean": round(mean_renames, 2),
            "median": median_renames,
            "mode": mode_renames,
            "max": max_renames
        },
        "analysis_metadata": {
            "project_name": project_name if project_name else "Unknown Project",
            "analysis_date": pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'),
            "dataset_date_range": {
                "earliest_commit": pd.to_datetime(df['timestamp'].min()).strftime('%Y-%m-%d %H:%M:%S'),
                "latest_commit": pd.to_datetime(df['timestamp'].max()).strftime('%Y-%m-%d %H:%M:%S')
            }
        },
        "renamed_attributes": [{"code_element": code_element, "rename": rename} for code_element, rename in renamed_attributes] if renamed_attributes else []
    }
    
    # If target commit hash is provided, add target commit analysis
    if target_commit_hash:
        # Find the target commit in the dataset
        commit_row = df[df['commit'] == target_commit_hash]
        
        # Skip commits with 3 or fewer renames
        # if not commit_row.empty and commit_row.iloc[0]['count'] <= 3:
        #     print(f"Warning: Commit {target_commit_hash} has {commit_row.iloc[0]['count']} renames (less than or equal to 3)")
        #     return None
            
        if not commit_row.empty:
            # Get author info directly from the DataFrame
            author_name = commit_row.iloc[0]['author_name']
            author_email = commit_row.iloc[0]['author_email']
            
            # Get all commits by this author
            author_commits = df[(df['author_name'] == author_name) & (df['author_email'] == author_email)]
            
            if not author_commits.empty:
                # Calculate author statistics
                author_total_commits = len(author_commits)
                author_total_renames = int(author_commits['count'].sum())
                author_avg_renames = round(author_commits['count'].mean(), 2)
                author_max_renames = int(author_commits['count'].max())
                
                # Get the target commit's rename count
                if json_data.get('commits') and len(json_data['commits']) > 0:
                    target_commit_renames = get_rename_instance_count(json_data['commits'][0]['refactorings'])
                else:
                    target_commit_renames = 0
                target_commit_timestamp = get_commit_timestamp(target_commit_hash, repo_path)
                # Convert timestamp to string for JSON serialization
                if target_commit_timestamp is not None:
                    target_commit_timestamp_str = target_commit_timestamp.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    target_commit_timestamp_str = None
                
                json_data["target_commit_analysis"] = {
                    "commit_hash": target_commit_hash,
                    "found_in_dataset": True,
                    "author_info_available": True,
                    "target_commit_info": {
                        "total_rename_in_author_commit": target_commit_renames,
                        "timestamp": target_commit_timestamp_str
                    },
                    "author_info": {
                        "name": author_name,
                        "email": author_email,
                        "total_rename_commit_by_author": author_total_commits,
                        "total_rename_by_author": author_total_renames,
                        "average_renames_per_commit": author_avg_renames,
                        "max_renames_in_single_commit": author_max_renames,
                        "percentage_of_total_commits": round((author_total_commits / total_commits) * 100, 2),
                        "percentage_of_total_renames": round((author_total_renames / total_renames) * 100, 2)
                    }
                }
                
                print(f"Author analysis complete:")
                print(f"  - {author_name} has {author_total_commits} commits in the dataset")
                print(f"  - Total renames: {author_total_renames}")
                print(f"  - Average renames per commit: {author_avg_renames}")
            else:
                print(f"No other commits found for author {author_name} in the dataset")
                json_data["target_commit_analysis"] = {
                    "commit_hash": target_commit_hash,
                    "found_in_dataset": True,
                    "author_info_available": True,
                    "target_commit_info": {
                        "total_rename_in_author_commit": int(commit_row.iloc[0]['count']),
                        "timestamp": pd.to_datetime(commit_row.iloc[0]['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
                    },
                    "author_info": {
                        "name": author_name,
                        "email": author_email,
                        "total_rename_commit_by_author": 1,
                        "total_rename_by_author": int(commit_row.iloc[0]['count']),
                        "average_renames_per_commit": float(commit_row.iloc[0]['count']),
                        "max_renames_in_single_commit": int(commit_row.iloc[0]['count']),
                        "percentage_of_total_commits": round((1 / total_commits) * 100, 2),
                        "percentage_of_total_renames": round((int(commit_row.iloc[0]['count']) / total_renames) * 100, 2)
                    }
                }
        else:
            print(f"Target commit {target_commit_hash} not found in dataset")
            processed, data = process_single_commit_with_refactoringminer(repo_path, target_commit_hash, f'{output_dir}/single_commit_analysis/{target_commit_hash}.json')
            
            if processed:
                author_name, author_email = get_commit_author_info(target_commit_hash, repo_path)
                developer_name = author_name.split(' ')[0]
                author_commits = df[(df['author_name'] == author_name) & (df['author_email'] == author_email)]
            
                if not author_commits.empty:
                    # Calculate author statistics
                    author_total_commits = len(author_commits)
                    author_total_renames = int(author_commits['count'].sum())
                    author_avg_renames = round(author_commits['count'].mean(), 2)
                    author_max_renames = int(author_commits['count'].max())
                
        
                    if data.get('commits') and len(data['commits']) > 0:
                        target_commit_renames = get_rename_instance_count(data['commits'][0]['refactorings'])
                    else:
                        target_commit_renames = 0
                    target_commit_timestamp = get_commit_timestamp(target_commit_hash, repo_path)
                    # Convert timestamp to string for JSON serialization
                    if target_commit_timestamp is not None:
                        target_commit_timestamp_str = target_commit_timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        target_commit_timestamp_str = None
                
                    json_data["target_commit_analysis"] = {
                        "commit_hash": target_commit_hash,
                        "found_in_dataset": True,
                         "author_info_available": True,
                         "target_commit_info": {
                        "total_rename_in_author_commit": target_commit_renames,
                        "timestamp": target_commit_timestamp_str
                    },
                    "author_info": {
                        "name": author_name,
                        "email": author_email,
                        "total_rename_commit_by_author": author_total_commits,
                        "total_rename_by_author": author_total_renames,
                        "average_renames_per_commit": author_avg_renames,
                        "max_renames_in_single_commit": author_max_renames,
                        "percentage_of_total_commits": round((author_total_commits / total_commits) * 100, 2),
                        "percentage_of_total_renames": round((author_total_renames / total_renames) * 100, 2)
                    }
                }
                
                    print(f"Author analysis complete by single commit analysis:")
                    print(f"  - {author_name} has {author_total_commits} commits in the dataset")
                    print(f"  - Total renames: {author_total_renames}")
                    print(f"  - Average renames per commit: {author_avg_renames}")

            else:
                print(f"Failed to process single commit {target_commit_hash}")
                return None
    
    # Save JSON file
    json_file = output_dir / f'comprehensive_analysis_{developer_name}.json'
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    
    print(f"Comprehensive JSON analysis saved to: {json_file}")
    
    # Print summary
    print(f"\nJSON Analysis Summary:")
    if original_commit_count is not None:
        print(f"Total commits from count file (deduplicated): {original_commit_count}")
    print(f"Total processed commits: {total_commits}")
    print(f"Total renames: {total_renames}")
    print(f"Commits with >1 rename: {commits_with_more_than_1_rename} ({round((commits_with_more_than_1_rename / total_commits) * 100, 1)}%)")
    print(f"Mean renames per commit: {round(mean_renames, 2)}")
    print(f"Median renames per commit: {median_renames}")
    print(f"Mode renames per commit: {mode_renames}")
    print(f"Max renames per commit: {max_renames}")
    
    return json_data

def create_comprehensive_developer_analysis(df, repo_path, output_dir):
    """Create comprehensive analysis of all developers in the dataset"""
    # Convert output_dir to Path object if it's a string
    if isinstance(output_dir, str):
        output_dir = Path(output_dir)
    
    print("Creating comprehensive developer analysis for all commits...")
    
    # Get author info for all commits (this might take a while)
    print("Fetching author information for all commits...")
    
    authors_info = []
    for i, (_, row) in enumerate(df.iterrows()):
        if i % 50 == 0:
            print(f"Processing commit {i+1}/{len(df)}: {row['commit'][:8]}")
        name, email = get_commit_author_info(row['commit'], repo_path)
        authors_info.append({'name': name, 'email': email})
    
    # Add author info to dataframe
    df_with_authors = df.copy()
    df_with_authors['author_name'] = [info['name'] for info in authors_info]
    df_with_authors['author_email'] = [info['email'] for info in authors_info]
    
    # Remove rows where we couldn't get author information
    df_with_authors = df_with_authors.dropna(subset=['author_name', 'author_email'])
    
    print(f"Successfully got author info for {len(df_with_authors)} commits")
    
    # Calculate comprehensive stats per developer
    comprehensive_stats = df_with_authors.groupby(['author_name', 'author_email']).agg({
        'count': ['count', 'sum', 'mean', 'max']
    }).round(2)
    
    # Flatten column names
    comprehensive_stats.columns = ['total_commits', 'total_renames', 'avg_renames_per_commit', 'max_renames_single_commit']
    comprehensive_stats = comprehensive_stats.reset_index()
    
    # Sort by total renames (descending)
    comprehensive_stats = comprehensive_stats.sort_values('total_renames', ascending=False)
    
    # Save comprehensive developer analysis
    comprehensive_file = output_dir / 'comprehensive_developer_analysis.csv'
    comprehensive_stats.to_csv(comprehensive_file, index=False)
    print(f"Comprehensive developer analysis saved to: {comprehensive_file}")
    
    # Print summary
    print(f"\nComprehensive Developer Analysis Summary:")
    print(f"Total unique developers: {len(comprehensive_stats)}")
    print(f"Total commits analyzed: {comprehensive_stats['total_commits'].sum()}")
    print(f"Total renames: {comprehensive_stats['total_renames'].sum()}")
    
    top_dev = comprehensive_stats.iloc[0]
    print(f"Most active developer: {top_dev['author_name']} ({top_dev['author_email']})")
    print(f"  - {int(top_dev['total_commits'])} commits, {int(top_dev['total_renames'])} total renames")
    
    return comprehensive_stats, df_with_authors

def create_developer_histogram(df, repo_path, output_dir):
    """Create a histogram of developers for top 50 commits with highest rename counts"""
    # Convert output_dir to Path object if it's a string
    if isinstance(output_dir, str):
        output_dir = Path(output_dir)
    
    print("Getting top 50 commits with highest rename counts...")
    
    # Get top 50 commits with highest rename counts
    top_50_commits = df.nlargest(50, 'count')
    
    print("Fetching author information for top commits...")
    
    # Get authors info for these commits
    authors_info = []
    for i, (_, row) in enumerate(top_50_commits.iterrows()):
        if i % 10 == 0:
            print(f"Processing author {i+1}/50: {row['commit'][:8]}")
        name, email = get_commit_author_info(row['commit'], repo_path)
        authors_info.append({'name': name, 'email': email})
    
    # Add authors to the dataframe
    top_50_commits = top_50_commits.copy()
    top_50_commits['author_name'] = [info['name'] for info in authors_info]
    top_50_commits['author_email'] = [info['email'] for info in authors_info]
    
    # Remove rows where we couldn't get author information
    top_50_commits = top_50_commits.dropna(subset=['author_name', 'author_email'])
    
    # Calculate both commit counts and total renames per author
    author_stats = top_50_commits.groupby(['author_name', 'author_email']).agg({
        'count': ['count', 'sum']  # count of commits, sum of renames
    }).round(1)
    
    # Flatten column names
    author_stats.columns = ['commit_count', 'total_renames']
    author_stats = author_stats.reset_index()
    
    # Sort by commit count (primary) then by total renames (secondary)
    author_stats = author_stats.sort_values(['commit_count', 'total_renames'], ascending=[False, False])
    
    # Create horizontal bar chart
    plt.figure(figsize=(14, max(8, len(author_stats) * 0.5)))
    
    # Create horizontal bar chart for commits
    bars = plt.barh(range(len(author_stats)), author_stats['commit_count'], 
                   color='#FF6B35', alpha=0.8, label='Commits')
    
    # Customize the plot
    plt.title('Developer Contributions: Top 50 Highest Rename Count Commits\n(Commits and Total Renames)', 
              fontsize=20, fontweight='bold', pad=20)  # Slightly smaller to avoid overlap
    plt.xlabel('Number of Commits', fontsize=18)
    plt.ylabel('Developer', fontsize=18)
    
    # Set y-axis labels to author names with bigger font
    plt.yticks(range(len(author_stats)), author_stats['author_name'], fontsize=14)  # Slightly smaller for readability
    
    # Add value labels on bars showing both commits and total renames
    for i, (_, row) in enumerate(author_stats.iterrows()):
        commits = int(row['commit_count'])
        renames = int(row['total_renames'])
        
        # Add commit count at the end of the bar (outside) with bigger font
        plt.text(row['commit_count'] + 0.1, i, f'{commits}', 
                ha='left', va='center', fontsize=14, fontweight='bold')
        
        # Add total renames inside the bar (centered)
        if row['commit_count'] >= 1:  # Only show inside if bar is wide enough
            plt.text(row['commit_count'] / 2, i, f'{renames} renames', 
                    ha='center', va='center', fontsize=12, fontweight='bold', 
                    color='white', bbox=dict(boxstyle="round,pad=0.2", facecolor='black', alpha=0.7))
        else:  # For very short bars, place it outside after the commit count
            plt.text(row['commit_count'] + 0.1, i - 0.2, f'({renames} renames)', 
                    ha='left', va='center', fontsize=11, style='italic', color='#666666')
    
    # Add grid for better readability
    plt.grid(True, alpha=0.3, axis='x')
    
    # Add legend explaining the labels with bigger font
    legend_elements = [
        Patch(facecolor='#FF6B35', alpha=0.8, label='Number of Commits'),
        Patch(facecolor='white', alpha=0, label='(Total Renames)')
    ]
    plt.legend(handles=legend_elements, loc='upper right', fontsize=14)
    
    # Adjust layout to prevent label cutoff
    plt.tight_layout()
    
    # Save the histogram
    plt.savefig(output_dir / 'developer_top_commits_histogram.png', dpi=300, bbox_inches='tight')
    print(f"Developer histogram saved to: {output_dir / 'developer_top_commits_histogram.png'}")
    
    plt.close()  # Close the figure to free memory
    
    # Print statistics
    print(f"\nTop 50 Developer Analysis Summary:")
    print(f"Total unique developers in top 50 commits: {len(author_stats)}")
    top_author = author_stats.iloc[0]
    print(f"Top developer: {top_author['author_name']} ({top_author['author_email']})")
    print(f"  - {int(top_author['commit_count'])} commits, {int(top_author['total_renames'])} total renames")
    print(f"Average commits per developer: {author_stats['commit_count'].mean():.1f}")
    print(f"Average total renames per developer: {author_stats['total_renames'].mean():.1f}")
    
    # Show detailed breakdown
    print(f"\nDetailed breakdown:")
    for _, row in author_stats.head(10).iterrows():
        commits = int(row['commit_count'])
        total_renames = int(row['total_renames'])
        avg_renames = total_renames / commits
        
        # Get individual commit data for this author
        author_commits = top_50_commits[top_50_commits['author_name'] == row['author_name']]
        max_renames = author_commits['count'].max()
        
        print(f"  {row['author_name']} ({row['author_email']}): {commits} commits, {total_renames} total renames, "
              f"avg {avg_renames:.1f} renames/commit, max {max_renames} renames")
    
    # Save detailed CSV with enhanced information including emails
    detailed_csv = top_50_commits[['commit', 'author_name', 'author_email', 'count', 'timestamp']].copy()
    detailed_csv['commit_timestamp'] = pd.to_datetime(detailed_csv['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')
    detailed_csv = detailed_csv.drop('timestamp', axis=1)
    detailed_csv = detailed_csv.sort_values('count', ascending=False)
    
    csv_file = output_dir / 'top_50_commits_with_authors.csv'
    detailed_csv.to_csv(csv_file, index=False)
    print(f"Top 50 commits with authors saved to: {csv_file}")
    
    # Save author summary with emails
    author_summary = author_stats.copy()
    author_summary['avg_renames_per_commit'] = (author_summary['total_renames'] / 
                                              author_summary['commit_count']).round(2)
    
    summary_file = output_dir / 'developer_summary.csv'
    author_summary.to_csv(summary_file, index=False)
    print(f"Developer summary (top 50) saved to: {summary_file}")
    
    return author_stats, detailed_csv

def main():
    parser = argparse.ArgumentParser(description='Weekly time series analysis of refactoring counts')
    parser.add_argument('--csv-file', required=True, help='Path to CSV file with commit IDs and counts')
    parser.add_argument('--repo-path', required=True, help='Path to the Git repository')
    parser.add_argument('--output-dir', default='weekly_results', 
                       help='Directory to save analysis results (default: weekly_results)')
    parser.add_argument('--commit-hash', help='Optional commit hash to analyze specific author')
    parser.add_argument('--project-name', help='Name of the project being analyzed')
    
    args = parser.parse_args()
    
    # Verify inputs
    csv_path = Path(args.csv_file)
    if not csv_path.exists():
        print(f"Error: CSV file '{csv_path}' does not exist")
        return
    
    repo_path = Path(args.repo_path)
    if not repo_path.exists():
        print(f"Error: Repository path '{repo_path}' does not exist")
        return
    
    if not (repo_path / '.git').exists():
        print(f"Error: '{repo_path}' is not a Git repository")
        return
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)
    
    try:
        # Load and enrich data
        df, initial_count = load_and_enrich_data(csv_path, repo_path)
        
        if len(df) == 0:
            print("No valid data to analyze")
            return
        
        # Create weekly plot
        print("\nCreating weekly time series plot...")
        weekly_data, summary_data = create_weekly_plot(df, output_dir, args.project_name)
        
        # Create heatmap
        print("\nCreating heatmap of rename activity...")
        heatmap_data = create_heatmap(df, output_dir)
        
        # Create day heatmap
        print("\nCreating heatmap of rename activity by day of month...")
        day_heatmap_data = create_day_heatmap(df, output_dir)
        
        # Create histogram
        print("\nCreating histogram of rename counts per commit...")
        histogram_data = create_histogram(df, output_dir)
        
        # Create comprehensive developer analysis
        print("\nCreating comprehensive developer analysis for all commits...")
        comprehensive_stats, df_with_authors = create_comprehensive_developer_analysis(df, repo_path, output_dir)
        
        # Create developer histogram
        print("\nCreating developer histogram for top 50 commits with highest rename counts...")
        developer_histogram_data, detailed_csv = create_developer_histogram(df, repo_path, output_dir)
        
        # Create JSON analysis (with optional commit hash analysis)
        print("\nCreating comprehensive JSON analysis...")
        json_data = create_json_analysis(df, repo_path, output_dir, args.commit_hash, args.project_name, original_commit_count=initial_count)
        
        print(f"\nResults saved in: {output_dir}")
        print(f"Files created:")
        print(f"  - weekly_rename_activity.png (plot)")
        print(f"  - weekly_grouped_data.csv (weekly data)")
        print(f"  - weekly_summary.csv (weekly summary)")
        print(f"  - rename_activity_heatmap.png (heatmap)")
        print(f"  - rename_activity_day_heatmap.png (day heatmap)")
        print(f"  - rename_distribution_histogram.png (histogram)")
        print(f"  - developer_top_commits_histogram.png (developer histogram)")
        print(f"  - top_50_commits_with_authors.csv (top 50 commits with authors)")
        print(f"  - developer_summary.csv (developer statistics)")
        print(f"  - comprehensive_developer_analysis.csv (all developers with emails)")
        print(f"  - comprehensive_analysis.json (comprehensive JSON analysis)")
        
        if args.commit_hash:
            print(f"\nSpecial analysis performed for commit: {args.commit_hash}")
            print(f"Author analysis results are included in the JSON file.")
        
        if args.project_name:
            print(f"Project name '{args.project_name}' included in analysis.")
        
    except Exception as e:
        print(f"Error during analysis: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 