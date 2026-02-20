
import pytest
import sqlite3
from obsidian_mcp import db

def test_init_db(tmp_db):
    """Test that database schema is initialized correctly."""
    with sqlite3.connect(tmp_db) as conn:
        cursor = conn.cursor()
        
        # Check tables exist
        tables = ["notes", "edges", "claims", "repo_mappings"]
        for table in tables:
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
            assert cursor.fetchone() is not None

def test_upsert_and_get_note(tmp_db, mock_config):
    """Test inserting and retrieving a note."""
    filename = "Test_Note.md"
    content = "# Hello World"
    content_hash = db.get_content_hash(content)
    
    db.upsert_note(
        filename=filename,
        path="/path/to/Test_Note.md",
        title="Test Note",
        folder="10_Projects",
        content_hash=content_hash,
        content=content
    )
    
    note = db.get_note_by_filename(filename)
    assert note is not None
    assert note["filename"] == filename
    assert note["title"] == "Test Note"
    assert note["content_hash"] == content_hash

def test_needs_reindex(tmp_db, mock_config):
    """Test content hash change detection."""
    filename = "Reindex_Test.md"
    content_v1 = "Version 1"
    hash_v1 = db.get_content_hash(content_v1)
    
    # First insert
    db.upsert_note(filename, "/path", "Title", "Folder", hash_v1, content_v1)
    
    # Same content -> no reindex
    assert db.needs_reindex(filename, hash_v1) is False
    
    # Changed content -> needs reindex
    content_v2 = "Version 2"
    hash_v2 = db.get_content_hash(content_v2)
    assert db.needs_reindex(filename, hash_v2) is True
    
    # New file -> needs reindex
    assert db.needs_reindex("New_File.md", "somehash") is True

def test_add_edge_and_connections(tmp_db, mock_config):
    """Test adding edges and retrieving connections."""
    # Add nodes first (implicit in some implementations, but good to be explicit for fkey constraints if any)
    # The current schema doesn't strictly enforce FKs on filenames for edges, but let's be safe
    
    source = "Source.md"
    target = "Target.md"
    
    db.add_edge(source, target, "links_to")
    
    connections = db.get_connections(source)
    
    # Check outlinks
    assert len(connections["outlinks"]) == 1
    assert connections["outlinks"][0]["target"] == target
    assert connections["outlinks"][0]["relation"] == "links_to"
    
    # Check backlinks from target perspective
    backlinks = db.get_connections(target)
    assert len(backlinks["backlinks"]) == 1
    assert backlinks["backlinks"][0]["source"] == source

def test_search_fts(tmp_db, mock_config):
    """Test full-text search."""
    db.upsert_note(
        "Search_Test.md", 
        "/path", 
        "Search Test", 
        "Inbox", 
        "hash", 
        "This is a unique keyword: banana"
    )
    
    results = db.search_fts("banana")
    assert len(results) == 1
    assert results[0]["filename"] == "Search_Test.md"

def test_get_stats(tmp_db, mock_config):
    """Test graph statistics."""
    db.upsert_note("N1.md", "/p", "T1", "F1", "h", "c")
    db.upsert_note("N2.md", "/p", "T2", "F2", "h", "c")
    db.add_edge("N1.md", "N2.md", "related")
    
    stats = db.get_stats()
    assert stats["total_notes"] == 2
    assert stats["total_edges"] == 1
