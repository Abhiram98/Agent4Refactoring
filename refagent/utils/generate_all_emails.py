import os
from pathlib import Path
import json
from email.message import EmailMessage
from email.utils import make_msgid

# Import your existing helpers
from email_template import attach_inline_image, generate_html_email

def generate_emails_for_all_projects(analyze_dir):
    analyze_dir = Path(analyze_dir)
    analyzed_repo = None
    repo_url = None
    with open("/Users/moul7361/Desktop/AI-Agents/Agent4Refactoring/refagent/utils/analyze_and_send_email/analyze/analyzed_repo.json", "r") as f:
        analyzed_repo = json.load(f)
    for project_dir in analyze_dir.iterdir():
        repo_url = None
        if not project_dir.is_dir() or not project_dir.name.startswith("refactoring_results_"):
            continue

        dev_analysis_dir = project_dir / "developer_analysis"
        plots_dir = project_dir / "plots"
        print(f'plots_dir: {plots_dir}')
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
            org_or_user = "yourorg"  # <-- Set this to your actual org/user
            # commit_url = f"https://github.com/{org_or_user}/{project}/commit/{commit_hash}"
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
            drafts_dir = project_dir / "email_drafts"
            drafts_dir.mkdir(parents=True, exist_ok=True)
            # Save as .eml draft in the email_drafts directory, use developer name/email for uniqueness
            safe_name = developer_name.replace('@', '_').replace('.', '_')
            eml_path = drafts_dir / f"email_draft_{safe_name}.eml"
            with open(eml_path, "wb") as f:
                f.write(bytes(msg))
            print(f"Email draft with inline images saved as {eml_path}")

if __name__ == "__main__":
    analyze_dir = "/Users/moul7361/Desktop/AI-Agents/Agent4Refactoring/refagent/utils/analyze_and_send_email/analyze"
    generate_emails_for_all_projects(analyze_dir)