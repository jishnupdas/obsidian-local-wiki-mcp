import pytest
import json
from unittest.mock import patch, MagicMock
from obsidian_mcp import hooks
from obsidian_mcp import db

@pytest.fixture
def populated_db(tmp_db):
    """Populate DB with repo mappings."""
    db.upsert_repo_mapping(
        vault_path="10_Projects/ProjectAlpha",
        repo_path="/home/user/project-alpha",
        description="Alpha project",
        active=True
    )
    db.upsert_repo_mapping(
        vault_path="10_Projects/ProjectBeta",
        repo_path="/home/user/project-beta",
        description="Beta project",
        active=True
    )
    return tmp_db

@pytest.fixture
def project_notes(tmp_vault):
    """Create Dev Logs for testing context extraction."""
    alpha_dir = tmp_vault / "10_Projects/ProjectAlpha"
    alpha_dir.mkdir(parents=True, exist_ok=True)
    (alpha_dir / "Dev Log.md").write_text("""# 🏗️ ProjectAlpha
## 📝 Executive Summary
This is the ProjectAlpha summary.
## 📊 Vital Statistics
- Python
""", encoding="utf-8")

    beta_dir = tmp_vault / "10_Projects/ProjectBeta"
    beta_dir.mkdir(parents=True, exist_ok=True)
    # ProjectBeta has no Dev Log, should handle gracefully

    return tmp_vault

def test_extract_keywords():
    engine = hooks.ContextEngine()

    prompt = "I want to work on ProjectAlpha and fix a bug in ProjectBeta."

    with patch("obsidian_mcp.hooks.get_all_repo_mappings") as mock_get:
        mock_get.return_value = [
            {"vault_path": "10_Projects/ProjectAlpha", "repo_path": "/path/alpha", "description": "Alpha"},
            {"vault_path": "10_Projects/ProjectBeta", "repo_path": "/path/beta", "description": "Beta"}
        ]

        keywords = engine.extract_keywords(prompt)
        names = [p["vault_path"].split("/")[-1] for p in keywords]
        assert "ProjectAlpha" in names
        assert "ProjectBeta" in names
        assert "irrelevant" not in names

def test_get_context(populated_db, project_notes, mock_config):
    engine = hooks.ContextEngine()

    prompt = "What is the status of ProjectAlpha?"

    output_json = engine.get_context(prompt)
    output = json.loads(output_json)

    assert "hookSpecificOutput" in output
    assert "additionalContext" in output["hookSpecificOutput"]

    context = output["hookSpecificOutput"]["additionalContext"]
    assert "Project Context (ProjectAlpha)" in context
    assert "This is the ProjectAlpha summary" in context

def test_get_context_no_match(populated_db, mock_config):
    engine = hooks.ContextEngine()
    prompt = "Just a general question."

    output_json = engine.get_context(prompt)
    output = json.loads(output_json)

    # No project match AND no semantic results → empty
    assert output == {"hookSpecificOutput": {"additionalContext": ""}}


def test_semantic_context_available():
    """When vector deps available, semantic results appear in context output."""
    engine = hooks.ContextEngine()

    fake_results = [
        {"filename": "Neural_Networks.md", "chunk_index": 0, "distance": 0.4},
        {"filename": "Deep_Learning.md", "chunk_index": 1, "distance": 0.6},
    ]

    with patch("obsidian_mcp.hooks.get_all_repo_mappings", return_value=[]), \
         patch("obsidian_mcp.vectors.is_available", return_value=True), \
         patch("obsidian_mcp.vectors.embed", return_value=[0.1] * 384) as mock_embed, \
         patch("obsidian_mcp.db.search_vectors", return_value=fake_results):

        output_json = engine.get_context("How do neural networks work?")
        output = json.loads(output_json)

        context = output["hookSpecificOutput"]["additionalContext"]
        assert "Semantically Related Notes" in context
        assert "Neural_Networks.md" in context
        assert "Deep_Learning.md" in context
        mock_embed.assert_called_once()


def test_semantic_context_unavailable():
    """When vector deps not installed, context works without semantic section."""
    engine = hooks.ContextEngine()

    with patch("obsidian_mcp.hooks.get_all_repo_mappings", return_value=[]), \
         patch("obsidian_mcp.vectors.is_available", return_value=False):

        output_json = engine.get_context("How do neural networks work?")
        output = json.loads(output_json)

        context = output["hookSpecificOutput"]["additionalContext"]
        assert "Semantically Related Notes" not in context
