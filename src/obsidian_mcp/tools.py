"""
MCP Tool Implementations for Obsidian Second Brain.

The Toolbox: Read/write operations for vault manipulation.
- Readers: search_vault, read_note, find_related_notes, vault_stats
- Writers: create_note, edit_note, apply_wikilink, append_to_daily (require --force for automation)
"""

import subprocess
import re
from pathlib import Path
from datetime import datetime

from .config import (
    VAULT_PATH,
    TEMPLATES,
    JOURNAL_FOLDER,
    JOURNAL_DATE_FORMAT,
)
from .db import (
    search_fts,
    search_edges,
    get_connections,
    get_stats,
    get_orphan_notes,
    get_most_connected,
)


# =============================================================================
# HELPERS
# =============================================================================


def _read_template(template_type: str) -> str | None:
    """Read a template file from the vault."""
    template_rel = TEMPLATES.get(template_type)
    if not template_rel:
        return None

    template_path = VAULT_PATH / template_rel
    if template_path.exists():
        try:
            return template_path.read_text(encoding="utf-8")
        except Exception:
            return None
    return None


def _apply_template_vars(template: str, **kwargs) -> str:
    """Apply variables to template ({{var}} syntax)."""
    result = template
    for key, value in kwargs.items():
        result = result.replace(f"{{{{{key}}}}}", str(value))
    return result


def _find_note_path(filename: str) -> Path | None:
    """Find a note by filename in the vault."""
    if not filename.endswith(".md"):
        filename += ".md"

    matches = list(VAULT_PATH.glob(f"**/{filename}"))

    # Filter out excluded paths
    matches = [m for m in matches if ".obsidian" not in str(m)]

    if len(matches) == 1:
        return matches[0]
    return None


def _find_all_note_paths(filename: str) -> list[Path]:
    """Find all notes matching filename."""
    if not filename.endswith(".md"):
        filename += ".md"

    matches = list(VAULT_PATH.glob(f"**/{filename}"))
    return [m for m in matches if ".obsidian" not in str(m)]


# =============================================================================
# TOOL 1: SEARCH VAULT (Hybrid)
# =============================================================================


def search_vault(
    query: str, include_graph: bool = True, include_fts: bool = True, limit: int = 10
) -> str:
    """
    Hybrid search across vault: ripgrep text matches + SQLite FTS + knowledge graph.

    Args:
        query: Search term or phrase
        include_graph: Include knowledge graph connections
        include_fts: Include full-text search results
        limit: Max results per category

    Returns:
        Formatted search results with file paths and context
    """
    results = []

    # 1. Ripgrep for exact text matches (fastest)
    try:
        rg_cmd = [
            "rg",
            "-i",  # Case insensitive
            "-n",  # Line numbers
            "--no-heading",  # No file headers
            "-C",
            "1",  # 1 line context
            "--max-count",
            "3",  # Max 3 matches per file
            "--max-filesize",
            "1M",  # Skip large files
            query,
            str(VAULT_PATH),
        ]
        rg_result = subprocess.run(rg_cmd, capture_output=True, text=True, timeout=10)

        if rg_result.stdout:
            lines = rg_result.stdout.strip().split("\n")
            # Clean up paths to be relative
            cleaned = []
            for line in lines[: limit * 3]:
                if str(VAULT_PATH) in line:
                    line = line.replace(str(VAULT_PATH) + "/", "")
                cleaned.append(line)

            if cleaned:
                results.append("=== TEXT MATCHES (ripgrep) ===")
                results.extend(cleaned[:20])
    except subprocess.TimeoutExpired:
        results.append("[ripgrep: timeout]")
    except FileNotFoundError:
        results.append("[ripgrep: not installed]")
    except Exception as e:
        results.append(f"[ripgrep error: {e}]")

    # 2. SQLite FTS for semantic matches
    if include_fts:
        try:
            fts_results = search_fts(query, limit)
            if fts_results:
                results.append("\n=== FTS MATCHES ===")
                for row in fts_results:
                    snippet = row.get("snippet", "")[:100]
                    results.append(f"- {row['filename']}: {snippet}")
        except Exception as e:
            results.append(f"[FTS error: {e}]")

    # 3. Knowledge graph connections
    if include_graph:
        try:
            edges = search_edges(query, limit)
            if edges:
                results.append("\n=== GRAPH CONNECTIONS ===")
                for e in edges:
                    claim = f" — {e['claim'][:60]}..." if e.get("claim") else ""
                    results.append(f"- {e['source']} --[{e['relation']}]--> {e['target']}{claim}")
        except Exception as e:
            results.append(f"[Graph error: {e}]")

    if not results:
        return f"No results found for '{query}'."

    return "\n".join(results)


