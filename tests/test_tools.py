
import pytest
from obsidian_mcp import tools
from obsidian_mcp import db

def test_read_note(tmp_vault, mock_config, sample_notes):
    """Test reading an existing note."""
    content = tools.read_note("AI_Overview.md")
    assert "# Artificial Intelligence" in content
    assert "📄" in content

def test_read_note_not_found(tmp_vault, mock_config):
    """Test reading a non-existent note."""
    result = tools.read_note("NonExistent.md")
    assert "not found" in result.lower()

def test_create_note(tmp_vault, mock_config):
    """Test creating a new note."""
    filename = "New_Idea.md"
    content = "This is a brilliant idea."
    
    # Test preview (force=False)
    preview = tools.create_note(filename, content=content, force=False)
    assert "PREVIEW" in preview
    assert not (tmp_vault / "00_Inbox" / filename).exists()
    
    # Test creation (force=True)
    result = tools.create_note(filename, content=content, force=True, folder="00_Inbox")
    assert "created" in result
    
    file_path = tmp_vault / "00_Inbox" / filename
    assert file_path.exists()
    assert content in file_path.read_text(encoding="utf-8")

def test_edit_note_replacement(tmp_vault, mock_config):
    """Test editing a note using text replacement."""
    filename = "Edit_Test.md"
    original_content = "Hello World\nThis is a test.\nGoodbye."
    (tmp_vault / "00_Inbox" / filename).write_text(original_content, encoding="utf-8")
    
    # Replace "test" with "successful test"
    tools.edit_note(
        filename, 
        old_text="This is a test.", 
        new_text="This is a successful test.", 
        force=True
    )
    
    new_content = (tmp_vault / "00_Inbox" / filename).read_text(encoding="utf-8")
    assert "This is a successful test." in new_content
    assert "Hello World" in new_content

def test_search_vault(tmp_vault, tmp_db, mock_config, sample_notes):
    """Test searching the vault."""
    # Index the sample notes first
    for filename, content in sample_notes.items():
        db.upsert_note(filename, str(tmp_vault / filename), filename, "", "hash", content)
    
    # Search for "Intelligence"
    results = tools.search_vault("Intelligence", include_graph=False, include_fts=True)
    assert "AI_Overview.md" in results

def test_find_related_notes(tmp_vault, tmp_db, mock_config):
    """Test finding related notes."""
    source = "Source.md"
    target = "Target.md"
    db.upsert_note(source, "/p", "Source", "", "h", "c")
    db.upsert_note(target, "/p", "Target", "", "h", "c")
    db.add_edge(source, target, "links_to")
    
    result = tools.find_related_notes(source)
    assert target in result
    assert "links_to" in result
