# Roadmap: Agentic Second Brain

**Vision:** Transform the Obsidian MCP from a passive knowledge graph indexer into an active **Strategist Agent** that analyzes your work, identifies priorities, and proactively prepares research for your review.

---

## Design Philosophy

### Core Principles

- **Developer-First**: CLI and MCP tool-based, integrates with existing workflows
- **Inbox-Driven**: Agent populates `00_Inbox` with priorities, research, and drafts rather than silently modifying notes
- **Balanced Trust**: Can auto-organize and link, but requires approval for external actions (commits, posts)
- **Structured Graph**: SQLite Knowledge Graph + FTS as foundation; vector search as an opt-in semantic layer

### Interaction Model

The agent acts as a **Chief of Staff**:

1. Monitors your dev workflows (GitHub, Jira, local repos)
2. Analyzes project notes and identifies gaps
3. Drafts priorities, research, and skeleton notes in `00_Inbox`
4. Waits for you to approve/expand/reject proposals

---

## Current State (v0.3.0)

### ✅ Implemented (15 MCP Tools)

| Tool                      | Module                          | Phase |
| :------------------------ | :------------------------------ | :---- |
| `search_vault`            | `tools.py`                      | Core  |
| `read_note`               | `tools.py`                      | Core  |
| `find_related_notes`      | `tools.py`                      | Core  |
| `create_note`             | `tools.py`                      | Core  |
| `edit_note`               | `tools.py`                      | Core  |
| `apply_wikilink`          | `tools.py`                      | Core  |
| `append_to_daily`         | `tools.py`                      | Core  |
| `vault_stats`             | `tools.py`                      | Core  |
| `index_vault`             | `server.py`                     | Core  |
| `load_repo_mappings`      | `server.py` / `repo_manager.py` | 1.1   |
| `list_repo_mappings`      | `server.py` / `repo_manager.py` | 1.1   |
| `verify_repo_mappings`    | `server.py` / `repo_manager.py` | 1.1   |
| `pulse_scan`              | `server.py` / `pulse.py`        | 1.2   |
| `onboard_project`         | `server.py` / `onboarding.py`   | 1.2   |
| `generate_daily_strategy` | `server.py` / `strategy.py`     | 2.1   |
| `analyze_gaps`            | `server.py` / `gaps.py`         | 2.2   |
| `deep_onboard`            | `server.py` / `deep_onboard.py` | Bonus |

### ✅ Infrastructure

- Hybrid search (ripgrep + FTS + knowledge graph)
- Smart indexing (only processes modified files, content hashing)
- Gemini-based claim extraction and relationship mapping
- Systemd timer for background indexing every 4 hours
- Templates system (`concept`, `bridge`, `daily`, `project`, `ticket`, `web_clip`)
- `repo_mapping.yaml` schema with SQLite persistence

### ⚠️ Engineering Gaps

- **No test suite** — zero unit tests, integration tests, or CI pipeline
- Only 2 git commits — history is thin, no tags/releases
- No `vectors.py` module yet (proposed but not implemented)
- No `hooks.py` module yet (proposed but not implemented)

---

## Phase 1: Deep Developer Integration

**Goal:** Connect the Second Brain to your active development context.

### 1.1 Repo-Vault Mapping System

**Status:** 🟢 Complete

Defined `repo_mapping.yaml` → SQLite mapping. `load_repo_mappings`, `list_repo_mappings`, `verify_repo_mappings` tools all implemented in `repo_manager.py`.

---

### 1.2 Automated Pulse Scans & Onboarding

**Status:** 🟢 Complete

- `pulse_scan(project_name)` gathers git log, GitHub PRs, Jira tickets, file changes → writes to `00_Inbox/Pulse - [Project] - [Date].md`
- `onboard_project(repo_path, project_name)` creates `Dev Log.md` and updates `Project Index.md`
- `deep_onboard(repo_path)` performs autonomous repo analysis, LLM-powered categorization, concept extraction, and vault integration

---

### 1.3 Dev Log Integration

**Status:** 🔴 Not Started

**Description:**

- When a `Dev Log.md` exists in a project folder, the agent can:
  - Append today's pulse scan summary
  - Extract recent work items and create backlinks to relevant concept notes
  - Identify "TODO" or "BLOCKED" markers and surface them in a digest

**Deliverables:**

- [ ] `append_to_dev_log(project, content)` helper
- [ ] Parser for `Dev Log.md` structure
- [ ] Integration with pulse scan

---

## Phase 2: The Agentic Inbox & Strategy

**Goal:** The agent actively synthesizes priorities and drafts strategy notes.

### 2.1 Priority Synthesis

**Status:** 🟢 Complete

`generate_daily_strategy()` tool implemented in `strategy.py`. Analyzes recent pulse scans and creates `00_Inbox/Daily Strategy - [Date].md`.

