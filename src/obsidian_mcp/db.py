"""
SQLite database layer for the knowledge graph.

Schema:
- notes: File metadata and content hashes for incremental indexing
- edges: Relationships between notes/concepts
- claims: Extracted facts and assertions
- notes_fts: Full-text search index
- system_meta: Key-value store for indexer state (last run time, etc.)
"""

import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager
from typing import Generator

from .config import DB_PATH

# =============================================================================
# SCHEMA
# =============================================================================

SCHEMA = """
-- Notes table: stores file metadata and content hash for incremental indexing
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY,
    filename TEXT UNIQUE NOT NULL,
    path TEXT NOT NULL,
    title TEXT,
    folder TEXT,
    created_at TEXT,
    indexed_at TEXT,
    content_hash TEXT
);

-- Edges: relationships between notes/concepts
CREATE TABLE IF NOT EXISTS edges (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,           -- Filename or concept name
    target TEXT NOT NULL,           -- Target note or concept
    relation TEXT NOT NULL,         -- Relationship type
    claim TEXT,                     -- Supporting assertion
    confidence REAL DEFAULT 1.0,    -- LLM confidence (0.0-1.0)
    extracted_at TEXT,
    UNIQUE(source, target, relation)
);

-- Claims: standalone facts extracted from notes
CREATE TABLE IF NOT EXISTS claims (
    id INTEGER PRIMARY KEY,
    note_filename TEXT NOT NULL,
    subject TEXT NOT NULL,
    claim TEXT NOT NULL,
    extracted_at TEXT,
    FOREIGN KEY (note_filename) REFERENCES notes(filename) ON DELETE CASCADE
);

-- Full-text search on note content
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
    filename, 
    title, 
    content,
    tokenize='porter unicode61'
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target);
CREATE INDEX IF NOT EXISTS idx_edges_relation ON edges(relation);
CREATE INDEX IF NOT EXISTS idx_notes_folder ON notes(folder);
CREATE INDEX IF NOT EXISTS idx_notes_hash ON notes(content_hash);
CREATE INDEX IF NOT EXISTS idx_claims_note ON claims(note_filename);

-- System metadata for indexer state tracking
CREATE TABLE IF NOT EXISTS system_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Repo mappings: links vault folders to git repos and external systems
CREATE TABLE IF NOT EXISTS repo_mappings (
    id INTEGER PRIMARY KEY,
    vault_path TEXT UNIQUE NOT NULL,
    repo_path TEXT,
    github_repo TEXT,
    jira_project TEXT,
    description TEXT,
    active BOOLEAN DEFAULT 1,
    created_at TEXT,
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_repo_vault_path ON repo_mappings(vault_path);
CREATE INDEX IF NOT EXISTS idx_repo_active ON repo_mappings(active);
"""


# =============================================================================
# CONNECTION MANAGEMENT
# =============================================================================


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Context manager for database connections with auto-commit."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Initialize database schema."""
    with get_db() as conn:
        conn.executescript(SCHEMA)


# =============================================================================
# HASHING & CHANGE DETECTION
# =============================================================================


def get_content_hash(content: str) -> str:
    """Generate truncated SHA-256 hash for change detection."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def needs_reindex(filename: str, content_hash: str) -> bool:
    """Check if file needs re-indexing based on content hash."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT content_hash FROM notes WHERE filename = ?", (filename,)
        ).fetchone()
        return row is None or row["content_hash"] != content_hash


# =============================================================================
# NOTE OPERATIONS
# =============================================================================


def upsert_note(
    filename: str, path: str, title: str, folder: str, content_hash: str, content: str
) -> None:
    """Insert or update a note record and its FTS index."""
    now = datetime.now().isoformat()

    with get_db() as conn:
        # Upsert note metadata
        conn.execute(
            """
            INSERT INTO notes (filename, path, title, folder, content_hash, indexed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(filename) DO UPDATE SET
                path = excluded.path,
                title = excluded.title,
                folder = excluded.folder,
                content_hash = excluded.content_hash,
                indexed_at = excluded.indexed_at
        """,
            (filename, path, title, folder, content_hash, now),
        )

        # Update FTS index
        conn.execute("DELETE FROM notes_fts WHERE filename = ?", (filename,))
        conn.execute(
            "INSERT INTO notes_fts (filename, title, content) VALUES (?, ?, ?)",
            (filename, title, content),
        )