# =============================================================================
# TOOL 2: READ NOTE
# =============================================================================


def read_note(filename: str, max_lines: int = 500) -> str:
    """
    Read full content of a specific note.

    Args:
        filename: Note filename (with or without .md extension)
        max_lines: Maximum lines to return (safety limit)

    Returns:
        Note content with path, or error message
    """
    if not filename.endswith(".md"):
        filename += ".md"

    matches = _find_all_note_paths(filename)

    if not matches:
        return f"❌ Note '{filename}' not found in vault."

    if len(matches) > 1:
        paths = [str(m.relative_to(VAULT_PATH)) for m in matches]
        return (
            f"⚠️ Multiple notes named '{filename}' found:\n"
            + "\n".join(f"  - {p}" for p in paths)
            + "\n\nSpecify the full path or folder to disambiguate."
        )

    note_path = matches[0]

    try:
        content = note_path.read_text(encoding="utf-8")
        lines = content.split("\n")

        rel_path = note_path.relative_to(VAULT_PATH)

        if len(lines) > max_lines:
            content = "\n".join(lines[:max_lines])
            content += f"\n\n... [Truncated at {max_lines} lines, total: {len(lines)}]"

        return f"📄 {rel_path}\n\n{content}"

    except Exception as e:
        return f"❌ Error reading note: {e}"


# =============================================================================
# TOOL 3: FIND RELATED NOTES
# =============================================================================


def find_related_notes(note_name: str) -> str:
    """
    Get all connections for a note from the knowledge graph.

    Args:
        note_name: Note filename or concept name

    Returns:
        Formatted list of outlinks, backlinks, and relationships
    """
    # Normalize variants
    search_names = [note_name]
    if note_name.endswith(".md"):
        search_names.append(note_name[:-3])
    else:
        search_names.append(note_name + ".md")

    results = []
    seen_out = set()
    seen_back = set()

    for name in search_names:
        connections = get_connections(name)

        for link in connections["outlinks"]:
            key = (link["target"], link["relation"])
            if key not in seen_out:
                seen_out.add(key)
                claim = f" — {link['claim'][:50]}..." if link.get("claim") else ""
                results.append(f"  → [{link['relation']}] {link['target']}{claim}")

        for link in connections["backlinks"]:
            key = (link["source"], link["relation"])
            if key not in seen_back:
                seen_back.add(key)
                claim = f" — {link['claim'][:50]}..." if link.get("claim") else ""
                results.append(f"  ← [{link['relation']}] {link['source']}{claim}")

    if not results:
        # Fallback: ripgrep for [[WikiLinks]]
        try:
            clean_name = note_name.replace(".md", "")
            rg_cmd = ["rg", "-l", f"\\[\\[{clean_name}", str(VAULT_PATH)]
            rg_result = subprocess.run(rg_cmd, capture_output=True, text=True, timeout=5)
            if rg_result.stdout:
                results.append("=== BACKLINKS (via ripgrep) ===")
                for path in rg_result.stdout.strip().split("\n")[:15]:
                    results.append(f"  ← {Path(path).name}")
        except Exception:
            pass

    if not results:
        return f"No connections found for '{note_name}'."

    header = f"=== CONNECTIONS for '{note_name}' ===\n"
    return header + "\n".join(results)


# =============================================================================
# TOOL 4: CREATE NOTE
# =============================================================================


