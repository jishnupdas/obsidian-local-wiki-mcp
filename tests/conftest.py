
import os
import sys
import pytest
import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add src to path if not already there (though pyproject.toml should handle this)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from obsidian_mcp.db import init_db, get_db
from obsidian_mcp import config

@pytest.fixture
def tmp_vault(tmp_path):
    """Create a temporary directory to act as the vault."""
    vault = tmp_path / "TestVault"
    vault.mkdir()
    
    # Create standard folders
    (vault / "00_Inbox").mkdir()
    (vault / "10_Projects").mkdir()
    (vault / "99_System" / "Templates").mkdir(parents=True)
    (vault / ".obsidian").mkdir()
    
    # Create dummy templates
    (vault / "99_System" / "Templates" / "Concept Note.md").write_text(
        "---\ntags: [concept]\n---\n# {{title}}\n\n{{content}}", encoding="utf-8"
    )
    
    return vault

@pytest.fixture
def tmp_db(tmp_vault):
    """Initialize a temporary SQLite database."""
    db_path = tmp_vault / ".obsidian" / "vault_graph.db"
    
    # Patch the DB path in config and db module
    with patch("obsidian_mcp.config.DB_PATH", db_path), \
         patch("obsidian_mcp.db.DB_PATH", db_path):
        
        # Initialize schema
        init_db()
        yield db_path

@pytest.fixture
def mock_config(tmp_vault, tmp_db):
    """Patch configuration to use temp vault and db."""
    # We must patch where the variables are imported/used, not just in config
    with patch("obsidian_mcp.config.VAULT_PATH", tmp_vault), \
         patch("obsidian_mcp.config.DB_PATH", tmp_db), \
         patch("obsidian_mcp.tools.VAULT_PATH", tmp_vault), \
         patch("obsidian_mcp.indexer.VAULT_PATH", tmp_vault), \
         patch("obsidian_mcp.db.DB_PATH", tmp_db), \
         patch("obsidian_mcp.server.VAULT_PATH", tmp_vault), \
         patch("obsidian_mcp.hooks.VAULT_PATH", tmp_vault):
        yield

@pytest.fixture
def sample_notes(tmp_vault):
    """Create a set of interlinked notes for testing."""
    notes = {
        "AI_Overview.md": """---
tags: [ai, overview]
created: 2023-01-01
---
# Artificial Intelligence

AI is a broad field. See [[Machine_Learning]] and [[Neural_Networks]].
""",
        "Machine_Learning.md": """---
tags: [ai, ml]
---
# Machine Learning

ML is a subset of [[AI_Overview]]. It involves learning from data.
""",
        "Neural_Networks.md": """---
tags: [ai, nn]
---
# Neural Networks

NNs are inspired by the human brain. Used in [[Deep_Learning]].
""",
        "Deep_Learning.md": """---
tags: [ai, dl]
---
# Deep Learning

Deep Learning uses multi-layered [[Neural_Networks]].
"""
    }
    
    for filename, content in notes.items():
        (tmp_vault / filename).write_text(content, encoding="utf-8")
    
    return notes
