import os
from pathlib import Path
import json
from email.message import EmailMessage
from email.utils import make_msgid
from datetime import datetime

# Import your existing helpers
from email_template import attach_inline_image, generate_html_email

def generate_emails_for_all_projects(analyze_dir, analyzed_repo_file=None, analysis_date=None):
    """
    Generate emails for all projects
    
    Args:
        analyze_dir (str): Directory containing analysis results
        analyzed_repo_file (str, optional): Path to analyzed_repo.json file. If None, looks in current directory
        analysis_date (str, optional): Date in YYYY-MM-DD format. If None, uses today's date
    """
    if analysis_date is None:
        analysis_date = datetime.now().strftime("%Y-%m-%d")
    
    if analyzed_repo_file is None:
        analyzed_repo_file = "analyzed_repo.json"
    
    analyze_dir = Path(analyze_dir)
    analyzed_repo = None
    repo_url = None
    dev_analysis_dir=""
    
    # Check if analyzed_repo file exists
    if not os.path.exists(analyzed_repo_file):
        print(f"Error: analyzed_repo file not found: {analyzed_repo_file}")
        return
    
    with open(analyzed_repo_file, "r") as f:
        analyzed_repo = json.load(f)
    for project_dir in analyze_dir.iterdir():
        repo_url = None
        if not project_dir.is_dir():
            continue

        dev_analysis_dir = project_dir / analysis_date / "developer_analysis"
        plots_dir = project_dir / "plots"
        print(f'Looking for analysis in: {dev_analysis_dir}')
        print(f'plots_dir: {plots_dir}')
        
        if not dev_analysis_dir.exists():
            print(f"Skipping {project_dir}: No developer_analysis directory found for date {analysis_date}")
            continue
            
        json_files = list(dev_analysis_dir.glob("*.json"))
        if not json_files:
            print(f"Skipping {project_dir}: No developer_analysis JSON found.")
            continue
        weekly_img = plots_dir / "weekly_rename_activity.png"
        heatmap_img = plots_dir / "rename_activity_heatmap.png"
        if not weekly_img.exists() or not heatmap_img.exists():
            print(f"Skipping {project_dir}: Missing plot(s).")
            continue

        for developer_json in json_files:
            # Load stats
            with open(developer_json, "r") as f:
                stats = json.load(f)
            
            if repo_url is None:
                for repo in analyzed_repo:
                    if repo['project'] == stats.get("analysis_metadata", {}).get("project_name", ""):
                        repo_url = repo['repo_url']
                        break
            # Extract developer info from the JSON structure
            author_info = stats.get("target_commit_analysis", {}).get("author_info", {})
            developer_name = author_info.get("name", "Developer")
            developer_email = author_info.get("email", "developer@example.com")
            entity_count = author_info.get("total_rename_by_author", 0)
            commit_count = author_info.get("total_rename_commit_by_author", 0)
            total_renames_in_the_commit = stats.get("target_commit_analysis", {}).get("target_commit_info", {}).get("total_rename_in_author_commit", 0)
            renamed_attributes = stats.get("renamed_attributes", [])

            # Construct commit URL if possible
            project = stats.get("analysis_metadata", {}).get("project_name", "project")
            commit_hash = stats.get("target_commit_analysis", {}).get("commit_hash", "EXAMPLE")
            commit_url = f"{repo_url.split('.git')[0]}/commit/{commit_hash}"

            # Prepare email
            msg = EmailMessage()
            msg['Subject'] = f"Study on Cluster-Renames in {project}"
            msg['From'] = "Raihan Ullah <Raihan.Ullah@colorado.edu>"
            msg['To'] = developer_email

            # Generate Content-IDs for images
            weekly_img_cid = make_msgid(domain="inline")
            heatmap_img_cid = make_msgid(domain="inline")

            # Set HTML body using your template
            html = generate_html_email(
                developer_name, stats, weekly_img_cid, heatmap_img_cid, commit_url, entity_count, commit_count, total_renames_in_the_commit, renamed_attributes
            )
            msg.set_content("This email contains HTML content. Please view in an HTML-compatible email client.")
            msg.add_alternative(html, subtype='html')

            # Attach images inline
            attach_inline_image(msg, weekly_img, weekly_img_cid)
            attach_inline_image(msg, heatmap_img, heatmap_img_cid)

            # Ensure the email_drafts directory exists in the project directory
            drafts_dir = dev_analysis_dir / "email_drafts"
            drafts_dir.mkdir(parents=True, exist_ok=True)
            # Save as .eml draft in the email_drafts directory, use developer name/email for uniqueness
            safe_name = developer_name.replace('@', '_').replace('.', '_')
            eml_path = drafts_dir / f"email_draft_{safe_name}_{analysis_date}.eml"
            with open(eml_path, "wb") as f:
                f.write(bytes(msg))
            print(f"Email draft with inline images saved as {eml_path}")

if __name__ == "__main__":
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate emails for all projects")
    parser.add_argument("analyze_dir", nargs='?', default="analysis_result", 
                       help="Directory containing analysis results (default: analysis_result)")
    parser.add_argument("--analyzed-repo-file", default=None,
                       help="Path to analyzed_repo.json file (default: analyzed_repo.json)")
    parser.add_argument("--analysis-date", default=None,
                       help="Analysis date in YYYY-MM-DD format (default: today)")
    
    args = parser.parse_args()
    
    generate_emails_for_all_projects(args.analyze_dir, args.analyzed_repo_file, args.analysis_date)