def create_note(
    filename: str,
    content: str | None = None,
    folder: str = "",
    template: str = "concept",
    title: str | None = None,
    force: bool = False,
) -> str:
    """
    Create a NEW markdown note with proper frontmatter.

    Args:
        filename: Note filename (e.g., 'Agent_Memory.md')
        content: Note body content (uses template if not provided)
        folder: Target folder relative to vault (e.g., '30_Resources/Concepts')
        template: Template type: concept, bridge, daily, project, ticket, web_clip
        title: Note title (defaults to filename-derived)
        force: Skip confirmation (for automation)

    Returns:
        Success message or error
    """
    if not filename.endswith(".md"):
        filename += ".md"

    target_dir = VAULT_PATH / folder if folder else VAULT_PATH
    target_path = target_dir / filename

    # Check existence
    if target_path.exists():
        return (
            f"❌ File already exists: {target_path.relative_to(VAULT_PATH)}\n"
            f"Use a different filename or delete the existing file first."
        )

    # Build content
    if content is None:
        template_content = _read_template(template)
        note_title = title or filename.replace(".md", "").replace("_", " ").replace("-", " ")
        today = datetime.now().strftime("%Y-%m-%d")

        if template_content:
            content = _apply_template_vars(template_content, title=note_title, date=today, repo="")
        else:
            # Minimal fallback template
            content = f"""---
tags:
  - {template}
created: {today}
status: Draft
---
# {note_title}

"""

    # Show preview if not forced
    if not force:
        preview = content[:400] + "..." if len(content) > 400 else content
        return f"""⚠️ PREVIEW (use --force or force=True to create)

**Path:** {target_path.relative_to(VAULT_PATH)}
**Template:** {template}

```markdown
{preview}
```

To create this note, call again with force=True"""

    # Execute creation
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")
        return f"✅ Note created: {target_path.relative_to(VAULT_PATH)}"
    except Exception as e:
        return f"❌ Error creating note: {e}"


# =============================================================================
# TOOL 5: EDIT NOTE
# =============================================================================


def edit_note(
    filename: str,
    old_text: str | None = None,
    new_text: str | None = None,
    section: str | None = None,
    section_content: str | None = None,
    append_to_section: bool = False,
    force: bool = False,
) -> str:
    """
    Edit an existing note with precise text replacement or section updates.

    Two modes of operation:
    1. **Text replacement**: Provide old_text and new_text to replace specific content
    2. **Section update**: Provide section and section_content to update/append to a section

    Args:
        filename: The note to edit (with or without .md extension)
        old_text: Text to find and replace (for replacement mode)
        new_text: Replacement text (for replacement mode)
        section: Section header to update (e.g., "## Summary" or "Summary")
        section_content: New content for the section (replaces or appends based on append_to_section)
        append_to_section: If True, append to section instead of replacing it
        force: Skip confirmation (for automation)

    Returns:
        Success message, preview, or error
    """
    if not filename.endswith(".md"):
        filename += ".md"

    note_path = _find_note_path(filename)

    if not note_path:
        matches = _find_all_note_paths(filename)
        if matches:
            return f"⚠️ Multiple files named '{filename}' found:\n" + "\n".join(
                f"  - {m.relative_to(VAULT_PATH)}" for m in matches
            )
        return f"❌ File '{filename}' not found in vault."

    try:
        content = note_path.read_text(encoding="utf-8")
    except Exception as e:
        return f"❌ Error reading note: {e}"

    # Determine edit mode
    is_text_replace = old_text is not None and new_text is not None
    is_section_update = section is not None and section_content is not None

    if not is_text_replace and not is_section_update:
        return (
            "❌ Invalid arguments. Provide either:\n"
            "  - old_text AND new_text (for text replacement)\n"
            "  - section AND section_content (for section update)"
        )

    if is_text_replace and is_section_update:
        return "❌ Cannot use both text replacement and section update at the same time."

    # === MODE 1: Text Replacement ===
    if is_text_replace:
        assert old_text is not None and new_text is not None  # Type narrowing

        if old_text not in content:
            # Try to find similar text for helpful error
            lines_with_similar = []
            for i, line in enumerate(content.split("\n"), 1):
                if old_text[:20].lower() in line.lower():
                    lines_with_similar.append(f"  Line {i}: {line[:80]}...")

            hint = ""
            if lines_with_similar:
                hint = "\n\nDid you mean one of these?\n" + "\n".join(lines_with_similar[:3])

            return f"⚠️ Text not found in '{filename}':\n  `{old_text[:100]}...`{hint}"

        count = content.count(old_text)
        new_content = content.replace(old_text, new_text)

        if not force:
            # Show diff-like preview
            old_preview = old_text[:200] + "..." if len(old_text) > 200 else old_text
            new_preview = new_text[:200] + "..." if len(new_text) > 200 else new_text

            return f"""⚠️ PREVIEW (use force=True to apply)

**File:** {note_path.relative_to(VAULT_PATH)}
**Occurrences:** {count}

**Replace:**
```
{old_preview}
```

**With:**
```
{new_preview}
```

To apply this change, call again with force=True"""

        # Execute replacement
        try:
            note_path.write_text(new_content, encoding="utf-8")
            return f"✅ Replaced {count} occurrence(s) in {filename}"
        except Exception as e:
            return f"❌ Error writing note: {e}"

    # === MODE 2: Section Update ===
    if is_section_update:
        assert section is not None and section_content is not None  # Type narrowing

        # Normalize section header (ensure it starts with ##)
        section_header = section if section.startswith("#") else f"## {section}"
        section_level = len(section_header) - len(section_header.lstrip("#"))
        section_name = section_header.lstrip("#").strip()

        # Build regex to find section (handles ## or ### etc)
        # Match from section header to next same-or-higher level header or EOF
        pattern = re.compile(
            rf"^({'#' * section_level}\s+{re.escape(section_name)}.*?)(?=\n{'#' * section_level}\s|\n{'#' * (section_level - 1)}\s|\Z)",
            re.MULTILINE | re.DOTALL | re.IGNORECASE,
        )

        match = pattern.search(content)

        if not match:
            # Section doesn't exist - offer to create it
            if not force:
                return f"""⚠️ Section '{section_name}' not found in '{filename}'.

To create this section, you could:
1. Use create mode by appending to the end of the file
2. Manually add the section header first

Available sections in this note:
{_list_sections(content)}"""

            # In force mode, append section at end
            new_section = f"\n\n{section_header}\n\n{section_content}\n"
            new_content = content.rstrip() + new_section
        else:
            existing_section = match.group(1)
            section_header_line = existing_section.split("\n")[0]

            if append_to_section:
                # Append to existing section content
                new_section = existing_section.rstrip() + "\n\n" + section_content + "\n"
            else:
                # Replace section content (keep header)
                new_section = f"{section_header_line}\n\n{section_content}\n"

            new_content = content[: match.start()] + new_section + content[match.end() :]

        if not force:
            action = "Append to" if append_to_section else "Replace"
            preview = (
                section_content[:300] + "..." if len(section_content) > 300 else section_content
            )

            return f"""⚠️ PREVIEW (use force=True to apply)

**File:** {note_path.relative_to(VAULT_PATH)}
**Action:** {action} section '{section_name}'

**New content:**
```markdown
{preview}
```

To apply this change, call again with force=True"""

        # Execute section update
        try:
            note_path.write_text(new_content, encoding="utf-8")
            action = "Appended to" if append_to_section else "Updated"
            return f"✅ {action} section '{section_name}' in {filename}"
        except Exception as e:
            return f"❌ Error writing note: {e}"

    return "❌ Unexpected error in edit_note"


