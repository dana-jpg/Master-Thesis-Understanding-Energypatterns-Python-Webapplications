"""
Git repository handler for cloning and managing repositories.
"""
import os
import re
import shutil
from pathlib import Path
from typing import Optional, Tuple
import subprocess


class GitHandler:
    def __init__(self, repos_dir: str = "./repos"):
        """Initialize Git handler with a directory for storing cloned repos."""
        self.repos_dir = Path(repos_dir)
        self.repos_dir.mkdir(exist_ok=True)
    
    def parse_git_url(self, url: str) -> Tuple[str, str, str]:
        """
        Parse a Git URL to extract provider, owner, and repo name.
        
        Supports:
        - https://github.com/owner/repo
        - https://github.com/owner/repo.git
        - https://gitlab.com/owner/repo
        - git@github.com:owner/repo.git
        
        Returns:
            Tuple of (provider, owner, repo_name)
        """
        # Remove .git suffix if present
        url = url.rstrip('/')
        if url.endswith('.git'):
            url = url[:-4]
        
        # Match HTTPS URLs
        https_pattern = r'https?://([^/]+)/([^/]+)/([^/]+)'
        match = re.match(https_pattern, url)
        if match:
            provider = match.group(1)
            owner = match.group(2)
            repo_name = match.group(3)
            return provider, owner, repo_name
        
        # Match SSH URLs
        ssh_pattern = r'git@([^:]+):([^/]+)/(.+)'
        match = re.match(ssh_pattern, url)
        if match:
            provider = match.group(1)
            owner = match.group(2)
            repo_name = match.group(3)
            return provider, owner, repo_name
        
        raise ValueError(f"Invalid Git URL format: {url}")
    
    def get_repo_path(self, url: str) -> Path:
        """Get the local path where the repository should be stored."""
        try:
            provider, owner, repo_name = self.parse_git_url(url)
            return self.repos_dir / provider / owner / repo_name
        except ValueError:
            # Fallback: use hash of URL
            import hashlib
            hash_name = hashlib.md5(url.encode()).hexdigest()[:12]
            return self.repos_dir / f"repo_{hash_name}"
    
    def clone_or_update(
        self, 
        repo_url: str, 
        branch: Optional[str] = None,
        progress_callback=None
    ) -> str:
        """
        Clone a repository or update it if it already exists.
        
        Args:
            repo_url: Git repository URL
            branch: Optional branch name to checkout
            progress_callback: Optional callback function for progress updates
        
        Returns:
            Path to the local repository
        """
        repo_path = self.get_repo_path(repo_url)
        
        if repo_path.exists():
            # Repository already exists, pull updates
            if progress_callback:
                progress_callback(f"Repository exists at {repo_path}, updating...")
            
            try:
                # Fetch latest changes
                self._run_git_command(["fetch", "--all"], cwd=repo_path)
                
                # Checkout branch if specified
                if branch:
                    if progress_callback:
                        progress_callback(f"Switching to branch '{branch}'...")
                    self._run_git_command(["checkout", branch], cwd=repo_path)
                
                # Pull latest changes
                if progress_callback:
                    progress_callback("Pulling latest changes...")
                self._run_git_command(["pull"], cwd=repo_path)
                
                if progress_callback:
                    progress_callback("Repository updated successfully")
                
            except subprocess.CalledProcessError as e:
                if progress_callback:
                    progress_callback(f"Warning: Update failed, using existing repository: {e}")
        else:
            # Clone the repository
            if progress_callback:
                progress_callback(f"Cloning repository from {repo_url}...")
            
            # Create parent directories
            repo_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Clone command
            clone_cmd = ["git", "clone"]
            if branch:
                clone_cmd.extend(["-b", branch])
            clone_cmd.extend([repo_url, str(repo_path)])
            
            try:
                subprocess.run(
                    clone_cmd,
                    check=True,
                    capture_output=True,
                    text=True
                )
                if progress_callback:
                    progress_callback("Repository cloned successfully")
            except subprocess.CalledProcessError as e:
                error_msg = f"Failed to clone repository: {e.stderr}"
                if progress_callback:
                    progress_callback(error_msg)
                raise RuntimeError(error_msg)
        
        return str(repo_path)
    
    def _run_git_command(self, args: list, cwd: Path):
        """Run a git command in the specified directory."""
        cmd = ["git"] + args
        result = subprocess.run(
            cmd,
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True
        )
        return result.stdout
    
    def cleanup_repo(self, repo_url: str):
        """Remove a cloned repository."""
        repo_path = self.get_repo_path(repo_url)
        if repo_path.exists():
            shutil.rmtree(repo_path)
