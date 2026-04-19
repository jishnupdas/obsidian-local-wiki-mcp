# obsidian-local-wiki-mcp

An MCP (Model Context Protocol) server that gives AI agents direct access to your [Obsidian](https://obsidian.md) vault. Search, read, write, and navigate your personal knowledge base from within any MCP-compatible AI agent (Claude, OpenCode, Gemini CLI, and others).

## What It Does

- **Hybrid Search** — Combines ripgrep (exact match), SQLite FTS5 (full-text), and a knowledge graph (semantic connections)
- **Knowledge Graph** — Background indexer uses Gemini CLI to extract relationships between concepts across your notes
- **Full Vault Access** — Read, create, and edit notes; append to daily journals; apply wikilinks
- **Dev Workflow Integration** — Connect vault folders to git repos, GitHub, and Jira for automated project pulse scans
- **Context Injection** — Automatically inject relevant vault context into AI agent sessions via a `BeforeAgent` hook

---

## Table of Contents

1. [Installation](#installation)
2. [Configuration](#configuration)
3. [AI Agent Integration](#ai-agent-integration)
4. [Building the Knowledge Graph](#building-the-knowledge-graph)
5. [MCP Tools Reference](#mcp-tools-reference)
6. [Usage Examples](#usage-examples)
7. [Dev Workflow Integration](#dev-workflow-integration)
8. [Context Hook (BeforeAgent)](#context-hook-beforeagent)
9. [Vector Search (Optional)](#vector-search-optional)
10. [Background Indexing (systemd)](#background-indexing-systemd)
11. [Architecture](#architecture)

---

## Installation

### Prerequisites

| Tool | Install |
|------|---------|
| Python 3.11+ | [python.org](https://www.python.org/downloads/) |
| [uv](https://docs.astral.sh/uv/) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| [Gemini CLI](https://github.com/google-gemini/gemini-cli) | `npm install -g @google/gemini-cli` |
| [ripgrep](https://github.com/BurntSushi/ripgrep) | `apt install ripgrep` / `brew install ripgrep` |

### Clone and Install

```bash
git clone https://github.com/your-username/obsidian-local-wiki-mcp
cd obsidian-local-wiki-mcp
uv sync
```

---

## Configuration

Copy the example environment file and edit it to point at your vault:

```bash
cp .env.example .env
```

```env
# Minimum required: path to your Obsidian vault
VAULT_PATH=~/Documents/MyVault
```

Full configuration reference:

| Variable | Default | Description |
|---|---|---|
| `VAULT_PATH` | `~/Projects/project-sb` | Path to your Obsidian vault |
| `DB_PATH` | `{vault}/.obsidian/vault_graph.db` | SQLite database location |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Model for the knowledge graph indexer |
| `BATCH_SIZE` | `25000` | Characters per LLM batch during indexing |
| `JOURNAL_FOLDER` | `50_Journal` | Vault folder for daily notes |
| `JOURNAL_DATE_FORMAT` | `%Y-%m-%d` | Date format for daily note filenames |
| `JIRA_BASE_URL` | _(empty)_ | Your Jira instance URL (e.g. `https://your-org.atlassian.net`) |
| `VECTOR_MODEL` | `BAAI/bge-small-en-v1.5` | Embedding model for semantic search |
| `VECTOR_CHUNK_SIZE` | `1500` | Characters per embedding chunk |

Verify your configuration at any time:

```bash
uv run obsidian-mcp --config
```

---

## AI Agent Integration

Replace `/path/to/obsidian-local-wiki-mcp` with the absolute path where you cloned this repo.

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "obsidian": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/obsidian-local-wiki-mcp",
        "obsidian-mcp"
      ]
    }
  }
}
```

### Claude Code (CLI)

Add to your project's `.mcp.json` or `~/.claude/mcp.json`:

```json
{
  "mcpServers": {
    "obsidian": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/obsidian-local-wiki-mcp",
        "obsidian-mcp"
      ]
    }
  }
}
```

### OpenCode

Add to `~/.config/opencode/opencode.json`:

```json
{
  "mcp": {
    "obsidian": {
      "type": "local",
      "command": [
        "uv",
        "run",
        "--directory",
        "/path/to/obsidian-local-wiki-mcp",
        "obsidian-mcp"
      ],
      "enabled": true
    }
  }
}
```

### Gemini CLI

Add to `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "obsidian": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/obsidian-local-wiki-mcp",
        "obsidian-mcp"
      ]
    }
  }
}
```

---

## Building the Knowledge Graph

Before searching by semantic relationships, build the knowledge graph index. The indexer runs Gemini CLI on your vault notes and stores extracted relationships in SQLite.

```bash
# First run: full index of all notes
uv run obsidian-mcp --index --full

# Subsequent runs: only process new/modified files (fast)
uv run obsidian-mcp --index

# Check index statistics
uv run obsidian-mcp --stats

# Search directly from the CLI (for testing)
uv run obsidian-mcp --search "your query"
uv run obsidian-mcp --search "your query" --no-semantic  # skip semantic results
```

The indexer is intentionally incremental — it skips unchanged files using content hashing, so re-runs are fast.

---

## MCP Tools Reference

### Core Knowledge Tools

| Tool | Description |
|---|---|
| `search_vault` | Hybrid search: ripgrep + FTS5 + knowledge graph |
| `read_note` | Read full content of a note by filename |
| `find_related_notes` | Get outlinks, backlinks, and relationship types for a note |
| `vault_stats` | Knowledge graph statistics and health metrics |

### Writing Tools

All write operations require `force=True` to apply. Without it, the tool returns a preview so you can confirm before committing.

| Tool | Description |
|---|---|
| `create_note` | Create a new note with frontmatter (uses vault templates) |
| `edit_note` | Edit a note: text replacement or section update |
| `apply_wikilink` | Convert plain text into `[[WikiLink]]` |
| `append_to_daily` | Append a timestamped entry to today's daily journal |

### Indexing

| Tool | Description |
|---|---|
| `index_vault` | Re-index files matching a query or glob pattern |

### Obsidian Native Tools

These require the [Obsidian Local REST API](https://github.com/coddingtonbear/obsidian-local-rest-api) community plugin to be installed and running.

| Tool | Description |
|---|---|
| `open_in_obsidian` | Open a specific note in the Obsidian app |
| `obsidian_search_native` | Use Obsidian's native search syntax (tags, paths, aliases) |
| `get_graph_context` | Get 1-depth structural graph: outlinks + backlinks |

### Dev Workflow Tools

| Tool | Description |
|---|---|
| `load_repo_mappings` | Load `repo_mapping.yaml` into the database |
| `list_repo_mappings` | List all configured project mappings |
| `verify_repo_mappings` | Check each mapping's status (path exists, git repo, etc.) |
| `pulse_scan` | Gather git/GitHub/Jira activity for a project |
| `onboard_project` | Create a Dev Log and update Project Index for a repo |
| `append_to_dev_log` | Add an entry to a project's Dev Log |
| `generate_daily_strategy` | Synthesize daily priorities from recent pulse scans |
| `analyze_gaps` | Find broken wikilinks, stub notes, and orphan notes |
| `deep_onboard` | Autonomous repo analysis with vault integration |

---

## Usage Examples

### Searching Your Knowledge Base

```
Search my vault for "machine learning"
```

```
What notes are related to "Transformer architecture"?
```

```
Find everything I've written about signal processing
```

Uses hybrid search combining ripgrep (exact text), FTS5 (full-text), and knowledge graph connections.

### Reading Notes and Getting Context

```
Read my note on "Kalman Filter"
```

```
Based on my notes, explain how I've documented the data pipeline
```

The agent searches the vault, reads relevant notes, and synthesizes an answer from your own knowledge base.

### Writing and Curation

```
Create a concept note about "Attention Mechanism" in 30_Resources/Concepts
```

```
Add to my daily note: "Reviewed the new PyTorch 2.0 paper"
```

```
In my Neural_Networks.md note, link "gradient descent" to the Gradient_Descent note
```

```
Update the "## Summary" section of my Kalman_Filter note with a cleaner explanation
```

### Knowledge Audits

```
Show vault stats. Which concepts have the most connections?
```

```
Find broken wikilinks and orphan notes I should link
```

---

## Dev Workflow Integration

Connect vault folders to your git repositories, GitHub, and Jira for automated project tracking.

### Step 1: Create Your Mapping File

```bash
cp repo_mapping.yaml.example repo_mapping.yaml
```

Edit `repo_mapping.yaml`:

```yaml
mappings:
  - vault_path: "10_Projects/MyProject"
    repo_path: "~/Projects/my-project"
    github: "your-org/my-project"
    jira_project: "MP"           # or null if not using Jira
    description: "My main project"
    active: true
```

Set `JIRA_BASE_URL` in `.env` if you use Jira:

```env
JIRA_BASE_URL=https://your-org.atlassian.net
```

### Step 2: Load the Mappings

```bash
uv run obsidian-mcp --load-mappings

# Or from within an AI agent session:
# "Load my repo mappings"
```

### Step 3: Run Pulse Scans

```bash
uv run obsidian-mcp --pulse "10_Projects/MyProject"
```

Or ask your agent:

```
Run a pulse scan for "10_Projects/MyProject"
```

The pulse scan gathers recent git commits, open GitHub PRs, open Jira tickets, and project structure, then saves a formatted Markdown note to your vault.

### Step 4: Generate Daily Strategy

```
Generate today's strategy note
```

This synthesizes priorities from recent pulse scans across all active projects and saves a `Daily Strategy` note to your inbox.

---

## Context Hook (BeforeAgent)

The context hook automatically injects relevant vault context at the start of each AI agent session, based on keywords in your prompt.

### Gemini CLI Setup

Copy the example settings file:

```bash
cp settings.json.example ~/.gemini/settings.json
```

Then edit `~/.gemini/settings.json` to update the directory path:

```json
{
  "hooks": {
    "beforeAgent": {
      "command": [
        "uv",
        "run",
        "--directory",
        "/path/to/obsidian-local-wiki-mcp",
        "obsidian-mcp",
        "--context-hook",
        "${prompt}"
      ]
    }
  }
}
```

When you type a prompt mentioning a project name (matched against your `repo_mapping.yaml`), the hook reads the project's Dev Log and injects a tactical briefing into the session context automatically.

### OpenCode Setup

Copy the `settings.json.example` to your OpenCode config directory and follow the same pattern.

---

## Vector Search (Optional)

Enable semantic search using local embeddings — no API key required, all processing happens on your machine.

```bash
# Install with vector extras (~85MB ONNX model download on first use)
uv sync --extra vector

# Rebuild the index to generate embeddings
uv run obsidian-mcp --index --full
```

Uses `BAAI/bge-small-en-v1.5` via ONNX runtime (no PyTorch required). Once indexed, `search_vault` automatically includes a `SEMANTIC MATCHES` section in results. Disable per-query with `include_semantic=False`.

---

## Background Indexing (systemd)

Keep the knowledge graph up to date automatically with a systemd timer:

```bash
# Enable and start the background timer
systemctl --user daemon-reload
systemctl --user enable obsidian-indexer.timer
systemctl --user start obsidian-indexer.timer

# Monitor
systemctl --user status obsidian-indexer.timer
journalctl --user -u obsidian-indexer.service
```

The timer runs an incremental index every 4 hours, processing only files modified since the last run.

---

## Architecture

```
obsidian-local-wiki-mcp/
├── src/obsidian_mcp/
│   ├── server.py        # MCP server + CLI entrypoint, all tool registrations
│   ├── tools.py         # Core vault tools (search, read, write)
│   ├── indexer.py       # Gemini CLI knowledge graph indexer
│   ├── db.py            # SQLite layer: FTS5, knowledge graph, vector store
│   ├── config.py        # Environment-based configuration
│   ├── pulse.py         # Git / GitHub / Jira activity gathering
│   ├── hooks.py         # BeforeAgent context injection engine
│   ├── vectors.py       # Local vector embeddings (optional)
│   ├── onboarding.py    # Project Dev Log creation
│   ├── strategy.py      # Daily strategy generation
│   ├── gaps.py          # Knowledge gap analysis
│   └── dev_log.py       # Dev Log append/parse helpers
├── .env.example         # Configuration template
├── repo_mapping.yaml.example  # Project mapping template
└── settings.json.example      # AI agent hook config template
```

**Two-system design:**

1. **The Heartbeat** — Background cron indexer. Reads vault notes in batches, calls Gemini CLI to extract semantic relationships (claims, connections, concept links), and stores them in a SQLite knowledge graph. Runs every 4 hours via systemd, skipping unchanged files.

2. **The Toolbox** — On-demand MCP server. Exposes tools for searching, reading, writing, and navigating the vault using the knowledge graph. Starts instantly and handles MCP requests from your AI agent.

### Relationship Types

The indexer extracts 18 semantic relationship types:

| Category | Types |
|---|---|
| Core | `prerequisite`, `application_of`, `analogy_to`, `opposes`, `extends`, `part_of` |
| Project | `implements`, `documents`, `cites`, `supersedes` |
| Workflow | `triggers`, `constrains` |
| Data | `measures`, `derived_from` |
| Graph | `bridges`, `example_of`, `links_to`, `related` |

---

## Requirements

- Python 3.11+
- uv
- Gemini CLI (`npm install -g @google/gemini-cli`) — for knowledge graph indexing
- ripgrep (`rg`) — for fast exact-text search
- GitHub CLI (`gh`) — optional, for pulse scan GitHub integration
- Atlassian CLI (`acli`) — optional, for pulse scan Jira integration

---

## License

MIT
