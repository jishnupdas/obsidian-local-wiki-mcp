# Obsidian MCP Server

MCP (Model Context Protocol) server for Obsidian Second Brain integration. Provides AI agents (OpenCode, Claude, Gemini CLI) with tools to search, read, create, and curate your knowledge base.

## Quick Start

Once configured in your AI agent, try these prompts:

**Search your knowledge base:**
```
Search my vault for "machine learning"
```

**Explore connections:**
```
What notes are related to "Signal Processing"?
```

**Add a quick thought:**
```
Add to my daily note: Remember to review the Kalman Filter implementation
```

**Check vault health:**
```
Show me vault statistics
```

## Architecture

**Two-System Design:**

1. **The Heartbeat** (Background): Cron-driven indexer extracts claims/connections via Gemini CLI → SQLite knowledge graph
2. **The Toolbox** (On-Demand): MCP server with 8 tools for vault manipulation

## Installation

```bash
cd ~/Projects/obsidian-mcp

# Install dependencies
uv sync

# Copy and configure environment
cp .env.example .env
# Edit .env to set your vault path
```

## Usage

### Run MCP Server (for OpenCode)
```bash
uv run python -m obsidian_mcp.server
```

### Run Indexer
```bash
# Incremental (only changed files)
uv run python -m obsidian_mcp.server --index

# Full rebuild
uv run python -m obsidian_mcp.server --index --full

# Limit to N files (for testing)
uv run python -m obsidian_mcp.server --index --limit 20

# Show stats
uv run python -m obsidian_mcp.server --stats

# Show config
uv run python -m obsidian_mcp.server --config
```

### Enable Background Indexing (systemd)
```bash
systemctl --user daemon-reload
systemctl --user enable obsidian-indexer.timer
systemctl --user start obsidian-indexer.timer

# Check status
systemctl --user status obsidian-indexer.timer
journalctl --user -u obsidian-indexer.service
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `search_vault` | Hybrid search: ripgrep + FTS + knowledge graph |
| `read_note` | Read full content of a note |
| `find_related_notes` | Get outlinks, backlinks, and relationships |
| `create_note` | Create new note with template (requires `force=True`) |
| `edit_note` | Edit existing note: text replacement or section update (requires `force=True`) |
| `apply_wikilink` | Convert plain text to `[[WikiLink]]` (requires `force=True`) |
| `append_to_daily` | Append timestamped entry to journal (requires `force=True`) |
| `vault_stats` | Get knowledge graph statistics |

## Usage Examples

### Search & Discovery

**Find notes about a topic:**
```
Search my vault for "signal processing"
```
Uses hybrid search combining ripgrep, FTS5, and knowledge graph.

**Explore a concept's connections:**
```
What notes are related to "Fourier Transform"?
```
Returns backlinks, outlinks, and relationship types (prerequisite, application_of, etc.)

### Reading & Context

**Read a specific note:**
```
Read my note on "Kalman Filter"
```

**Research before answering:**
```
Based on my notes, explain how I've documented the ECG processing pipeline
```
Agent searches vault, reads relevant notes, synthesizes from YOUR knowledge.

### Writing & Curation

**Create a concept note:**
```
Create a concept note about "Wavelet Transform" in 30_Resources/Concepts
```
Uses vault templates, shows preview first, creates with `force=True`.

**Quick capture to journal:**
```
Add to my daily note: "Idea - use attention mechanism for QRS detection"
```
Appends timestamped entry under "Inbox / Quick Captures".

**Build knowledge graph links:**
```
In my ECG_Processing.md note, link "bandpass filter" to the Bandpass_Filter concept
```
Converts plain text to `[[WikiLink]]` to strengthen the graph.

**Edit an existing note:**
```
In my Kalman_Filter note, update the "## Summary" section with a clearer explanation
```
Supports text replacement or section-based updates with preview mode.

### Workflow Examples

**Research workflow:**
```
I'm writing about adaptive filtering. Search my vault for relevant notes,
read the top 3, and summarize what I already know.
```

**Learning integration:**
```
I just learned about Hilbert Transform. Create a concept note for it,
and add a quick capture to my daily note that I studied this today.
```

**Knowledge audit:**
```
Show vault stats. Which concepts have the most connections?
Are there any orphan notes I should link?
```

## OpenCode Configuration

Add to `~/.config/opencode/opencode.json`:

```json
{
  "mcp": {
    "obsidian": {
      "type": "local",
      "command": [
        "uv", "run", "--directory", "/home/jishnu/Projects/obsidian-mcp",
        "python", "-m", "obsidian_mcp.server"
      ],
      "enabled": true
    }
  }
}
```

## Configuration

Edit `.env` or set environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `VAULT_PATH` | `~/Projects/project-sb` | Path to Obsidian vault |
| `DB_PATH` | `{vault}/.obsidian/vault_graph.db` | SQLite database location |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Model for indexer |
| `BATCH_SIZE` | `25000` | Characters per LLM batch |
| `JOURNAL_FOLDER` | `50_Journal` | Daily notes folder |

## Relationship Types

The indexer extracts 18 semantic relationship types:

- **Core**: `prerequisite`, `application_of`, `analogy_to`, `opposes`, `extends`, `part_of`
- **Project**: `implements`, `documents`, `cites`, `supersedes`
- **Workflow**: `triggers`, `constrains`
- **Data**: `measures`, `derived_from`
- **Graph**: `bridges`, `example_of`, `links_to`, `related`

## Requirements

- Python 3.11+
- uv (Python package manager)
- Gemini CLI (`npm install -g @google/gemini-cli`)
- ripgrep (`rg`)

## License

MIT