---

### 2.2 Gap Analysis

**Status:** 🟢 Complete

`analyze_gaps(project_name?)` tool implemented in `gaps.py`. Finds broken wikilinks, stub notes, and orphan notes. Returns a markdown report.

---

### 2.3 Drafting Loop

**Status:** 🔴 Not Started

**Description:**

- When a gap is identified, the agent:
  1. Creates a **draft note** in `00_Inbox/Drafts/`
  2. Uses Gemini to populate a basic outline (3-5 bullet points)
  3. Adds `status: Draft` to frontmatter
  4. Notifies user via `append_to_daily()`
- User can: Accept → Move to proper folder | Reject → Delete | Defer → Leave in inbox

**Deliverables:**

- [ ] `00_Inbox/Drafts/` folder convention
- [ ] `create_draft_note(topic, context)` helper
- [ ] LLM prompt for outline generation
- [ ] Notification system

---

## Phase 2.5: Gemini CLI Hook Integration _(NEW)_

**Goal:** Make obsidian-mcp proactive by hooking into the Gemini CLI lifecycle.

> [!NOTE]
> See: `00_Inbox/Implementation Plan - Obsidian MCP Hook Integration.md`

### 2.5.1 Context Ingestion Hook (`BeforeAgent`)

**Status:** � Not Started

**Description:**

- New `hooks.py` module with a `ContextEngine`:
  - Scans user prompts for project keywords
  - Maps keywords to vault paths via `repo_mappings`
  - Extracts "Tactical Briefings" from `Project Home.md`
- CLI subcommand: `obsidian-mcp hooks context --query "..."`

**Deliverables:**

- [ ] `src/obsidian_mcp/hooks.py` with `ContextEngine`
- [ ] Keyword → project mapping with caching
- [ ] `--query` CLI subcommand

---

### 2.5.2 Activity Logging Hook (`AfterTool`)

**Status:** 🔴 Not Started

**Description:**

- `LoggingEngine` in `hooks.py`:
  - Monitors tool outputs (`write_file`, `replace`) for significant changes
  - Generates `systemMessage` suggestions for dev log entries
- CLI subcommand: `obsidian-mcp hooks log --tool "..." --input "..." --response "..."`

**Deliverables:**

- [ ] `LoggingEngine` with heuristic change detection
- [ ] `--log` CLI subcommand
- [ ] `~/.gemini/settings.json` hook configuration template

---

## Phase 3: Proactive Research & Verification

**Goal:** Agent assists with fact-finding and quality control.

### 3.1 Web Clip Synthesis

**Status:** 🟢 Complete (Manual workflow in use)

---

### 3.2 Claim Verification

**Status:** 🔴 Not Started

**Description:**

- New MCP tool `verify_claims(note_name)`:
  - Extracts factual claims from a note
  - Cross-references with other vault notes and timestamps
  - Flags contradictions, outdated info, and missing citations
  - Creates `00_Inbox/Verification Report - [Note].md`

**Deliverables:**

- [ ] `verify_claims()` MCP tool
- [ ] Claim extraction from notes
- [ ] Cross-reference logic
- [ ] Staleness detection (based on `created` frontmatter)
- [ ] Report template

---

### 3.3 Web Search Integration

**Status:** 🟡 Deferred

Consider Tavily/Serper API integration once Phases 1-2 are mature.

---

## Phase 4: Advanced Graph Reasoning

**Goal:** Unlock the full potential of the knowledge graph.

### 4.0 Vector / Semantic Search _(NEW)_

**Status:** 🟡 Proposed — Awaiting Approval

> [!NOTE]
> See: `VECTOR_SEARCH_PROPOSAL.md`

**Description:**

- Add local vector search using **ChromaDB** + **SentenceTransformers** (`all-MiniLM-L6-v2`)
- New module `vectors.py`: `get_chroma_client()`, `upsert_embedding()`, `search_vectors()`
- Integrates into `indexer.py` (compute embeddings on index) and `search_vault` (new semantic results category)
- Enables finding conceptually related notes even without keyword overlap

**Trade-offs:**
| Pros | Cons |
|:---|:---|
| True semantic understanding | +500MB dependencies (`torch`, `chromadb`) |
| Zero API cost (local embeddings) | Slower initial indexing |
| Full privacy — data stays local | Additional DB state to manage |

**Deliverables:**

- [ ] `src/obsidian_mcp/vectors.py`
- [ ] ChromaDB persistence in `VAULT_PATH/.obsidian/chroma_db/`
- [ ] `search_vault` semantic mode flag
- [ ] Lazy migration for existing vaults
- [ ] `vector_store_size` in `vault_stats`

---

### 4.1 Inference Engine

**Status:** 🔴 Not Started

Graph traversal (BFS/DFS) to find hidden connections between concepts across projects.

