"""
Repo Mapping Manager - Links vault folders to git repos and external systems.

This module handles loading repo_mapping.yaml and providing utilities
for the pulse scan and dev integration features.
"""

import os
import subprocess
from pathlib import Path
from typing import Optional

import yaml

from .config import VAULT_PATH
from .db import (
    init_db,
    upsert_repo_mapping,
    get_repo_mapping,
    get_repo_for_note,
    get_all_repo_mappings,
    clear_repo_mappings,
)


def get_mapping_file_path() -> Path:
    """
    Get the path to repo_mapping.yaml.

    Looks in:
    1. VAULT_PATH/99_System/AI_Context/repo_mapping.yaml
    2. Current directory (./repo_mapping.yaml)
    3. obsidian-mcp directory
    """
    candidates = [
        VAULT_PATH / "99_System" / "AI_Context" / "repo_mapping.yaml",
        Path.cwd() / "repo_mapping.yaml",
        Path(__file__).parent.parent.parent / "repo_mapping.yaml",
    ]

    for path in candidates:
        if path.exists():
            return path

    # Return default location even if doesn't exist
    return VAULT_PATH / "99_System" / "AI_Context" / "repo_mapping.yaml"


def load_mappings_from_yaml(yaml_path: Optional[Path] = None, clear_existing: bool = True) -> int:
    """
    Load repo mappings from YAML file into the database.

    Args:
        yaml_path: Path to repo_mapping.yaml (auto-detected if None)
        clear_existing: Clear existing mappings before loading

    Returns:
        Number of mappings loaded

    Raises:
        FileNotFoundError: If YAML file doesn't exist
        ValueError: If YAML is invalid
    """
    if yaml_path is None:
        yaml_path = get_mapping_file_path()

    if not yaml_path.exists():
        raise FileNotFoundError(
            f"repo_mapping.yaml not found at {yaml_path}. "
            f"Copy repo_mapping.yaml.example and customize it."
        )

    # Initialize database
    init_db()

    # Load YAML
    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f)

    if not data or "mappings" not in data:
        raise ValueError("Invalid repo_mapping.yaml: missing 'mappings' key")

    # Clear existing mappings if requested
    if clear_existing:
        clear_repo_mappings()

    # Insert mappings
    count = 0
    for mapping in data["mappings"]:
        vault_path = mapping.get("vault_path")
        if not vault_path:
            continue

        # Expand ~ in repo_path
        repo_path = mapping.get("repo_path")
        if repo_path and repo_path.startswith("~"):
            repo_path = os.path.expanduser(repo_path)

        upsert_repo_mapping(
            vault_path=vault_path,
            repo_path=repo_path,
            github_repo=mapping.get("github"),
            jira_project=mapping.get("jira_project"),
            description=mapping.get("description"),
            active=mapping.get("active", True),
        )
        count += 1

    return count


def expand_repo_path(repo_path: str) -> Path:
    """Expand ~/ and relative paths in repo path."""
    if repo_path.startswith("~"):
        return Path(os.path.expanduser(repo_path))
    return Path(repo_path).resolve()


def get_git_status(repo_path: str) -> dict:
    """
    Get git status for a repository.

    Returns:
        Dict with keys: branch, ahead, behind, dirty, untracked
    """
    path = expand_repo_path(repo_path)

    if not path.exists():
        return {"error": f"Repo not found: {path}"}

    if not (path / ".git").exists():
        return {"error": f"Not a git repo: {path}"}

    result = {
        "branch": None,
        "ahead": 0,
        "behind": 0,
        "dirty": False,
        "untracked": 0,
        "modified": 0,
        "error": None,
    }

    try:
        # Get current branch
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if branch_result.returncode == 0:
            result["branch"] = branch_result.stdout.strip()

        # Get status
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if status_result.returncode == 0:
            lines = status_result.stdout.strip().split("\n")
            result["dirty"] = len(lines) > 0 and lines[0] != ""
            result["untracked"] = sum(1 for line in lines if line.startswith("??"))
            result["modified"] = sum(1 for line in lines if line.startswith(" M"))

        # Get ahead/behind
        tracking_result = subprocess.run(
            ["git", "rev-list", "--left-right", "--count", "HEAD...@{upstream}"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if tracking_result.returncode == 0:
            parts = tracking_result.stdout.strip().split()
            if len(parts) == 2:
                result["ahead"] = int(parts[0])
                result["behind"] = int(parts[1])

    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError) as e:
        result["error"] = str(e)

    return result


def verify_mapping(mapping: dict) -> dict:
    """
    Verify a repo mapping configuration.

    Returns:
        Dict with status info
    """
    status = {
        "vault_path": mapping["vault_path"],
        "vault_exists": False,
        "repo_exists": False,
        "is_git_repo": False,
        "github_accessible": False,
        "jira_accessible": False,
        "warnings": [],
    }

    # Check vault path
    vault_full_path = VAULT_PATH / mapping["vault_path"]
    status["vault_exists"] = vault_full_path.exists()
    if not status["vault_exists"]:
        status["warnings"].append(f"Vault path not found: {vault_full_path}")

    # Check repo path
    if mapping.get("repo_path"):
        repo_path = expand_repo_path(mapping["repo_path"])
        status["repo_exists"] = repo_path.exists()
        if not status["repo_exists"]:
            status["warnings"].append(f"Repo path not found: {repo_path}")
        else:
            status["is_git_repo"] = (repo_path / ".git").exists()
            if not status["is_git_repo"]:
                status["warnings"].append(f"Not a git repo: {repo_path}")

    # Check GitHub access (basic check)
    if mapping.get("github_repo"):
        try:
            result = subprocess.run(
                ["gh", "repo", "view", mapping["github_repo"], "--json", "name"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            status["github_accessible"] = result.returncode == 0
            if not status["github_accessible"]:
                status["warnings"].append(f"Cannot access GitHub repo: {mapping['github_repo']}")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            status["warnings"].append("gh CLI not available or timed out")

    # Check Jira access (basic check)
    if mapping.get("jira_project"):
        try:
            result = subprocess.run(
                ["acli", "jira", "project", "get", "--key", mapping["jira_project"]],
                capture_output=True,
                text=True,
                timeout=5,
            )
            status["jira_accessible"] = result.returncode == 0
            if not status["jira_accessible"]:
                status["warnings"].append(f"Cannot access Jira project: {mapping['jira_project']}")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            status["warnings"].append("acli not available or timed out")

    return status
