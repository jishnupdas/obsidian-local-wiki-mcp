"""
Gap Analysis Module - Identifies broken links, stubs, and orphans.
"""

import re
from pathlib import Path
from typing import Dict, List, Set, Any
from datetime import datetime

from .config import VAULT_PATH
from .db import get_db
from .indexer import extract_wikilinks


def find_broken_links() -> List[Dict[str, str]]:
    """
    Scan all markdown files for wikilinks that point to non-existent files.
    """
    broken = []

    # 1. Build set of all existing note names (without path/extension)
    # This is an approximation as Obsidian resolves links flexibly
    existing_notes = set()
    for f in VAULT_PATH.glob("**/*.md"):
        existing_notes.add(f.stem)
        existing_notes.add(f.name)  # Also track full filename

    # 2. Scan content
    for fpath in VAULT_PATH.glob("**/*.md"):
        try:
            content = fpath.read_text(encoding="utf-8")
            links = extract_wikilinks(content)

            for link in links:
                # Handle [[Link|Alias]] -> Link
                target = link.split("|")[0].split("#")[0]

                # Check if target exists
                # Simple check: is 'target' in our set of stems?
                # Obsidian matching is complex (case-insensitive usually, partial paths)
                # We'll do a loose match for now.

                found = False
                if target in existing_notes:
                    found = True
                else:
                    # Try case-insensitive
                    target_lower = target.lower()
                    for note in existing_notes:
                        if note.lower() == target_lower:
                            found = True
                            break

                if not found:
                    broken.append(
                        {
                            "source": str(fpath.relative_to(VAULT_PATH)),
                            "target": target,
                            "context": "WikiLink",
                        }
                    )

        except Exception:
            continue

    return broken


def find_stub_notes(min_length: int = 200) -> List[Dict[str, Any]]:
    """
    Find notes that are too short to be useful (stubs).
    Excludes templates and daily notes if needed.
    """
    stubs = []

    for fpath in VAULT_PATH.glob("**/*.md"):
        # Skip templates
        if "99_System/Templates" in str(fpath):
            continue

        try:
            content = fpath.read_text(encoding="utf-8")
            # Strip frontmatter for length check
            body = re.sub(r"^---\n.*?\n---\n", "", content, flags=re.DOTALL)

            if len(body.strip()) < min_length:
                stubs.append(
                    {"path": str(fpath.relative_to(VAULT_PATH)), "length": len(body.strip())}
                )
        except Exception:
            continue

    return sorted(stubs, key=lambda x: x["length"])


def find_orphans() -> List[str]:
    """
    Find notes that have zero backlinks.
    Uses the SQLite graph.
    """
    with get_db() as conn:
        # Get all notes
        all_notes = {
            row["filename"] for row in conn.execute("SELECT filename FROM notes").fetchall()
        }

        # Get all targets (notes that are linked TO)
        linked_notes = {
            row["target"] for row in conn.execute("SELECT target FROM edges").fetchall()
        }

        orphans = list(all_notes - linked_notes)

    return sorted(orphans)


def analyze_gaps_logic(project_name: str | None = None) -> str:
    """
    Perform gap analysis and generate a report.
    If project_name is provided, filters results to that folder.
    """
    broken_links = find_broken_links()
    stubs = find_stub_notes()
    orphans = find_orphans()

    # Filter if project specified
    if project_name:
        broken_links = [b for b in broken_links if project_name in b["source"]]
        stubs = [s for s in stubs if project_name in s["path"]]
        # Orphans filtering is harder as we only have filename, not path in DB typically
        # But we can try matching filename

    # Generate Report
    lines = [
        f"# 🕵️ Gap Analysis Report",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d')}",
        f"**Scope:** {project_name if project_name else 'Entire Vault'}",
        "",
        f"## 🔗 Broken Links ({len(broken_links)})",
        "Links pointing to non-existent notes. These are high-value research opportunities.",
        "",
    ]

    if broken_links:
        lines.append("| Source Note | Dead Link |")
        lines.append("|---|---|")
        for b in broken_links[:20]:  # Limit output
            lines.append(f"| `[[{b['source']}]]` | `[[{b['target']}]]` |")
        if len(broken_links) > 20:
            lines.append(f"\n*(...and {len(broken_links) - 20} more)*")
    else:
        lines.append("✅ No broken links found.")

    lines.append("")
    lines.append(f"## 📝 Stub Notes ({len(stubs)})")
    lines.append("Notes with < 200 characters of content. Candidates for expansion or deletion.")
    lines.append("")

    if stubs:
        lines.append("| Note | Length |")
        lines.append("|---|---|")
        for s in stubs[:20]:
            lines.append(f"| `[[{s['path']}]]` | {s['length']} chars |")
    else:
        lines.append("✅ No stubs found.")

    lines.append("")
    lines.append(f"## 🏝️ Orphans ({len(orphans)})")
    lines.append("Notes not linked from anywhere else.")
    lines.append("")

    if orphans:
        for o in orphans[:20]:
            lines.append(f"- [[{o}]]")
    else:
        lines.append("✅ No orphans found.")

    return "\n".join(lines)
