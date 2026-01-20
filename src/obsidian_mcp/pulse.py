"""
Pulse Scan - Gathers project activity from Git, GitHub, and Jira.
"""

import subprocess
import os
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List


def run_command(cmd: list, cwd: Optional[Path] = None, timeout: int = 15) -> str:
    """Run a shell command and return output."""
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        if result.returncode == 0:
            return result.stdout.strip()
        return f"Error: {result.stderr.strip()}"
    except Exception as e:
        return f"Exception: {str(e)}"


def gather_git_info(repo_path: Path) -> Dict[str, Any]:
    """Gather git status and recent commits from a repo or its subdirectories."""
    repos = []

    # Check if the path itself is a repo
    if (repo_path / ".git").exists():
        repos.append(repo_path)
    else:
        # Check subdirectories (1 level deep)
        if repo_path.exists():
            for item in repo_path.iterdir():
                if item.is_dir() and (item / ".git").exists():
                    repos.append(item)

    if not repos:
        return {"error": "No git repositories found in path"}

    repo_data = []
    for r in repos:
        name = r.name if r != repo_path else "root"
        branch = run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=r)
        status = run_command(["git", "status", "--porcelain"], cwd=r)
        log = run_command(["git", "log", "-3", "--pretty=format:%h - %s (%cr)"], cwd=r)
        repo_data.append(
            {
                "name": name,
                "branch": branch,
                "dirty": bool(status),
                "status_summary": status,
                "recent_commits": log,
            }
        )

    return {"repos": repo_data}


def gather_structural_info(repo_path: Path) -> Dict[str, Any]:
    """Gather structural context based on the Project Onboarding Protocol."""
    if not repo_path.exists():
        return {"error": "Path does not exist"}

    # 1. Structure (Tree)
    structure = run_command(
        [
            "tree",
            "-L",
            "2",
            "-I",
            ".git|node_modules|__pycache__|env|venv|target|dist",
            "--dirsfirst",
        ],
        cwd=repo_path,
    )
    if structure.startswith("Exception") or structure.startswith("Error"):
        # Fallback to find
        structure = run_command(
            ["find", ".", "-maxdepth", "2", "-not", "-path", "*/.*"], cwd=repo_path
        )

    # 2. Key Files
    manifest_files = [
        "package.json",
        "requirements.txt",
        "Cargo.toml",
        "go.mod",
        "docker-compose.yml",
        "Makefile",
        "CMakeLists.txt",
        "pyproject.toml",
    ]
    found_manifests = []
    for f in manifest_files:
        if (repo_path / f).exists():
            found_manifests.append(f)

    # 3. Context Mining (rg)
    todos = run_command(
        [
            "rg",
            "-i",
            "TODO|FIXME|hack",
            ".",
            "--glob",
            "!{node_modules,dist,build,vendor,.git}",
            "--max-count",
            "5",
        ],
        cwd=repo_path,
    )
    architecture = run_command(
        [
            "rg",
            "-i",
            "architecture|design pattern|interface|adapter",
            ".",
            "--glob",
            "!{node_modules,dist,build,vendor,.git}",
            "--max-count",
            "5",
        ],
        cwd=repo_path,
    )

    # 4. Documentation (rga if available, else rg)
    # Check if rga is installed
    has_rga = run_command(["which", "rga"])
    if not has_rga.startswith("Error") and not has_rga.startswith("Exception"):
        docs = run_command(
            [
                "rga",
                "-i",
                "overview|goal|purpose|abstract|introduction",
                ".",
                "--glob",
                "*.{md,pdf,txt}",
                "--max-count",
                "5",
            ],
            cwd=repo_path,
        )
    else:
        docs = run_command(
            [
                "rg",
                "-i",
                "overview|goal|purpose|abstract|introduction",
                ".",
                "--glob",
                "*.{md,txt}",
                "--max-count",
                "5",
            ],
            cwd=repo_path,
        )

    return {
        "structure": structure,
        "manifests": found_manifests,
        "todos": todos,
        "architecture": architecture,
        "docs": docs,
    }


def gather_github_info(github_repo: str) -> Dict[str, Any]:
    """Gather PRs and Issues from GitHub."""
    prs_raw = run_command(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            github_repo,
            "--limit",
            "5",
            "--json",
            "number,title,author,updatedAt",
        ]
    )
    issues_raw = run_command(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            github_repo,
            "--limit",
            "5",
            "--json",
            "number,title,updatedAt",
        ]
    )

    try:
        prs = json.loads(prs_raw) if not prs_raw.startswith("Error") else []
    except:
        prs = []

    try:
        issues = json.loads(issues_raw) if not issues_raw.startswith("Error") else []
    except:
        issues = []

    return {"prs": prs, "issues": issues, "repo": github_repo}