def get_note_by_filename(filename: str) -> dict | None:
    """Get note metadata by filename."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM notes WHERE filename = ?", (filename,)).fetchone()
        return dict(row) if row else None


# =============================================================================
# EDGE OPERATIONS
# =============================================================================


def add_edge(
    source: str, target: str, relation: str, claim: str | None = None, confidence: float = 1.0
) -> None:
    """Add or update an edge in the graph."""
    now = datetime.now().isoformat()

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO edges (source, target, relation, claim, confidence, extracted_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, target, relation) DO UPDATE SET
                claim = excluded.claim,
                confidence = excluded.confidence,
                extracted_at = excluded.extracted_at
        """,
            (source, target, relation, claim, confidence, now),
        )


def clear_edges_for_note(filename: str) -> None:
    """Clear all edges where this note is the source (for re-indexing)."""
    with get_db() as conn:
        conn.execute("DELETE FROM edges WHERE source = ?", (filename,))
        conn.execute("DELETE FROM claims WHERE note_filename = ?", (filename,))


def get_connections(note_name: str) -> dict:
    """Get all connections for a note (outlinks and backlinks)."""
    with get_db() as conn:
        outlinks = conn.execute(
            """
            SELECT target, relation, claim, confidence
            FROM edges 
            WHERE source = ? OR source = ?
            ORDER BY confidence DESC
        """,
            (note_name, note_name + ".md"),
        ).fetchall()

        backlinks = conn.execute(
            """
            SELECT source, relation, claim, confidence
            FROM edges 
            WHERE target = ? OR target = ?
            ORDER BY confidence DESC
        """,
            (note_name, note_name.replace(".md", "")),
        ).fetchall()

        return {
            "outlinks": [dict(row) for row in outlinks],
            "backlinks": [dict(row) for row in backlinks],
        }


# =============================================================================
# CLAIM OPERATIONS
# =============================================================================


def add_claim(note_filename: str, subject: str, claim: str) -> None:
    """Add an extracted claim."""
    now = datetime.now().isoformat()

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO claims (note_filename, subject, claim, extracted_at)
            VALUES (?, ?, ?, ?)
        """,
            (note_filename, subject, claim, now),
        )


def get_claims_for_note(filename: str) -> list[dict]:
    """Get all claims extracted from a note."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT subject, claim FROM claims WHERE note_filename = ?", (filename,)
        ).fetchall()
        return [dict(row) for row in rows]


# =============================================================================
# SEARCH
# =============================================================================


def search_fts(query: str, limit: int = 20) -> list[dict]:
    """Full-text search across notes."""
    with get_db() as conn:
        # FTS5 MATCH syntax - quote multi-word queries
        if " " in query and not query.startswith('"'):
            search_query = f'"{query}"'
        else:
            search_query = query

        try:
            rows = conn.execute(
                """
                SELECT 
                    filename, 
                    title, 
                    snippet(notes_fts, 2, '>>>', '<<<', '...', 32) as snippet,
                    rank
                FROM notes_fts
                WHERE notes_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """,
                (search_query, limit),
            ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.OperationalError:
            # Fallback for malformed queries
            return []


def search_edges(query: str, limit: int = 20) -> list[dict]:
    """Search edges by source, target, or claim content."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT source, target, relation, claim 
            FROM edges 
            WHERE source LIKE ? OR target LIKE ? OR claim LIKE ?
            ORDER BY extracted_at DESC
            LIMIT ?
        """,
            (f"%{query}%", f"%{query}%", f"%{query}%", limit),
        ).fetchall()
        return [dict(row) for row in rows]


# =============================================================================
# STATISTICS
# =============================================================================


def get_stats() -> dict:
    """Get knowledge graph statistics."""
    with get_db() as conn:
        total_notes = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        total_edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        total_claims = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]

        relations = conn.execute(
            "SELECT relation, COUNT(*) as count FROM edges GROUP BY relation ORDER BY count DESC"
        ).fetchall()

        folders = conn.execute(
            "SELECT folder, COUNT(*) as count FROM notes GROUP BY folder ORDER BY count DESC LIMIT 10"
        ).fetchall()

        return {
            "total_notes": total_notes,
            "total_edges": total_edges,
            "total_claims": total_claims,
            "relations": {row["relation"]: row["count"] for row in relations},
            "folders": {row["folder"]: row["count"] for row in folders},
        }


def get_orphan_notes(limit: int = 50) -> list[str]:
    """Find notes with no outgoing or incoming edges."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT n.filename
            FROM notes n
            LEFT JOIN edges e_out ON n.filename = e_out.source
            LEFT JOIN edges e_in ON n.filename = e_in.target
            WHERE e_out.id IS NULL AND e_in.id IS NULL
            LIMIT ?
        """,
            (limit,),
        ).fetchall()
        return [row["filename"] for row in rows]


