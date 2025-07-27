import os
import subprocess


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


def get_repo_url(repo_path):
    """Get the repository URL from the local git repository"""
    try:
        original_dir = os.getcwd()
        os.chdir(repo_path)

        # Try to get the origin remote URL
        cmd = "git remote get-url origin"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

        os.chdir(original_dir)

        if result.returncode == 0:
            return result.stdout.strip()
        else:
            print("Error getting repository URL")
            return None
    except Exception as e:
        print(f"Error getting repository URL: {e}")
        return None


def git_pull(repo_path, branch=None):
    """
    Perform git pull on a local repository

    Args:
        repo_path (str): Path to the local Git repository
        branch (str): Specific branch to pull (optional, defaults to current branch)

    Returns:
        dict: {"success": bool, "output": str, "error": str}
    """
    try:
        original_dir = os.getcwd()
        os.chdir(repo_path)

        # Build git pull command
        if branch:
            cmd = f"git pull origin {branch}"
        else:
            cmd = "git pull"

        print(f"Running: {cmd}")
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

        os.chdir(original_dir)

        if result.returncode == 0:
            print(f"Git pull successful for {repo_path}")
            return {
                "success": True,
                "output": result.stdout.strip(),
                "error": ""
            }
        else:
            print(f"Git pull failed for {repo_path}: {result.stderr}")
            return {
                "success": False,
                "output": result.stdout.strip(),
                "error": result.stderr.strip()
            }

    except Exception as e:
        print(f"Error during git pull for {repo_path}: {e}")
        return {
            "success": False,
            "output": "",
            "error": str(e)
        }