---

### 4.2 Natural Language CLI

**Status:** 🔴 Not Started

Interactive `obsidian-mcp --chat` mode for querying the vault in natural language.

---

### 4.3 Multi-Hop Reasoning

**Status:** 🔴 Not Started

Chain-of-thought reasoning across multiple vault notes with full citation tracking.

---

## Implementation Priority

### ✅ Completed

1. Smart Indexing (Core)
2. Repo-Vault Mapping (1.1)
3. Automated Pulse Scans & Onboarding (1.2)
4. Priority Synthesis (2.1)
5. Gap Analysis (2.2)
6. Deep Onboarding (Bonus)

### 🔥 Next Up (Immediate)

7. **Test Suite & CI** — Add pytest infrastructure, unit tests for core tools, integration test for indexer
8. **Dev Log Integration (1.3)** — Connect pulse scans to Dev Logs for continuous project awareness
9. **Gemini CLI Hooks (2.5)** — Make the MCP proactive with `BeforeAgent` context injection

### 📋 Short-Term (Next 2-4 weeks)

10. Drafting Loop (2.3)
11. Activity Logging Hook (2.5.2)
12. Vector Search (4.0) — Decide: approve or defer the proposal

### 🗓️ Medium-Term (1-3 months)

13. Claim Verification (3.2)
14. Inference Engine (4.1)

### 🔮 Long-Term (3+ months)

15. Natural Language CLI (4.2)
16. Multi-Hop Reasoning (4.3)
17. Web Search Integration (3.3)

---

## Recommended Next Steps

> [!IMPORTANT]
> The project has strong feature coverage but lacks engineering fundamentals. Before adding more features, solidify the foundation.

### 1. Add Test Infrastructure _(Critical)_

- Create `tests/` directory with `conftest.py` and fixtures
- Add unit tests for `tools.py` functions (at least `search_vault`, `read_note`, `create_note`, `edit_note`)
- Add integration test for the indexer pipeline
- Set up `pytest` in `pyproject.toml` with proper test configuration
- **Why**: No tests means no confidence in refactoring or adding new features safely

### 2. Implement Dev Log Integration (Phase 1.3)

- This is the last remaining Phase 1 item
- Makes pulse scans more actionable by flowing data into project Dev Logs
- Relatively small scope — mostly a new helper + pulse scan integration

### 3. Decide on Vector Search Proposal

- The `VECTOR_SEARCH_PROPOSAL.md` is well-structured and ready for review
- Key decision: is the +500MB dependency weight acceptable for your setup?
- Alternative: use Gemini API embeddings (lighter, but adds API dependency)

### 4. Build Gemini CLI Hooks (Phase 2.5)

- The vault note `Implementation Plan - Obsidian MCP Hook Integration` has a strong plan
- Start with Phase 1 (Context Ingestion) — highest value for lowest effort
- This transforms the MCP from "tool you call" to "agent that helps automatically"

---

## Success Metrics

### Quantitative

- **Time to Priority**: How fast can the agent generate a daily priority list?
- **Gap Discovery Rate**: How many broken links/stubs are identified per week?
- **Pulse Scan Completeness**: % of active projects with weekly pulse scans
- **Research Hit Rate**: % of drafted notes that are accepted vs rejected
- **Test Coverage**: % of core tools covered by unit tests

### Qualitative

- **Trust**: Do you feel confident acting on the agent's recommendations?
- **Relevance**: Are the priorities/research actually useful?
- **Flow**: Does the agent enhance or interrupt your workflow?

---

## Technical Considerations

### API Quotas

- Gemini Flash: Currently free tier (1500 RPD)
- If we exceed limits, consider:
  - Batching more aggressively
  - Caching LLM responses
  - Using cheaper models for routine tasks

### Performance

- Smart indexing already handles 200+ notes in <1s when nothing changed
- Pulse scans should complete in <5s per project
- Daily strategy generation should be <10s

### Error Handling

- Graceful degradation if `gh`/`acli` are unavailable
- Clear error messages in inbox notes if agent fails
- Rollback mechanism for accidental edits

---

## Open Questions

1. **Notification System**: How should the agent notify you about new inbox items?
   - Append to daily journal?
   - System notification?
   - Just let systemd logs handle it?

2. **Conflict Resolution**: If the agent drafts a note but you create one manually with the same name, what happens?

3. **Privacy**: Should the agent avoid indexing certain folders (e.g., `40_Archives/Personal`)?

4. **Versioning**: Should agent-generated notes include a version history?

5. **Vector Search**: Approve the ChromaDB proposal or explore lighter alternatives?

6. **Hook Scope**: Should the `AfterTool` hook auto-log, or always prompt? What's the trust threshold?

---

**Last Updated:** 2026-02-20
**Version:** 0.3.0
**Maintainer:** Jishnu