def _list_sections(content: str) -> str:
    """List all section headers in content."""
    sections = re.findall(r"^(#{1,6})\s+(.+)$", content, re.MULTILINE)
    if not sections:
        return "  (no sections found)"
    return "\n".join(f"  {'#' * len(level)} {title}" for level, title in sections[:15])


# =============================================================================
# TOOL 6: APPLY WIKILINK
# =============================================================================


def apply_wikilink(filename: str, text_to_link: str, target_note: str, force: bool = False) -> str:
    """
    Refactor a note by turning plain text into a [[WikiLink]].

    Args:
        filename: The file to edit
        text_to_link: The exact phrase to find
        target_note: The destination note name
        force: Skip confirmation (for automation)

    Returns:
        Success message or preview
    """
    if not filename.endswith(".md"):
        filename += ".md"

    note_path = _find_note_path(filename)

    if not note_path:
        matches = _find_all_note_paths(filename)
        if matches:
            return f"⚠️ Multiple files named '{filename}' found:\n" + "\n".join(
                f"  - {m.relative_to(VAULT_PATH)}" for m in matches
            )
        return f"❌ File '{filename}' not found in vault."

    content = note_path.read_text(encoding="utf-8")

    # Check if text exists
    if text_to_link not in content:
        return f"⚠️ Phrase '{text_to_link}' not found in {filename}."

    # Count occurrences
    count = content.count(text_to_link)

    # Build wikilink
    # Use piped link if text differs from target
    target_clean = target_note.replace(".md", "")
    text_normalized = text_to_link.lower().replace(" ", "_").replace("-", "_")
    target_normalized = target_clean.lower().replace(" ", "_").replace("-", "_")

    if text_normalized == target_normalized:
        replacement = f"[[{target_clean}]]"
    else:
        replacement = f"[[{target_clean}|{text_to_link}]]"

    new_content = content.replace(text_to_link, replacement)

    # Preview if not forced
    if not force:
        return f"""⚠️ PREVIEW (use --force or force=True to apply)

**File:** {note_path.relative_to(VAULT_PATH)}
**Replace:** `{text_to_link}` → `{replacement}`
**Occurrences:** {count}

To apply this change, call again with force=True"""

    # Execute replacement
    try:
        note_path.write_text(new_content, encoding="utf-8")
        return f"✅ Linked '{text_to_link}' → `{replacement}` in {filename} ({count} occurrence(s))"
    except Exception as e:
        return f"❌ Error applying wikilink: {e}"


