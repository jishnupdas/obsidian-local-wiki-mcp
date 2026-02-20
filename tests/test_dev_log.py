import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime
from obsidian_mcp import dev_log

@pytest.fixture
def sample_dev_log(tmp_vault):
    """Create a sample Dev Log file."""
    project_dir = tmp_vault / "10_Projects" / "TestProject"
    project_dir.mkdir(parents=True, exist_ok=True)
    
    log_path = project_dir / "Dev Log.md"
    log_path.write_text("""---
tags: [project]
---
# 🏗️ TestProject

## 📝 Executive Summary
Summary here.

## 📜 Activity Log

### 2023-01-01
- Initial commit
""", encoding="utf-8")
    return log_path

def test_append_to_dev_log_existing_section(tmp_vault, sample_dev_log):
    """Test appending to an existing Activity Log section."""
    project_dir = sample_dev_log.parent
    
    dev_log.append_to_dev_log(project_dir, "New entry")
    
    content = sample_dev_log.read_text("utf-8")
    assert "New entry" in content
    assert "## 📜 Activity Log" in content
    # Should be at the end or under the section
    assert content.index("New entry") > content.index("Activity Log")

def test_append_to_dev_log_creates_section(tmp_vault):
    """Test creating the Activity Log section if it's missing."""
    project_dir = tmp_vault / "10_Projects" / "NoSectionProject"
    project_dir.mkdir(parents=True, exist_ok=True)
    log_path = project_dir / "Dev Log.md"
    log_path.write_text("# Project\n\nSome content.", encoding="utf-8")
    
    dev_log.append_to_dev_log(project_dir, "First log entry")
    
    content = log_path.read_text("utf-8")
    assert "## 📜 Activity Log" in content
    assert "First log entry" in content

def test_append_to_dev_log_creates_file(tmp_vault):
    """Test creating a new Dev Log file if it doesn't exist."""
    project_dir = tmp_vault / "10_Projects" / "NewProject"
    # Don't create directory or file yet (function should handle dir creation if needed? 
    # well, project dir usually exists. lets assume project dir exists)
    project_dir.mkdir(parents=True, exist_ok=True)
    
    dev_log.append_to_dev_log(project_dir, "Zero state entry")
    
    log_path = project_dir / "Dev Log.md"
    assert log_path.exists()
    content = log_path.read_text("utf-8")
    assert "# 🏗️ NewProject" in content # Default title
    assert "## 📜 Activity Log" in content
    assert "Zero state entry" in content

def test_extract_action_items(tmp_vault):
    """Test extracting TODO/BLOCKED items."""
    content = """
    # Log
    - TODO: Fix bug #123
    - [ ] Another task
    - BLOCKED: Waiting for API key
    - Done task
    """
    
    items = dev_log.extract_action_items(content)
    
    assert len(items) == 3
    assert "- TODO: Fix bug #123" in items
    assert "- [ ] Another task" in items # Maybe supported?
    assert "- BLOCKED: Waiting for API key" in items
    assert "Done task" not in items
