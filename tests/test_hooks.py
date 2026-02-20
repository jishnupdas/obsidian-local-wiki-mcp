import pytest
import json
from unittest.mock import patch, MagicMock
from obsidian_mcp import hooks
from obsidian_mcp import db

@pytest.fixture
def populated_db(tmp_db):
    """Populate DB with repo mappings."""
    db.upsert_repo_mapping(
        vault_path="10_Projects/OVI",
        repo_path="/home/user/ovi",
        description="Obsidian Vault Interface",
        active=True
    )
    db.upsert_repo_mapping(
        vault_path="10_Projects/MCP",
        repo_path="/home/user/mcp",
        description="Model Context Protocol server",
        active=True
    )
    return tmp_db

@pytest.fixture
def project_notes(tmp_vault):
    """Create Dev Logs for testing context extraction."""
    ovi_dir = tmp_vault / "10_Projects/OVI"
    ovi_dir.mkdir(parents=True, exist_ok=True)
    (ovi_dir / "Dev Log.md").write_text("""# 🏗️ OVI
## 📝 Executive Summary
This is the OVI project summary.
## 📊 Vital Statistics
- Python
""", encoding="utf-8")

    mcp_dir = tmp_vault / "10_Projects/MCP"
    mcp_dir.mkdir(parents=True, exist_ok=True)
    # MCP has no Dev Log, should handle gracefully
    
    return tmp_vault

def test_extract_keywords():
    engine = hooks.ContextEngine()
    # Mock database or cache if needed
    
    prompt = "I want to work on OVI and fix a bug in MCP."
    # We need keywords that map to projects. 
    # The engine hopefully knows about "OVI" and "MCP" from the DB.
    # So we need to mock the repo mappings loading?
    
    with patch("obsidian_mcp.hooks.get_all_repo_mappings") as mock_get:
        mock_get.return_value = [
            {"vault_path": "10_Projects/OVI", "repo_path": "/path/ovi", "description": "OVI"},
            {"vault_path": "10_Projects/MCP", "repo_path": "/path/mcp", "description": "MCP"}
        ]
        
        keywords = engine.extract_keywords(prompt)
        # Extract names from mapping dicts
        names = [p["vault_path"].split("/")[-1] for p in keywords]
        assert "OVI" in names
        assert "MCP" in names
        assert "irrelevant" not in names

def test_get_context(populated_db, project_notes, mock_config):
    engine = hooks.ContextEngine()
    
    prompt = "What is the status of OVI?"
    
    # Needs to return JSON string for hook output
    output_json = engine.get_context(prompt)
    output = json.loads(output_json)
    
    assert "hookSpecificOutput" in output
    assert "additionalContext" in output["hookSpecificOutput"]
    
    context = output["hookSpecificOutput"]["additionalContext"]
    assert "Project Context (OVI)" in context
    assert "This is the OVI project summary" in context

def test_get_context_no_match(populated_db, mock_config):
    engine = hooks.ContextEngine()
    prompt = "Just a general question."
    
    output_json = engine.get_context(prompt)
    output = json.loads(output_json)
    
    # Should be empty or minimal
    assert output == {"hookSpecificOutput": {"additionalContext": ""}}
