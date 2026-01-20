"""
Knowledge Graph Indexer using Gemini CLI.

The Heartbeat: A background process that reads your vault and builds a
semantic knowledge graph by extracting claims and connections via LLM.

Supports incremental indexing (only re-processes changed files).
"""

import subprocess
import json
import re
from pathlib import Path
from datetime import datetime

from .config import (
    VAULT_PATH,
    GEMINI_MODEL,
    BATCH_SIZE,
    EXCLUDE_PATTERNS,
    RELATIONSHIP_TYPES,
)
from .db import (
    init_db,
    get_content_hash,
    needs_reindex,
    upsert_note,
    add_edge,
    add_claim,
    clear_edges_for_note,
    get_stats,
    get_last_index_time,
    set_last_index_time,
)


# =============================================================================
# EXTRACTION PROMPT
# =============================================================================


def _build_extraction_prompt() -> str:
    """Build the system prompt for LLM extraction."""
    relations_list = "\n".join(f"- {k}: {v}" for k, v in RELATIONSHIP_TYPES.items())

    return f"""Analyze these Obsidian markdown notes. Extract:

1. **Claims**: Key assertions, facts, or insights stated in each note
2. **Connections**: Relationships between concepts mentioned (including [[WikiLinks]])

Output a JSON array with this structure:
[{{
  "source": "filename.md",
  "target": "Target concept or note name",
  "relation": "relationship_type",
  "claim": "Brief description of the connection or assertion"
}}]

Valid relationship types:
{relations_list}

Rules:
- Extract explicit [[WikiLinks]] as "links_to" relationships
- Identify implicit conceptual relationships based on content
- Use "related" if no specific type fits
- Keep claims concise (1-2 sentences max)
- source should be the note filename (with .md)
- target should be the linked concept/note name (without path)
- Output ONLY valid JSON, no markdown formatting"""


EXTRACTION_PROMPT = _build_extraction_prompt()


# =============================================================================
# GEMINI CLI INTEGRATION
# =============================================================================


