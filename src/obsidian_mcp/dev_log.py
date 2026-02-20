"""
Dev Log Integration Module.

Handles structured appending to Project Dev Logs and extracting action items.
"""

import re
from pathlib import Path
from datetime import datetime

from .config import VAULT_PATH

ACTIVITY_LOG_HEADER = "## 📜 Activity Log"

def append_to_dev_log(project_path: Path, content: str, title: str | None = None) -> Path:
    """
    Append an entry to the project's Dev Log.
    Create the file if it doesn't exist.
    """
    if not project_path.exists():
        project_path.mkdir(parents=True, exist_ok=True)

    log_path = project_path / "Dev Log.md"
    project_name = project_path.name
    
    today = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%H:%M")
    
    # Format the entry
    entry_header = f"### {today} - {timestamp}"
    if title:
        entry_header += f" - {title}"
        
    formatted_entry = f"\n{entry_header}\n{content}\n"

    if not log_path.exists():
        # Create new Dev Log
        initial_content = f"""---
tags: [project, dev-log]
created: {today}
repo: {project_path}
---

# 🏗️ {project_name}

{ACTIVITY_LOG_HEADER}
{formatted_entry}
"""
        log_path.write_text(initial_content, encoding="utf-8")
        return log_path

    # Read existing content
    existing_content = log_path.read_text(encoding="utf-8")
    
    # Check if section exists
    if ACTIVITY_LOG_HEADER in existing_content:
        # Append to section
        # Find the start of the section
        section_start = existing_content.find(ACTIVITY_LOG_HEADER)
        # Find the next H2 header after this section
        next_section_match = re.search(r"\n## ", existing_content[section_start + len(ACTIVITY_LOG_HEADER):])
        
        if next_section_match:
            insert_pos = section_start + len(ACTIVITY_LOG_HEADER) + next_section_match.start()
            new_content = existing_content[:insert_pos] + formatted_entry + existing_content[insert_pos:]
        else:
            # Append to end of file if no next section
            new_content = existing_content.rstrip() + "\n" + formatted_entry
    else:
        # Append section and content to end
        new_content = existing_content.rstrip() + "\n\n" + ACTIVITY_LOG_HEADER + "\n" + formatted_entry
        
    log_path.write_text(new_content, encoding="utf-8")
    return log_path

def extract_action_items(content: str) -> list[str]:
    """
    Extract TODOs and BLOCKED items from content.
    """
    items = []
    lines = content.split('\n')
    
    for line in lines:
        line = line.strip()
        # Case insensitive check
        upper_line = line.upper()
        
        if "- [ ]" in line:
            items.append(line)
        elif "TODO:" in upper_line or "TODO " in upper_line:
            # Make sure it's a list item or just a standalone line? 
            # Usually they are list items "- TODO: ..."
            # But let's capture any line with TODO
            items.append(line)
        elif "BLOCKED:" in upper_line or "BLOCKED " in upper_line:
            items.append(line)
        elif "FIXME:" in upper_line:
            items.append(line)
            
    return items
