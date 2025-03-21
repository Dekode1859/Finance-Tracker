#!/usr/bin/env python3
"""
Test the HuggingFace sync script locally.
This lets you verify the script works before pushing to GitHub.

Usage:
1. Set the HF_TOKEN and HF_USERNAME environment variables
2. Run this script: python scripts/test_sync_locally.py
"""

import os
import sys
import subprocess

def check_requirements():
    """Check that all required environment variables are set."""
    required_vars = ["HF_TOKEN", "HF_USERNAME"]
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        print(f"Error: The following environment variables are required but not set: {', '.join(missing_vars)}")
        print("\nPlease set them before running this script. For example:")
        print("  export HF_TOKEN=your_token_here")
        print("  export HF_USERNAME=your_username_here")
        return False
    
    return True

def test_sync():
    """Run the sync_to_huggingface.py script with appropriate environment variables."""
    # Get the absolute path to the repo root directory
    repo_root = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], 
        text=True
    ).strip()
    
    # Check if the sync script exists
    sync_script_path = os.path.join(repo_root, "scripts", "sync_to_huggingface.py")
    if not os.path.exists(sync_script_path):
        print(f"Error: Sync script not found at {sync_script_path}")
        print("Please make sure the script exists and you're running this from within the git repository.")
        return False
    
    # Run the sync script
    print("Running sync script...")
    try:
        subprocess.run(
            [sys.executable, sync_script_path],
            check=True,
            env=os.environ
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error running sync script: {e}")
        return False

if __name__ == "__main__":
    if not check_requirements():
        sys.exit(1)
    
    print("Environment variables look good, running sync script...")
    if test_sync():
        print("\n✅ Sync test completed successfully!")
        print("Your HuggingFace Space should be created/updated.")
    else:
        print("\n❌ Sync test failed.")
        sys.exit(1) 