def call_gemini_cli(content: str, timeout: int = 120) -> list | None:
    """
    Call Gemini CLI for claim/connection extraction.

    Args:
        content: Batch of notes to analyze
        timeout: Max seconds to wait for response

    Returns:
        List of extracted items or None on error
    """
    cmd = [
        "gemini",
        "--model",
        GEMINI_MODEL,
    ]

    full_input = f"{EXTRACTION_PROMPT}\n\n---\nNOTES TO ANALYZE:\n---\n\n{content}"
    proc = None

    try:
        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        stdout, stderr = proc.communicate(input=full_input, timeout=timeout)

        if proc.returncode != 0:
            print(f"  ⚠️  Gemini CLI error (code {proc.returncode}): {stderr[:200]}")
            return None

        # Parse response - Gemini CLI returns raw text, not JSON wrapper
        raw = stdout.strip()

        # Clean markdown code blocks if present
        raw = re.sub(r"^```json\s*", "", raw)
        raw = re.sub(r"^```\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        raw = raw.strip()

        # Find JSON array in response
        json_match = re.search(r"\[[\s\S]*\]", raw)
        if json_match:
            raw = json_match.group(0)

        return json.loads(raw)

    except subprocess.TimeoutExpired:
        if proc:
            proc.kill()
        print(f"  ⚠️  Gemini CLI timeout after {timeout}s")
        return None
    except json.JSONDecodeError as e:
        print(f"  ⚠️  JSON parse error: {e}")
        return None
    except FileNotFoundError:
        print("  ❌ Gemini CLI not found. Install with: npm install -g @google/gemini-cli")
        return None
    except Exception as e:
        print(f"  ⚠️  Unexpected error: {type(e).__name__}: {e}")
        return None


# =============================================================================
# TEXT EXTRACTION HELPERS
# =============================================================================


def extract_wikilinks(content: str) -> list[str]:
    """Extract [[WikiLinks]] from content."""
    # Match [[Link]] or [[Link|Alias]]
    pattern = r"\[\[([^\]|#]+)(?:[|#][^\]]+)?\]\]"
    matches = re.findall(pattern, content)
    # Deduplicate while preserving order
    seen = set()
    result = []
    for m in matches:
        if m not in seen:
            seen.add(m)
            result.append(m)
    return result


def extract_title(content: str, filename: str) -> str:
    """Extract title from first H1 heading or use filename."""
    # Look for # Title
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    # Fallback to filename
    return filename.replace(".md", "").replace("_", " ").replace("-", " ")


def extract_frontmatter_tags(content: str) -> list[str]:
    """Extract tags from YAML frontmatter."""
    # Match YAML frontmatter
    fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not fm_match:
        return []

    frontmatter = fm_match.group(1)

    # Look for tags
    tags_match = re.search(r"tags:\s*\n((?:\s+-\s+.+\n?)+)", frontmatter)
    if tags_match:
        tags_block = tags_match.group(1)
        return re.findall(r"-\s+(\S+)", tags_block)

    # Single-line tags: [tag1, tag2]
    tags_match = re.search(r"tags:\s*\[([^\]]+)\]", frontmatter)
    if tags_match:
        return [t.strip() for t in tags_match.group(1).split(",")]

    return []


def should_exclude(path: Path) -> bool:
    """Check if path should be excluded from indexing."""
    try:
        rel_path = str(path.relative_to(VAULT_PATH))
    except ValueError:
        return True

    return any(excl in rel_path for excl in EXCLUDE_PATTERNS)


# =============================================================================
# FILE DISCOVERY
# =============================================================================


def get_files_to_index(
    pattern: str | None = None,
    query: str | None = None,
    modified_since: float | None = None,
) -> list[Path]:
    """
    Get list of markdown files to index based on filters.

    This enables smart indexing - only process files that actually need it.

    Args:
        pattern: Glob pattern relative to vault (e.g., "10_Projects/**/*.md")
                 If None, uses "**/*.md" (all markdown files)
        query: ripgrep search term - only files containing this text
        modified_since: Unix timestamp - only files modified after this time

    Returns:
        List of Path objects for files matching all criteria
    """
    # Start with glob pattern
    glob_pattern = pattern if pattern else "**/*.md"
    md_files = list(VAULT_PATH.glob(glob_pattern))

    # Filter out excluded paths
    md_files = [f for f in md_files if not should_exclude(f)]

    # Filter by modification time if specified
    if modified_since is not None:
        md_files = [f for f in md_files if f.stat().st_mtime > modified_since]

    # Filter by content query using ripgrep (fast!)
    if query:
        try:
            # Use ripgrep to find files containing the query
            result = subprocess.run(
                ["rg", "-l", "--type", "md", query, str(VAULT_PATH)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                # rg -l returns file paths, one per line
                rg_files = set(
                    Path(p.strip()) for p in result.stdout.strip().split("\n") if p.strip()
                )
                md_files = [f for f in md_files if f in rg_files]
            else:
                # No matches found or error - return empty list for query filter
                md_files = []
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # ripgrep not available or timeout - fall back to no query filter
            pass

    return md_files


# =============================================================================
# MAIN INDEXER
# =============================================================================


def build_index(
    full_rebuild: bool = False,
    verbose: bool = True,
    limit: int | None = None,
    file_list: list[Path] | None = None,
) -> dict:
    """
    Build or update the knowledge graph index.

    Args:
        full_rebuild: Force re-indexing of all files (ignores content hash check)
        verbose: Print progress to stdout
        limit: Maximum number of files to index (None = all files)
        file_list: Pre-filtered list of files to index. If provided, skips
                   vault-wide glob. Use get_files_to_index() to generate this.

    Returns:
        Dictionary with indexing statistics
    """
    start_time = datetime.now()

    if verbose:
        print("🧠 Obsidian MCP Indexer")
        print(f"   Vault: {VAULT_PATH}")
        print(f"   Model: {GEMINI_MODEL}")
        mode_desc = "Full Rebuild" if full_rebuild else "Incremental"
        if file_list is not None:
            mode_desc = f"Targeted ({len(file_list)} files)"
        print(f"   Mode:  {mode_desc}")
        if limit:
            print(f"   Limit: {limit} files")
        print()

    # Initialize database
    init_db()

    # Use provided file list or gather all markdown files
    if file_list is not None:
        md_files = file_list
        total_files = len(md_files)
    else:
        md_files = list(VAULT_PATH.glob("**/*.md"))
        md_files = [f for f in md_files if not should_exclude(f)]
        total_files = len(md_files)

    # Apply limit if specified
    if limit and limit < total_files:
        md_files = md_files[:limit]

    if verbose:
        if file_list is not None:
            print(f"📂 Processing {len(md_files)} targeted files")
        elif limit:
            print(f"📂 Processing {len(md_files)} of {total_files} markdown files")
        else:
            print(f"📂 Found {len(md_files)} markdown files")

    # Tracking
    batch_buffer = []
    batch_size = 0
    files_processed = 0
    files_skipped = 0
    files_errored = 0
    total_edges = 0
    total_claims = 0
    num_files = len(md_files)

    def print_progress(current: int, filename: str, status: str = ""):
        """Print progress indicator with file info."""
        if not verbose:
            return
        pct = (current / num_files) * 100 if num_files > 0 else 0
        bar_width = 20
        filled = int(bar_width * current / num_files) if num_files > 0 else 0
        bar = "█" * filled + "░" * (bar_width - filled)
        # Truncate filename if too long
        display_name = filename[:30] + "..." if len(filename) > 30 else filename
        status_str = f" ({status})" if status else ""
        print(
            f"\r   [{bar}] {current}/{num_files} ({pct:5.1f}%) {display_name}{status_str}".ljust(
                80
            ),
            end="",
            flush=True,
        )

    for i, fpath in enumerate(md_files):
        try:
            content = fpath.read_text(encoding="utf-8")
            filename = fpath.name
            rel_path = str(fpath.relative_to(VAULT_PATH))
            folder = fpath.parent.name if fpath.parent != VAULT_PATH else ""
            content_hash = get_content_hash(content)
            title = extract_title(content, filename)

            # Check if needs re-indexing
            if not full_rebuild and not needs_reindex(filename, content_hash):
                files_skipped += 1
                print_progress(i + 1, filename, "skipped")
                continue

            # Show progress for file being indexed
            print_progress(i + 1, filename, "indexing")

            # Always update note metadata
            upsert_note(filename, rel_path, title, folder, content_hash, content)

            # Extract native wikilinks (no LLM needed)
            wikilinks = extract_wikilinks(content)
            clear_edges_for_note(filename)

            for link in wikilinks:
                add_edge(filename, link, "links_to")
                total_edges += 1

            # Add to batch for LLM extraction
            # Truncate very long notes to avoid token limits
            note_content = content[:10000] if len(content) > 10000 else content
            tagged = f'<note filename="{filename}" path="{rel_path}">\n{note_content}\n</note>\n\n'

            batch_buffer.append(tagged)
            batch_size += len(tagged)
            files_processed += 1

            # Fire batch when size threshold reached or at end
            is_last = i == len(md_files) - 1
            should_fire = batch_size >= BATCH_SIZE or (is_last and batch_buffer)

            if should_fire:
                # Clear progress line before batch message
                if verbose:
                    print("\r" + " " * 80 + "\r", end="")
                    print(
                        f"   🔄 Processing batch ({len(batch_buffer)} notes, {batch_size // 1000}KB)..."
                    )

                extractions = call_gemini_cli("\n".join(batch_buffer))

                if extractions:
                    for item in extractions:
                        source = item.get("source", "")
                        target = item.get("target", "")
                        relation = item.get("relation", "related")
                        claim = item.get("claim", "")

                        # Skip empty or self-referential
                        if not source or not target or source == target:
                            continue

                        # Normalize relation
                        if relation not in RELATIONSHIP_TYPES:
                            relation = "related"

                        add_edge(source, target, relation, claim)
                        total_edges += 1

                        # Store claim if substantial
                        if claim and len(claim) > 10:
                            add_claim(source, target, claim)
                            total_claims += 1

                    if verbose:
                        print(f"      ✓ Extracted {len(extractions)} items")

                # Reset batch
                batch_buffer = []
                batch_size = 0

        except Exception as e:
            files_errored += 1
            if verbose:
                print("\r" + " " * 80 + "\r", end="")  # Clear progress line
                print(f"   ❌ Error processing {fpath.name}: {e}")

    # Clear progress line before final output
    if verbose:
        print("\r" + " " * 80 + "\r", end="")

    # Get final stats
    stats = get_stats()
    elapsed = (datetime.now() - start_time).total_seconds()

    # Record successful index time (only if we actually processed files)
    if files_processed > 0:
        set_last_index_time(start_time.timestamp())

    if verbose:
        print()
        print("✅ Indexing Complete")
        print(f"   ⏱️  Time: {elapsed:.1f}s")
        print(f"   📄 Notes indexed: {files_processed}")
        print(f"   ⏭️  Notes skipped (unchanged): {files_skipped}")
        print(f"   ❌ Notes errored: {files_errored}")
        print(f"   🔗 Total edges in graph: {stats['total_edges']}")
        print(f"   💡 Total claims: {stats['total_claims']}")
        print()

        if stats["relations"]:
            print("   Relationship distribution (top 10):")
            for rel, count in list(stats["relations"].items())[:10]:
                print(f"      {rel}: {count}")

    return {
        "files_processed": files_processed,
        "files_skipped": files_skipped,
        "files_errored": files_errored,
        "elapsed_seconds": elapsed,
        **stats,
    }


def index_single_note(filepath: str | Path, verbose: bool = False) -> dict | None:
    """
    Index a single note (for real-time updates).

    Args:
        filepath: Path to the markdown file
        verbose: Print progress

    Returns:
        Extraction results or None on error
    """
    filepath = Path(filepath)

    if not filepath.exists():
        return None

    try:
        content = filepath.read_text(encoding="utf-8")
        filename = filepath.name
        rel_path = str(filepath.relative_to(VAULT_PATH))
        folder = filepath.parent.name if filepath.parent != VAULT_PATH else ""
        content_hash = get_content_hash(content)
        title = extract_title(content, filename)

        # Update note record
        upsert_note(filename, rel_path, title, folder, content_hash, content)

        # Extract wikilinks
        wikilinks = extract_wikilinks(content)
        clear_edges_for_note(filename)

        for link in wikilinks:
            add_edge(filename, link, "links_to")

        # LLM extraction for single note
        tagged = f'<note filename="{filename}" path="{rel_path}">\n{content}\n</note>'
        extractions = call_gemini_cli(tagged)

        if extractions:
            for item in extractions:
                source = item.get("source", filename)
                target = item.get("target", "")
                relation = item.get("relation", "related")
                claim = item.get("claim", "")

                if target and source != target:
                    add_edge(source, target, relation, claim)
                    if claim:
                        add_claim(source, target, claim)

        return {"filename": filename, "wikilinks": wikilinks, "extractions": extractions or []}

    except Exception as e:
        if verbose:
            print(f"Error indexing {filepath}: {e}")
        return None
