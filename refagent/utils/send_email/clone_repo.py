import pandas as pd
import os
import subprocess
import shutil
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def clone_repository(repo_url, base_path, project_name):
    """
    Clone a repository to the specified base path.
    
    Args:
        repo_url (str): GitHub repository URL
        base_path (str): Base directory to clone into
        project_name (str): Name of the project (for directory naming)
        
    Returns:
        str: 'cloned' if newly cloned, 'exists' if already exists, 'failed' if failed
    """
    try:
        # Create base path if it doesn't exist
        Path(base_path).mkdir(parents=True, exist_ok=True)
        
        # Determine the target directory (extract repo name from URL)
        repo_name = repo_url.split('/')[-1]
        if repo_name.endswith('.git'):
            repo_name = repo_name[:-4]
        
        target_path = os.path.join(base_path, repo_name)
        lowercase_name = repo_name.lower()
        lowercase_path = os.path.join(base_path, lowercase_name)
        
        # Check if repository already exists (either original name or lowercase) - don't clone if it does
        if os.path.exists(target_path):
            print(f"    ⚠ Repository already exists, skipping: {target_path}")
            return 'exists'
        elif os.path.exists(lowercase_path):
            print(f"    ⚠ Repository already exists (lowercase), skipping: {lowercase_path}")
            return 'exists'
        
        print(f"    📥 Shallow cloning {repo_url} (since 2024-01-01) to {target_path}")
        
        try:
            result = subprocess.run([
                'git', 'clone', '--progress', '--shallow-since', '2024-01-01', repo_url, target_path
            ], timeout=3000)  # 50 minutes timeout, shows progress in real-time
            
            if result.returncode == 0:
                print(f"    ✓ Successfully cloned: {repo_name}")
                
                # Rename directory to lowercase if needed
                lowercase_name = repo_name.lower()
                if repo_name != lowercase_name:
                    lowercase_path = os.path.join(base_path, lowercase_name)
                    
                    # Check if lowercase directory already exists
                    if os.path.exists(lowercase_path):
                        print(f"    ⚠ Lowercase directory already exists: {lowercase_path}")
                        print(f"    ✗ Removing newly cloned directory: {target_path}")
                        shutil.rmtree(target_path)
                        return 'failed'
                    
                    try:
                        print(f"    🔄 Renaming {repo_name} → {lowercase_name}")
                        os.rename(target_path, lowercase_path)
                        print(f"    ✓ Successfully renamed to lowercase: {lowercase_name}")
                    except Exception as e:
                        print(f"    ✗ Failed to rename to lowercase: {e}")
                        return 'failed'
                
                return 'cloned'
            else:
                print(f"    ✗ Failed to clone {repo_name} (exit code: {result.returncode})")
                return 'failed'
                
        except subprocess.TimeoutExpired:
            print(f"    ✗ Timeout cloning {repo_name} (exceeded 50 minutes)")
            return 'failed'
            
    except Exception as e:
        print(f"    ✗ Error cloning {repo_name}: {e}")
        return 'failed'

def extract_project_names_from_txt(txt_file):
    if not os.path.exists(txt_file):
        print(f"Error: Text file not found: {txt_file}")
        return []
    
    project_names = []
    
    try:
        with open(txt_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):  # Skip empty lines and comments
                    continue
                
                # Extract filename from path (e.g., "projects/temp_kafka.jsonl" -> "temp_kafka.jsonl")
                filename = os.path.basename(line)
                
                # Remove "temp_" prefix and ".jsonl" suffix
                if filename.startswith('temp_') and filename.endswith('.jsonl'):
                    project_name = filename[5:-6]  # Remove "temp_" (5 chars) and ".jsonl" (6 chars)
                    project_names.append(project_name)
        
        print(f"Extracted {len(project_names)} project names from {txt_file}")
        print(f"Project names: {project_names}")
        
        return project_names
        
    except Exception as e:
        print(f"Error reading text file: {e}")
        return []

