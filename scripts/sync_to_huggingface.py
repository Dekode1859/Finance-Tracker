import os
import sys
import requests
import json
import subprocess
from pathlib import Path

# Hugging Face API base URL
HF_API_URL = "https://huggingface.co/api"

def create_hf_space(repo_name, token, space_sdk="streamlit"):
    """Create a Hugging Face Space if it doesn't exist."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Check if space already exists
    response = requests.get(
        f"{HF_API_URL}/spaces/{os.environ.get('HF_USERNAME')}/{repo_name}",
        headers=headers
    )
    
    if response.status_code == 200:
        print(f"Space {repo_name} already exists. Will update it.")
        return True
    
    # Create space if it doesn't exist
    data = {
        "repo_id": f"{os.environ.get('HF_USERNAME')}/{repo_name}",
        "space_sdk": space_sdk,
        "private": False
    }
    
    response = requests.post(
        f"{HF_API_URL}/spaces/create",
        headers=headers,
        json=data
    )
    
    if response.status_code == 200:
        print(f"Successfully created space: {repo_name}")
        return True
    else:
        print(f"Failed to create space: {response.text}")
        return False

def configure_git_for_hf():
    """Configure git for Hugging Face."""
    subprocess.run(["git", "config", "--global", "credential.helper", "store"])
    
    # Create credentials file
    credential_file = os.path.expanduser("~/.git-credentials")
    with open(credential_file, "w") as f:
        f.write(f"https://{os.environ.get('HF_USERNAME')}:{os.environ.get('HF_TOKEN')}@huggingface.co\n")
    
    subprocess.run(["git", "config", "--global", "user.email", os.environ.get("GIT_EMAIL", "action@github.com")])
    subprocess.run(["git", "config", "--global", "user.name", os.environ.get("GIT_NAME", "GitHub Action")])

def create_hf_files(repo_path, repo_name):
    """Create necessary Hugging Face Space configuration files."""
    # Create README.md if it doesn't exist
    readme_path = os.path.join(repo_path, "README.md")
    if not os.path.exists(readme_path):
        with open(readme_path, "w") as f:
            f.write(f"# {repo_name}\n\nA Streamlit app for tracking banking transactions from email notifications.")
    
    # Create .gitignore if it doesn't exist
    gitignore_path = os.path.join(repo_path, ".gitignore")
    if not os.path.exists(gitignore_path):
        with open(gitignore_path, "w") as f:
            f.write("""
# Python
__pycache__/
*.py[cod]
*$py.class
.pytest_cache/
.coverage
htmlcov/
.venv
venv/
env/

# Local dev files
.env
token.json
credentials.json
*.db
*.sqlite
*.sqlite3

# Logs
*.log
            """.strip())
    
    # Create Streamlit configuration
    streamlit_config_dir = os.path.join(repo_path, ".streamlit")
    os.makedirs(streamlit_config_dir, exist_ok=True)
    
    config_path = os.path.join(streamlit_config_dir, "config.toml")
    with open(config_path, "w") as f:
        f.write("""
[theme]
primaryColor = "#FF4B4B"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F0F2F6"
textColor = "#262730"
        """.strip())
    
    # Create requirements.txt if it doesn't exist in the target repo
    reqs_path = os.path.join(repo_path, "requirements.txt")
    if not os.path.exists(reqs_path):
        # Copy from source repo if exists
        source_reqs = os.path.join(os.getcwd(), "requirements.txt")
        if os.path.exists(source_reqs):
            with open(source_reqs, "r") as src, open(reqs_path, "w") as dst:
                dst.write(src.read())
        else:
            # Create basic requirements.txt
            with open(reqs_path, "w") as f:
                f.write("""
