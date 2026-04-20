
import pytest
from pathlib import Path
from obsidian_mcp import indexer
from obsidian_mcp.config import EXCLUDE_PATTERNS

def test_extract_wikilinks():
    content = "Link to [[Note A]] and [[Note B|Alias]] and [[Note C#Section]]."
    links = indexer.extract_wikilinks(content)
    assert "Note A" in links
    assert "Note B" in links
    assert "Note C" in links
    assert len(links) == 3

def test_extract_title():
    content_h1 = "# My Title\nSome content."
    assert indexer.extract_title(content_h1, "file.md") == "My Title"
    
    content_frontmatter = "---\ntitle: Frontmatter Title\n---\n# H1 Title"
    # Assuming extract_title prioritizes H1 or frontmatter?
    # Based on implementation reading: usually H1.
    assert indexer.extract_title(content_frontmatter, "file.md") == "H1 Title"
    
    content_none = "Just content."
    assert indexer.extract_title(content_none, "file.md") == "file"  # Fallback to filename stem

def test_extract_frontmatter_tags():
    content = """---
tags:
  - ai
  - python
---
# Content
"""
    tags = indexer.extract_frontmatter_tags(content)
    assert "ai" in tags
    assert "python" in tags

def test_extract_frontmatter_tags_inline():
    content = """---
tags: [ai, python]
---
"""
    tags = indexer.extract_frontmatter_tags(content)
    assert "ai" in tags
    assert "python" in tags

def test_should_exclude(tmp_vault, mock_config):
    # Test built-in exclusions
    assert indexer.should_exclude(tmp_vault / ".obsidian/workspace") is True
    assert indexer.should_exclude(tmp_vault / ".git/HEAD") is True
    assert indexer.should_exclude(tmp_vault / "Normal_File.md") is False

def test_get_files_to_index(tmp_vault, mock_config):
    # Create some files
    (tmp_vault / "Note1.md").touch()
    (tmp_vault / "Note2.md").touch()
    (tmp_vault / "Image.png").touch()
    (tmp_vault / ".hidden").touch()
    
    files = indexer.get_files_to_index()
    filenames = [f.name for f in files]
    
    assert "Note1.md" in filenames
    assert "Note2.md" in filenames
    assert "Image.png" not in filenames
    assert ".hidden" not in filenames

from unittest.mock import patch

def test_build_index_integration(tmp_vault, tmp_db, mock_config):
    """Test the full indexing pipeline with mocked Gemini."""
    # Create a note
    (tmp_vault / "Test.md").write_text("# Test Note\nContent with [[Link]]", encoding="utf-8")
    
    # Mock call_gemini_cli to return a fixed response
    mock_response = [{
        "source": "Test.md",
        "target": "Concept",
        "relation": "related",
        "claim": "Test claim"
    }]
    
    with patch("obsidian_mcp.indexer.call_llm_extract", return_value=mock_response):
        stats = indexer.build_index(full_rebuild=True, verbose=False)
        
        # 2 files: Test.md + Concept Note.md (from tmp_vault fixture)
        assert stats["files_processed"] == 2
        assert stats["total_edges"] >= 1 # 1 from wikilink + 1 from Gemini