# =============================================================================
# TOOL 6: APPEND TO DAILY
# =============================================================================


def append_to_daily(
    content: str,
    section: str = "Inbox / Quick Captures",
    topic: str | None = None,
    force: bool = False,
) -> str:
    """
    Append timestamped entry to today's daily journal note.

    Args:
        content: Content to append
        section: Section header to append under
        topic: Optional topic label for the entry
        force: Skip confirmation (for automation)

    Returns:
        Success message or preview
    """
    today = datetime.now().strftime(JOURNAL_DATE_FORMAT)
    journal_dir = VAULT_PATH / JOURNAL_FOLDER
    journal_path = journal_dir / f"{today}.md"

    timestamp = datetime.now().strftime("%H:%M")
    topic_label = f" - {topic}" if topic else ""
    entry = f"\n### {timestamp}{topic_label}\n{content}\n"

    # Check if daily note exists
    is_new = not journal_path.exists()

    if is_new:
        # Create from template
        template = _read_template("daily")
        if template:
            base_content = _apply_template_vars(template, date=today)
        else:
            base_content = f"""---
tags:
  - daily
created: {today}
---
# {today}

## Inbox / Quick Captures

"""
        final_content = base_content + entry
    else:
        existing = journal_path.read_text(encoding="utf-8")

        # Try to find section header
        section_pattern = re.compile(
            rf"^(##\s+{re.escape(section)}.*?)(?=\n##|\Z)", re.MULTILINE | re.DOTALL | re.IGNORECASE
        )
        match = section_pattern.search(existing)

        if match:
            # Insert after section header line
            section_end = match.end()
            final_content = existing[:section_end] + entry + existing[section_end:]
        else:
            # Append to end
            final_content = existing.rstrip() + "\n" + entry

    # Preview if not forced
    if not force:
        action = "Create and append to" if is_new else "Append to"
        return f"""⚠️ PREVIEW (use --force or force=True to apply)

**Action:** {action} daily note
**Path:** {JOURNAL_FOLDER}/{today}.md
**Section:** {section}

**Entry to add:**
```markdown
{entry}
```

To apply this change, call again with force=True"""

    # Execute
    try:
        journal_dir.mkdir(parents=True, exist_ok=True)
        journal_path.write_text(final_content, encoding="utf-8")
        action = "Created and appended to" if is_new else "Appended to"
        return f"✅ {action} {JOURNAL_FOLDER}/{today}.md"
    except Exception as e:
        return f"❌ Error: {e}"


# =============================================================================
# TOOL 7: VAULT STATS
# =============================================================================


def vault_stats() -> str:
    """
    Get knowledge graph statistics and health metrics.

    Returns:
        Formatted statistics including note count, edges, and top connections
    """
    stats = get_stats()
    orphans = get_orphan_notes(10)
    top_connected = get_most_connected(10)

    result = [
        "=== VAULT STATISTICS ===",
        f"📄 Total Notes:  {stats['total_notes']}",
        f"🔗 Total Edges:  {stats['total_edges']}",
        f"💡 Total Claims: {stats['total_claims']}",
        "",
    ]

    # Folder distribution
    if stats.get("folders"):
        result.append("📁 Notes by Folder:")
        for folder, count in list(stats["folders"].items())[:8]:
            result.append(f"   {folder or '(root)'}: {count}")
        result.append("")

    # Relationship distribution
    if stats.get("relations"):
        result.append("🔗 Relationship Types:")
        for rel, count in list(stats["relations"].items())[:10]:
            result.append(f"   {rel}: {count}")
        result.append("")

    # Most connected
    if top_connected:
        result.append("⭐ Most Connected:")
        for item in top_connected[:5]:
            result.append(f"   {item['name']}: {item['connections']} connections")
        result.append("")

    # Orphans
    if orphans:
        result.append(f"🏝️ Orphan Notes ({len(orphans)} found):")
        for orphan in orphans[:5]:
            result.append(f"   - {orphan}")

    return "\n".join(result)