streamlit==1.43.2
pandas==2.2.4
google-auth==2.27.0
google-auth-oauthlib==1.2.0
google-api-python-client==2.115.0
psutil==5.9.6
                """.strip())
    
    # Create packages.txt for system dependencies
    packages_path = os.path.join(repo_path, "packages.txt")
    if not os.path.exists(packages_path):
        with open(packages_path, "w") as f:
            f.write("sqlite3")
    
    # Create a simple startup script if app.py is missing
    app_path = os.path.join(repo_path, "app.py")
    if not os.path.exists(app_path):
        source_app = os.path.join(os.getcwd(), "app.py")
        if os.path.exists(source_app):
            # Copy the app.py from the source repository
            with open(source_app, "r") as src, open(app_path, "w") as dst:
                dst.write(src.read())
    
    # Create Hugging Face Space metadata
    space_config = {
        "title": f"{repo_name}",
        "emoji": "💰",
        "colorFrom": "blue",
        "colorTo": "indigo",
        "sdk": "streamlit",
        "sdk_version": "1.43.2",
        "python_version": "3.10",
        "app_file": "app.py",
        "pinned": False,
        "license": "mit"
    }
    
    with open(os.path.join(repo_path, "README.md"), "r") as f:
        readme_content = f.read()
    
    # Update README with Hugging Face Space widget
    updated_readme = readme_content
    if "<!-- SPACES WIDGET -->" not in readme_content:
        updated_readme = readme_content + f"""

<!-- SPACES WIDGET -->
## Hugging Face Space

<a href="https://huggingface.co/spaces/{os.environ.get('HF_USERNAME')}/{repo_name}">
    <img src="https://huggingface.co/datasets/huggingface/badges/resolve/main/open-in-hf-spaces-md.svg" alt="Open in HF Spaces"/>
</a>
"""
    
    with open(os.path.join(repo_path, "README.md"), "w") as f:
        f.write(updated_readme)
    
    # Write Hugging Face Space metadata
    with open(os.path.join(repo_path, "README.md"), "a") as f:
        f.write("\n\n<!-- HF-SPACE-CONFIG\n")
        json.dump(space_config, f, indent=2)
        f.write("\n-->\n")

def sync_repo_to_hf(local_repo_path, repo_name, token):
    """Push local repo to Hugging Face."""
    temp_dir = f"/tmp/hf_{repo_name}"
    
    # Create temporary directory
    os.makedirs(temp_dir, exist_ok=True)
    
    # Initialize git repo in temp directory
    subprocess.run(["git", "init"], cwd=temp_dir, check=True)
    
    # Create .gitattributes for LFS
    with open(os.path.join(temp_dir, ".gitattributes"), "w") as f:
        f.write("*.sqlite filter=lfs diff=lfs merge=lfs -text\n")
        f.write("*.db filter=lfs diff=lfs merge=lfs -text\n")
        f.write("*.sqlite3 filter=lfs diff=lfs merge=lfs -text\n")
    
    # Copy files from source repo to temp dir, excluding .git directory
    print(f"Copying files from {local_repo_path} to {temp_dir}")
    subprocess.run(["rsync", "-av", "--exclude=.git", "--exclude=node_modules", 
                   "--exclude=__pycache__", f"{local_repo_path}/", temp_dir], check=True)
    
    # Create and configure HF-specific files
    create_hf_files(temp_dir, repo_name)
    
    # Add remote
    repo_url = f"https://huggingface.co/spaces/{os.environ.get('HF_USERNAME')}/{repo_name}"
    subprocess.run(["git", "remote", "add", "origin", repo_url], cwd=temp_dir, check=True)
    
    # Add, commit, and push
    subprocess.run(["git", "add", "."], cwd=temp_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Update from GitHub Actions"], cwd=temp_dir, check=True)
    subprocess.run(["git", "push", "--force", "origin", "main"], cwd=temp_dir, check=True)
    
    print(f"Successfully pushed to {repo_url}")
    return repo_url

def main():
    # Get environment variables
    hf_token = os.environ.get("HF_TOKEN")
    hf_username = os.environ.get("HF_USERNAME")
    
    if not hf_token or not hf_username:
        print("Error: HF_TOKEN and HF_USERNAME environment variables must be set")
        sys.exit(1)
    
    # Get repository name from GitHub repository or current directory
    github_repo = os.environ.get("GITHUB_REPOSITORY")
    if github_repo:
        repo_name = github_repo.split("/")[-1]
    else:
        repo_name = os.path.basename(os.getcwd())
    
    print(f"Repository name: {repo_name}")
    
    # Configure git for Hugging Face
    configure_git_for_hf()
    
    # Create Hugging Face space
    if not create_hf_space(repo_name, hf_token):
        print("Error creating Hugging Face space")
        sys.exit(1)
    
    # Sync repository to Hugging Face
    repo_url = sync_repo_to_hf(os.getcwd(), repo_name, hf_token)
    print(f"Hugging Face Space URL: {repo_url}")

if __name__ == "__main__":
    main() 