def get_most_connected(limit: int = 20) -> list[dict]:
    """Get notes/concepts with most connections."""
    with get_db() as conn:
        # Count both directions
        rows = conn.execute(
            """
            SELECT name, SUM(cnt) as total FROM (
                SELECT source as name, COUNT(*) as cnt FROM edges GROUP BY source
                UNION ALL
                SELECT target as name, COUNT(*) as cnt FROM edges GROUP BY target
            )
            GROUP BY name
            ORDER BY total DESC
            LIMIT ?
        """,
            (limit,),
        ).fetchall()
        return [{"name": row["name"], "connections": row["total"]} for row in rows]


# =============================================================================
# SYSTEM METADATA (Indexer State)
# =============================================================================


def get_last_index_time() -> float | None:
    """
    Get the timestamp of the last successful index run.

    Returns:
        Unix timestamp (float) or None if never indexed
    """
    with get_db() as conn:
        row = conn.execute("SELECT value FROM system_meta WHERE key = 'last_index_time'").fetchone()
        if row:
            try:
                return float(row["value"])
            except (ValueError, TypeError):
                return None
        return None


def set_last_index_time(timestamp: float | None = None) -> None:
    """
    Set the timestamp of the last successful index run.

    Args:
        timestamp: Unix timestamp. If None, uses current time.
    """
    if timestamp is None:
        timestamp = datetime.now().timestamp()

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO system_meta (key, value) VALUES ('last_index_time', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
            (str(timestamp),),
        )


def get_indexed_filenames() -> set[str]:
    """
    Get all filenames currently in the index.

    Returns:
        Set of filenames that have been indexed
    """
    with get_db() as conn:
        rows = conn.execute("SELECT filename FROM notes").fetchall()
        return {row["filename"] for row in rows}


# =============================================================================
# REPO MAPPINGS (Dev Integration)
# =============================================================================


def upsert_repo_mapping(
    vault_path: str,
    repo_path: str | None = None,
    github_repo: str | None = None,
    jira_project: str | None = None,
    description: str | None = None,
    active: bool = True,
) -> None:
    """
    Insert or update a repo mapping.

    Args:
        vault_path: Vault folder path (e.g., "10_Projects/OVI")
        repo_path: Local git repo path (e.g., "~/Projects/dev/ovi")
        github_repo: GitHub repo in "owner/repo" format
        jira_project: Jira project key (e.g., "AK")
        description: Human-readable description
        active: Whether this mapping is currently active
    """
    now = datetime.now().isoformat()

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO repo_mappings 
            (vault_path, repo_path, github_repo, jira_project, description, active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(vault_path) DO UPDATE SET
                repo_path = excluded.repo_path,
                github_repo = excluded.github_repo,
                jira_project = excluded.jira_project,
                description = excluded.description,
                active = excluded.active,
                updated_at = excluded.updated_at
        """,
            (vault_path, repo_path, github_repo, jira_project, description, active, now, now),
        )


def get_repo_mapping(vault_path: str) -> dict | None:
    """
    Get repo mapping for a specific vault path.

    Args:
        vault_path: Vault folder path

    Returns:
        Mapping dict or None if not found
    """
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM repo_mappings WHERE vault_path = ? AND active = 1", (vault_path,)
        ).fetchone()
        return dict(row) if row else None


def get_repo_for_note(filename: str) -> dict | None:
    """
    Get repo mapping for a note based on its folder path.

    Args:
        filename: Note filename

    Returns:
        Mapping dict or None if no mapping found
    """
    with get_db() as conn:
        # Get note's folder path
        note_row = conn.execute("SELECT path FROM notes WHERE filename = ?", (filename,)).fetchone()

        if not note_row:
            return None

        note_path = note_row["path"]

        # Find the longest matching vault_path prefix
        mappings = conn.execute(
            "SELECT * FROM repo_mappings WHERE active = 1 ORDER BY LENGTH(vault_path) DESC"
        ).fetchall()

        for mapping in mappings:
            vault_path = mapping["vault_path"]
            if note_path.startswith(vault_path):
                return dict(mapping)

        return None


def get_all_repo_mappings(active_only: bool = True) -> list[dict]:
    """
    Get all repo mappings.

    Args:
        active_only: Only return active mappings

    Returns:
        List of mapping dicts
    """
    with get_db() as conn:
        if active_only:
            rows = conn.execute(
                "SELECT * FROM repo_mappings WHERE active = 1 ORDER BY vault_path"
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM repo_mappings ORDER BY vault_path").fetchall()

        return [dict(row) for row in rows]


def clear_repo_mappings() -> None:
    """Clear all repo mappings (useful before reload)."""
    with get_db() as conn:
        conn.execute("DELETE FROM repo_mappings")
