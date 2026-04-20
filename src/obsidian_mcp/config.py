"""
Configuration management for Obsidian MCP Server.

All settings are centralized here for easy modification.
Environment variables override defaults via .env file.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()


def _get_path(env_var: str, default: str) -> Path:
    """Get path from environment variable or default, expanding user."""
    return Path(os.getenv(env_var, default)).expanduser()


def _get_int(env_var: str, default: int) -> int:
    """Get integer from environment variable or default."""
    return int(os.getenv(env_var, str(default)))


# =============================================================================
# PATHS
# =============================================================================

VAULT_PATH = _get_path("VAULT_PATH", "~/Projects/project-sb")
DB_PATH = _get_path("DB_PATH", "~/Projects/project-sb/.obsidian/vault_graph.db")

# =============================================================================
# INDEXER SETTINGS
# =============================================================================

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")

_DEFAULT_MODELS: dict[str, str] = {
    "gemini": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),  # backward-compat alias
    "claude": "claude-sonnet-4-5",
    "openai": "gpt-4o-mini",
}
LLM_MODEL = os.getenv("LLM_MODEL") or _DEFAULT_MODELS.get(LLM_PROVIDER.lower(), "gemini-2.5-flash")

BATCH_SIZE = _get_int("BATCH_SIZE", 25000)  # Characters per batch

# Paths to exclude from indexing (relative to vault root)
EXCLUDE_PATTERNS = [
    ".obsidian",
    ".git",
    # Templates are included for reference
]

# =============================================================================
# JOURNAL SETTINGS
# =============================================================================

JOURNAL_FOLDER = os.getenv("JOURNAL_FOLDER", "50_Journal")
JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "")
JOURNAL_DATE_FORMAT = os.getenv("JOURNAL_DATE_FORMAT", "%Y-%m-%d")

# =============================================================================
# VECTOR SEARCH SETTINGS
# =============================================================================

VECTOR_MODEL = os.getenv("VECTOR_MODEL", "BAAI/bge-small-en-v1.5")
VECTOR_CHUNK_SIZE = _get_int("VECTOR_CHUNK_SIZE", 1500)    # chars per chunk
VECTOR_CHUNK_OVERLAP = _get_int("VECTOR_CHUNK_OVERLAP", 200)  # overlap between chunks

# =============================================================================
# TEMPLATE PATHS (relative to vault root)
# =============================================================================

TEMPLATES = {
    "concept": "99_System/Templates/Concept Note.md",
    "bridge": "99_System/Templates/Bridge Note.md",
    "daily": "99_System/Templates/Daily Note.md",
    "project": "99_System/Templates/Project Dashboard.md",
    "ticket": "99_System/Templates/Ticket Note.md",
    "web_clip": "99_System/Templates/Web Clip.md",
}

# =============================================================================
# RELATIONSHIP TYPES
# =============================================================================

RELATIONSHIP_TYPES = {
    # Core relationships (from Graph Connectivity Enhancement Plan)
    "prerequisite": "Must understand A before B",
    "application_of": "B is a practical use of A",
    "analogy_to": "Structurally similar across domains",
    "opposes": "Contradictory or trade-off",
    "extends": "Builds upon or refines",
    "part_of": "Component relationship",
    # Project/Code relationships
    "implements": "Code/Project realizes a concept",
    "documents": "Note describes a project/code",
    "cites": "References external source",
    "supersedes": "Replaces or deprecates",
    # Workflow relationships
    "triggers": "Event/action causes another",
    "constrains": "Limits or bounds",
    # Data/Analysis relationships
    "measures": "Quantifies or tracks",
    "derived_from": "Calculated or extracted from",
    # Knowledge graph specific
    "bridges": "Cross-domain connection (explicit)",
    "example_of": "Instance or case study",
    # Generic (fallback)
    "links_to": "Native wikilink connection",
    "related": "General relationship",
}

# =============================================================================
# HELPER: CONFIG DICT (for backward compatibility)
# =============================================================================

CONFIG = {
    "vault_path": VAULT_PATH,
    "db_path": DB_PATH,
    "gemini_model": GEMINI_MODEL,  # kept for backward compat
    "llm_provider": LLM_PROVIDER,
    "llm_model": LLM_MODEL,
    "batch_size": BATCH_SIZE,
    "exclude_patterns": EXCLUDE_PATTERNS,
    "templates": TEMPLATES,
    "journal_folder": JOURNAL_FOLDER,
    "journal_date_format": JOURNAL_DATE_FORMAT,
    "vector_model": VECTOR_MODEL,
    "vector_chunk_size": VECTOR_CHUNK_SIZE,
    "vector_chunk_overlap": VECTOR_CHUNK_OVERLAP,
}


def print_config():
    """Print current configuration for debugging."""
    print("=== Obsidian MCP Configuration ===")
    print(f"  Vault Path:      {VAULT_PATH}")
    print(f"  Database:        {DB_PATH}")
    print(f"  LLM Provider:    {LLM_PROVIDER}")
    print(f"  LLM Model:       {LLM_MODEL}")
    print(f"  Batch Size:      {BATCH_SIZE} chars")
    print(f"  Journal:         {JOURNAL_FOLDER}/")
    print(f"  Excluded:        {', '.join(EXCLUDE_PATTERNS)}")
    print(f"  Relations:       {len(RELATIONSHIP_TYPES)} types")
    print(f"  Vector Model:    {VECTOR_MODEL}")
    print(f"  Chunk Size:      {VECTOR_CHUNK_SIZE} chars")
    print(f"  Chunk Overlap:   {VECTOR_CHUNK_OVERLAP} chars")