if __name__ == "__main__":
    # File paths
    csv_file = 'analysis_result/projects_sorted.csv'
    txt_file = 'projects/created_files.txt'
    
    # Check if files exist
    if not os.path.exists(csv_file):
        print(f"Error: CSV file not found: {csv_file}")
        exit(1)
    
    if not os.path.exists(txt_file):
        print(f"Error: Text file not found: {txt_file}")
        exit(1)
    
    try:
        # Read the CSV file
        print("Reading CSV file...")
        df = pd.read_csv(csv_file)
        
        print(f"Successfully loaded CSV file: {csv_file}")
        print(f"CSV Shape: {df.shape}")
        print(f"CSV Columns: {df.columns.tolist()}")
        
        # Extract project names from created_files.txt
        print(f"\nExtracting project names from: {txt_file}")
        project_names = extract_project_names_from_txt(txt_file)
        
        if not project_names:
            print("No project names found. Exiting.")
            exit(1)
        
        # Filter CSV to only include rows where 'name' column contains project names as exact keywords
        print(f"\nFiltering CSV for matching project names (exact keyword matching)...")
        
        def contains_exact_keyword(csv_name, keywords):
            """Check if any keyword appears as an exact word in the CSV name."""
            if pd.isna(csv_name):
                return False
            
            # Split CSV name by / delimiter only
            csv_parts = [part.lower() for part in csv_name.split('/')]
            
            # Check if any keyword matches any part exactly
            for keyword in keywords:
                if keyword.lower() in csv_parts:
                    return True
            return False
        
        # Apply the exact keyword matching
        mask = df['name'].apply(lambda x: contains_exact_keyword(x, project_names))
        filtered_df = df[mask]
        
        print(f"\nFiltered results:")
        print(f"Original CSV rows: {len(df)}")
        print(f"Matching rows found: {len(filtered_df)}")
        print(f"Projects from txt file: {len(project_names)}")
        
        if len(filtered_df) > 0:
            print(f"\nMatched projects (showing txt_name → csv_name mapping):")
            for csv_name in filtered_df['name'].tolist():
                # Find which txt project name matched this CSV name using exact keyword matching
                csv_parts = [part.lower() for part in csv_name.split('/')]
                matching_txt_names = [txt_name for txt_name in project_names 
                                    if txt_name.lower() in csv_parts]
                txt_match = ', '.join(matching_txt_names) if matching_txt_names else 'unknown'
                print(f"  - {txt_match} → {csv_name}")
            
            print(f"\nProject details:")
            print(filtered_df[['name', 'stargazers', 'forks', 'mainLanguage', 'size']].to_string(index=False))
            
            # Get PROJECTS_BASE_PATH from environment
            base_path = os.getenv('PROJECTS_BASE_PATH')
            if not base_path:
                print(f"\n⚠ PROJECTS_BASE_PATH environment variable not set!")
                print("Please set it using one of these methods:")
                print("  1. Create a .env file with: PROJECTS_BASE_PATH=/path/to/your/projects")
                print("  2. Export it in your shell: export PROJECTS_BASE_PATH=/path/to/your/projects")
                exit(1)
            
            print(f"\nCloning repositories to: {base_path}")
            print("=" * 60)
            
            # Clone each repository
            newly_cloned = 0
            already_existed = 0
            failed_clones = 0
            
            for csv_name in filtered_df['name'].tolist():
                # Create GitHub URL
                github_url = f"https://github.com/{csv_name}"
                
                print(f"\n🔄 Processing: {csv_name}")
                print(f"    URL: {github_url}")
                
                result = clone_repository(github_url, base_path, csv_name)
                if result == 'cloned':
                    newly_cloned += 1
                elif result == 'exists':
                    already_existed += 1
                else:  # 'failed'
                    failed_clones += 1
            
            # Summary
            print("\n" + "=" * 60)
            print("CLONING SUMMARY")
            print("=" * 60)
            print(f"Total repositories: {len(filtered_df)}")
            print(f"Newly cloned: {newly_cloned}")
            print(f"Already existed (skipped): {already_existed}")
            print(f"Failed: {failed_clones}")
            print(f"Base path: {base_path}")
            
            # Show unmatched project names from txt file
            matched_txt_names = []
            for csv_name in filtered_df['name'].tolist():
                csv_parts = [part.lower() for part in csv_name.split('/')]
                matched_txt_names.extend([txt_name for txt_name in project_names 
                                        if txt_name.lower() in csv_parts])
            
            unmatched_txt_names = [name for name in project_names if name not in matched_txt_names]
            if unmatched_txt_names:
                print(f"\n⚠ Unmatched projects from txt file:")
                for name in unmatched_txt_names:
                    print(f"  - {name}")
            
        else:
            print("\n⚠ No matching projects found!")
            print("Projects in txt file:", project_names)
            print("Sample projects in CSV:", df['name'].tolist()[:10], "..." if len(df) > 10 else "")
        
    except Exception as e:
        print(f"Error processing files: {e}")