def gather_jira_info(project_key: str) -> Dict[str, Any]:
    """Gather active Jira tickets."""
    jql = f"project = {project_key} AND status != Done ORDER BY updated DESC"
    raw_tickets = run_command(["acli", "jira", "workitem", "search", "--jql", jql, "--json"])

    try:
        tickets = json.loads(raw_tickets) if not raw_tickets.startswith("Error") else []
    except:
        tickets = []

    return {"tickets": tickets, "project": project_key}


def format_pulse_markdown(project_name: str, data: Dict[str, Any]) -> str:
    """Format gathered data into a nice markdown note."""
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        f"---",
        f"tags:",
        f"  - pulse",
        f"  - scan/auto",
        f"  - project/{project_name.lower().replace(' ', '-')}",
        f"created: {now.strftime('%Y-%m-%d')}",
        f"---",
        f"",
        f"# ⚡ Pulse Scan: {project_name}",
        f"**Date:** {today_str}",
        f"",
    ]

    # Git
    git = data.get("git", {})
    lines.append("## 💻 Local Activity (Git)")
    if "error" in git:
        lines.append(f"⚠️ {git['error']}")
    else:
        for repo in git.get("repos", []):
            lines.append(f"### 📁 {repo['name']}")
            lines.append(f"- **Branch:** `{repo['branch']}`")
            lines.append(f"- **Status:** {'🔴 Dirty' if repo['dirty'] else '🟢 Clean'}")
            if repo["dirty"]:
                lines.append("```")
                lines.append(repo["status_summary"])
                lines.append("```")

            if repo["recent_commits"]:
                lines.append("\n**Recent Commits:**")
                lines.append("```")
                lines.append(repo["recent_commits"])
                lines.append("```")
            lines.append("")

    # Structural Info
    structure = data.get("structure", {})
    if structure and "error" not in structure:
        lines.append("## 🏗️ Codebase Structure")
        lines.append("```")
        lines.append(structure.get("structure", ""))
        lines.append("```")

        if structure.get("manifests"):
            lines.append(
                "\n**Key Files Found:** " + ", ".join([f"`{m}`" for m in structure["manifests"]])
            )

        if structure.get("todos") and not structure["todos"].startswith("Error"):
            lines.append("\n**TODOs & Markers:**")
            lines.append("```")
            lines.append(structure["todos"])
            lines.append("```")

        if structure.get("architecture") and not structure["architecture"].startswith("Error"):
            lines.append("\n**Architectural Hints:**")
            lines.append("```")
            lines.append(structure["architecture"])
            lines.append("```")

            lines.append("```")

        if structure.get("docs") and not structure["docs"].startswith("Error"):
            lines.append("\n**Documentation Insights:**")
            lines.append("```")
            lines.append(structure["docs"])
            lines.append("```")
        lines.append("")

    # GitHub
    gh = data.get("github", {})
    if gh and (gh.get("prs") or gh.get("issues")):
        lines.append(f"## 🐙 GitHub: {gh['repo']}")

        if gh.get("prs"):
            lines.append("### Open PRs")
            lines.append("| # | Title | Author | Updated |")
            lines.append("|---|-------|--------|---------|")
            for pr in gh["prs"]:
                author = pr.get("author", {}).get("login", "unknown")
                updated = pr.get("updatedAt", "").split("T")[0]
                lines.append(f"| {pr['number']} | {pr['title']} | {author} | {updated} |")

        if gh.get("issues"):
            lines.append("\n### Recent Issues")
            lines.append("| # | Title | Updated |")
            lines.append("|---|-------|---------|")
            for issue in gh["issues"]:
                updated = issue.get("updatedAt", "").split("T")[0]
                lines.append(f"| {issue['number']} | {issue['title']} | {updated} |")
        lines.append("")

    # Jira
    jira = data.get("jira", {})
    if jira and jira.get("tickets"):
        lines.append(f"## 🎫 Jira Project: {jira['project']}")
        lines.append("| Key | Summary | Status | Priority |")
        lines.append("|-----|---------|--------|----------|")
        for t in jira["tickets"]:
            fields = t.get("fields", {})
            summary = fields.get("summary", "No summary")
            status = fields.get("status", {}).get("name", "Unknown")
            priority = fields.get("priority", {}).get("name", "Normal")
            lines.append(
                f"| [{t['key']}](https://accurkardia.atlassian.net/browse/{t['key']}) | {summary} | `{status}` | {priority} |"
            )
        lines.append("")

    return "\n".join(lines)
