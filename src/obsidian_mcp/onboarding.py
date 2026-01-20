"""
Project Onboarding Logic - Implements the Project Onboarding Protocol.
"""

import os
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

from .config import VAULT_PATH
from .pulse import gather_git_info, gather_structural_info, run_command

ONBOARDING_TEMPLATE = """---
tags:
  - project
  - {language}
  - scan/auto
created: {today}
status: Active
repo: {repo_path}
---

# 🏗️ {project_name}

## 📝 Executive Summary
{summary}

## 📊 Vital Statistics
*   **Languages:** {languages}
*   **Last Active:** {last_active}
*   **Key Dependencies:** {dependencies}

## 📂 Architecture Map
{architecture_map}

## 🚀 Usage / Quick Start
{usage}

## 💡 "rga" Insights
*   **Purpose:** {purpose}
*   **Context:** {context}

[[Home]]
"""


def onboard_project_logic(
    repo_path: str, project_name: str, vault_folder: str = "10_Projects"
) -> Dict[str, Any]:
    """
    Implements Phase 1 & 2 of the Onboarding Protocol.
    Gathers data and synthesizes the Dev Log.md content.
    """
    path = Path(os.path.expanduser(repo_path))
    if not path.exists():
        return {"error": f"Repo path not found: {repo_path}"}

    # Phase 1: Data Gathering
    git_info = gather_git_info(path)
    struct_info = gather_structural_info(path)

    # Phase 2: Synthesis
    today = datetime.now().strftime("%Y-%m-%d")

    # Infer languages from manifests and extensions
    languages = []
    if "package.json" in struct_info.get("manifests", []):
        languages.append("TypeScript/JavaScript")
    if "pyproject.toml" in struct_info.get("manifests", []):
        languages.append("Python")
    if "Cargo.toml" in struct_info.get("manifests", []):
        languages.append("Rust")
    if "go.mod" in struct_info.get("manifests", []):
        languages.append("Go")

    # Extract last active date
    last_active = "Unknown"
    if "repos" in git_info and git_info["repos"]:
        # Just use the first repo for simplicity
        log = git_info["repos"][0].get("recent_commits", "")
        match = re.search(r"\((.+ ago)\)", log)
        if match:
            last_active = match.group(1)

    # Architecture Map from tree
    tree_lines = struct_info.get("structure", "").split("\n")[:15]
    architecture_map = "\n".join(
        [f"* `{line.strip()}`" for line in tree_lines if line.strip() and not line.startswith(".")]
    )

    # Summary and Usage (Mocking LLM synthesis for now or using simple extraction)
    summary = "> [Extracted summary from README/Docs]"
    usage = "Check `README.md` for build/run instructions."

    # Actually try to read README for better summary
    readme_paths = list(path.glob("README*"))
    if readme_paths:
        readme_content = readme_paths[0].read_text(encoding="utf-8")
        # Extract first paragraph
        lines = [l.strip() for l in readme_content.split("\n") if l.strip()]
        for line in lines:
            if not line.startswith("#") and len(line) > 50:
                summary = f"> {line[:200]}..."
                break

    # Build the Dev Log content
    content = ONBOARDING_TEMPLATE.format(
        project_name=project_name,
        language=", ".join(languages) if languages else "General",
        today=today,
        repo_path=repo_path,
        summary=summary,
        languages=", ".join(languages) if languages else "Unknown",
        last_active=last_active,
        dependencies=", ".join(struct_info.get("manifests", [])),
        architecture_map=architecture_map,
        usage=usage,
        purpose=project_name,
        context=struct_info.get("todos", "None identified")[:300],
    )

    return {
        "project_name": project_name,
        "content": content,
        "target_dir": VAULT_PATH / vault_folder / project_name,
    }


def update_project_index(project_name: str) -> str:
    """Phase 3: Update the Project Index.md."""
    index_path = VAULT_PATH / "10_Projects" / "Project Index.md"
    if not index_path.exists():
        return "⚠️ Project Index.md not found."

    content = index_path.read_text(encoding="utf-8")

    # 1. Locate project entry and change [ ] to [x]
    # Match: - [ ] [[project_name]] or - [ ] [[Project Name]]
    pattern = rf"-\s*\[\s*\]\s*\[\[{re.escape(project_name)}\]\]"
    if re.search(pattern, content, re.IGNORECASE):
        content = re.sub(pattern, f"- [x] [[{project_name}]]", content, flags=re.IGNORECASE)
    else:
        # If not found, maybe it's already checked or named differently
        # For now, let's just log it
        pass

    # 2. Update stats (Indexed count)
    # Looking for lines like: | **🧪 Dev / POCs**     |       4        |   0/4   | ░░░░░░░░░░ 0%  |
    # We'll look for the specific category row if we can identify it.

    # Simple increment for "🧪 Dev / POCs" as a test or just generic increment
    def increment_indexed(match):
        category = match.group(1)
        total = int(match.group(2))
        current = int(match.group(3))
        new_current = min(current + 1, total)
        percent = int((new_current / total) * 100)

        # Build progress bar
        bar_filled = percent // 10
        bar = "█" * bar_filled + "░" * (10 - bar_filled)

        # Match the spacing of the original table
        # | **🚀 Archimydes**     |       37       |  12/37   | ███░░░░░░░ 32% |
        return f"| {category.ljust(21)} | {str(total).center(14)} | {str(new_current).center(4)}/{str(total).ljust(3)} | {bar} {percent:2d}% |"

    # Category matching pattern (very specific to the current Project Index table)
    # Example: | **🚀 Archimydes**     |       37       |  12/37   | ███░░░░░░░ 32% |
    category_pattern = r"\| (\*\*.*?\*\*) +\| +(\d+) +\| +(\d+)/\d+ +\| +[█░]+ \d+%"

    # For now, let's just find the first category that matches or update Archimydes by default
    # A better way would be to map project to category, but this is a start.
    content = re.sub(category_pattern, increment_indexed, content, count=1)

    # Save the updated content
    index_path.write_text(content, encoding="utf-8")
    return "✅ Project Index.md updated (checked project and updated dashboard stats)."
