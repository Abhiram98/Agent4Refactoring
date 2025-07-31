#!/usr/bin/env python3
"""
Script to collect all generated email .eml files from project directories
and copy them to a centralized generated_emails directory.

Usage:
    python collect_emails.py [analyze_dir] [--analysis-date YYYY-MM-DD]
    
This script will:
1. Scan all project directories in analyze_dir
2. Find email_drafts directories for the specified date
3. Copy all .eml files to analyze_dir/generated_emails/
4. Prefix filenames with project name for uniqueness
"""

import os
import shutil
import argparse
from pathlib import Path
from datetime import datetime


def collect_emails_from_projects(analyze_dir, analysis_date=None):
    """
    Collect all generated email .eml files from project directories.
    
    Args:
        analyze_dir (str): Directory containing analysis results
        analysis_date (str, optional): Date in YYYY-MM-DD format. If None, uses today's date
    """
    if analysis_date is None:
        analysis_date = datetime.now().strftime("%Y-%m-%d")
    
    analyze_dir = Path(analyze_dir)
    
    if not analyze_dir.exists():
        print(f"Error: Analysis directory not found: {analyze_dir}")
        return
    
    # Create centralized emails directory with date subdirectory
    emails_base_dir = analyze_dir / "generated_emails"
    emails_output_dir = emails_base_dir / analysis_date
    emails_output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Collecting emails from projects for date: {analysis_date}")
    print(f"Analysis directory: {analyze_dir}")
    print(f"Output directory: {emails_output_dir}")
    print("")
    
    total_emails_copied = 0
    projects_with_emails = 0
    
    # Scan all project directories
    for project_dir in analyze_dir.iterdir():
        if not project_dir.is_dir() or project_dir.name == "generated_emails":
            continue
            
        project_name = project_dir.name
        email_drafts_dir = project_dir / analysis_date / "developer_analysis" / "email_drafts"
        
        print(f"Checking project: {project_name}")
        print(f"  Looking for emails in: {email_drafts_dir}")
        
        if not email_drafts_dir.exists():
            print(f"  ✗ No email_drafts directory found for {project_name} on {analysis_date}")
            continue
        
        # Find all .eml files in the email_drafts directory
        eml_files = list(email_drafts_dir.glob("*.eml"))
        
        if not eml_files:
            print(f"  ✗ No .eml files found in {email_drafts_dir}")
            continue
        
        projects_with_emails += 1
        print(f"  ✓ Found {len(eml_files)} email file(s)")
        
        # Copy each .eml file to the centralized directory
        for eml_file in eml_files:
            # Create new filename with project prefix
            original_name = eml_file.name
            new_name = f"{project_name}_{original_name}"
            destination = emails_output_dir / new_name
            
            try:
                shutil.copy2(eml_file, destination)
                print(f"    ✓ Copied: {original_name} -> {new_name}")
                total_emails_copied += 1
            except Exception as e:
                print(f"    ✗ Failed to copy {original_name}: {e}")
        
        print("")
    
    # Summary
    print("=" * 50)
    print("COLLECTION SUMMARY")
    print("=" * 50)
    print(f"Analysis date: {analysis_date}")
    print(f"Projects scanned: {len([d for d in analyze_dir.iterdir() if d.is_dir() and d.name != 'generated_emails'])}")
    print(f"Projects with emails: {projects_with_emails}")
    print(f"Total emails copied: {total_emails_copied}")
    print(f"Emails saved to: {emails_output_dir}")
    
    if total_emails_copied > 0:
        print(f"\n✓ Successfully collected {total_emails_copied} email files!")
        
        # List the collected files
        collected_files = list(emails_output_dir.glob("*.eml"))
        if collected_files:
            print(f"\nCollected email files:")
            for email_file in sorted(collected_files):
                file_size = email_file.stat().st_size
                print(f"  - {email_file.name} ({file_size} bytes)")
    else:
        print(f"\n⚠ No email files were collected for date {analysis_date}")


def main():
    """Main function to handle command line arguments."""
    parser = argparse.ArgumentParser(description="Collect generated email files from all projects")
    parser.add_argument("analyze_dir", nargs='?', default="analysis_result",
                       help="Directory containing analysis results (default: analysis_result)")
    parser.add_argument("--analysis-date", default=None,
                       help="Analysis date in YYYY-MM-DD format (default: today)")
    
    args = parser.parse_args()
    
    collect_emails_from_projects(args.analyze_dir, args.analysis_date)


if __name__ == "__main__":
    main() 