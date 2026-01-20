# Roadmap: Agentic Second Brain

**Vision:** Transform the Obsidian MCP from a passive knowledge graph indexer into an active **Strategist Agent** that analyzes your work, identifies priorities, and proactively prepares research for your review.

---

## Design Philosophy

### Core Principles
- **Developer-First**: CLI and MCP tool-based, integrates with existing workflows
- **Inbox-Driven**: Agent populates `00_Inbox` with priorities, research, and drafts rather than silently modifying notes
- **Balanced Trust**: Can auto-organize and link, but requires approval for external actions (commits, posts)
- **Structured Graph**: Continue using SQLite Knowledge Graph + FTS (no vector DB complexity)

### Interaction Model
The agent acts as a **Chief of Staff**:
1. Monitors your dev workflows (GitHub, Jira, local repos)
2. Analyzes project notes and identifies gaps
3. Drafts priorities, research, and skeleton notes in `00_Inbox`
4. Waits for you to approve/expand/reject proposals

---

## Current State (v0.1)

✅ **Implemented:**
- Hybrid search (ripgrep + FTS + knowledge graph)
- Smart indexing (only processes modified files)
- 8 MCP tools: `search_vault`, `read_note`, `find_related_notes`, `create_note`, `edit_note`, `apply_wikilink`, `append_to_daily`, `vault_stats`, `index_vault`
- Gemini-based claim extraction and relationship mapping
- Systemd timer for background indexing every 4 hours

---

## Phase 1: Deep Developer Integration

**Goal:** Connect the Second Brain to your active development context.

### 1.1 Repo-Vault Mapping System
**Status:** 🟢 Complete

**Description:**
- Define a `repo_mapping.yaml` in `99_System/AI_Context/` that links vault folders to local git repos
- Example:
  ```yaml
  mappings:
    - vault_path: "10_Projects/OVI"
      repo_path: "~/Projects/dev/ovi"
      github: "anomalyco/ovi"
    - vault_path: "10_Projects/Accurkardia"
      repo_path: "~/Projects/dev/accurkardia"
      jira_project: "AK"
  ```
- Store this mapping in SQLite for fast lookup
- Add `get_repo_for_note(filename)` helper function

**Tools/Commands:**
- Leverage `gh` CLI for GitHub operations
- Leverage `acli` for Jira operations (already configured)

**Deliverables:**
- [ ] `repo_mapping.yaml` schema and parser
- [ ] SQLite table for repo mappings
- [ ] Helper functions in `db.py`
- [ ] Documentation in README

---

### 1.2 Automated Pulse Scans
**Status:** 🟢 Complete

**Description:**
- A new MCP tool `pulse_scan(project_name)` that gathers:
  - Recent commits (`git log --since="7 days ago"`)
  - Open PRs (`gh pr list`)
  - Active Jira tickets (`acli jira workitem search --jql "project=X AND status!=Done"`)
  - Local file changes (`git status`)
- Writes a timestamped summary to `00_Inbox/Pulse - [Project] - [Date].md`

**Deliverables:**
- [ ] New `pulse_scan` MCP tool in `server.py`
- [ ] Integration with `gh` CLI
- [ ] Integration with `acli` Jira CLI
- [ ] Template for pulse scan output
- [ ] Systemd timer option for automated scans (optional)

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

**Description:**
- New MCP tool `generate_daily_strategy()`:
  - Analyzes `Project Index.md` and active tickets
  - Identifies top 3-5 priority items based on:
    - Jira ticket due dates
    - GitHub PR review requests
    - Recent activity in dev logs
  - Creates `00_Inbox/Daily Strategy - [Date].md` with:
    - Recommended focus areas
    - Blocking issues
    - Quick wins
- User reviews and moves items to `50_Journal/[Date].md` or project notes

**Deliverables:**
- [ ] `generate_daily_strategy()` MCP tool
- [ ] LLM prompt for priority analysis
- [ ] Template for Daily Strategy notes
- [ ] Integration with Jira/GitHub APIs

---

### 2.2 Gap Analysis
**Status:** 🟢 Complete

**Description:**
- New MCP tool `analyze_gaps(project_name)`:
  - Scans project notes for:
    - Broken wikilinks (`[[Note That Doesn't Exist]]`)
    - Stub notes (< 100 chars of content)
    - Concepts mentioned in code/tickets but not documented
  - Creates `00_Inbox/Research Opportunities - [Project].md` with a ranked list
  - For each gap, drafts a skeleton note with:
    - Placeholder frontmatter
    - Context from where it was referenced
    - Suggested research sources

**Deliverables:**
- [ ] `analyze_gaps()` MCP tool
- [ ] Broken link detection algorithm
- [ ] Stub note identification
- [ ] Skeleton note generation with templates

---

### 2.3 Drafting Loop
**Status:** 🔴 Not Started

**Description:**
- When a gap is identified, the agent:
  1. Creates a **draft note** in `00_Inbox/Drafts/`
  2. Uses Gemini to populate a basic outline (3-5 bullet points)
  3. Adds `status: Draft` to frontmatter
  4. Notifies user via `append_to_daily()`
- User can:
  - Accept: Move to proper folder and expand
  - Reject: Delete or archive
  - Defer: Leave in inbox for later

**Deliverables:**
- [ ] `00_Inbox/Drafts/` folder convention
- [ ] `create_draft_note(topic, context)` helper
- [ ] LLM prompt for outline generation
- [ ] Notification system

---

## Phase 3: Proactive Research & Verification

**Goal:** Agent assists with fact-finding and quality control.

### 3.1 Web Clip Synthesis (Already Implemented)
**Status:** 🟢 Complete

**Notes:**
- User is already using web clip workflow
- Continue current process
- Future: Agent could suggest related clips based on current project context

---

### 3.2 Claim Verification
**Status:** 🔴 Not Started

**Description:**
- New MCP tool `verify_claims(note_name)`:
  - Extracts factual claims from a note
  - Cross-references with:
    - Other notes in the vault
    - External sources (optional web search)
    - Timestamps/dates for staleness detection
  - Flags potential issues:
    - Contradictions between notes
    - Outdated information (e.g., API docs from 2020)
    - Missing citations
  - Creates `00_Inbox/Verification Report - [Note].md`

**Deliverables:**
- [ ] `verify_claims()` MCP tool
- [ ] Claim extraction from notes
- [ ] Cross-reference logic
- [ ] Staleness detection (based on `created` frontmatter)
- [ ] Report template

---

### 3.3 Web Search Integration (Future)
**Status:** 🟡 Deferred

**Notes:**
- Wait until Phases 1-2 are complete
- Consider Tavily/Serper API integration
- Use case: Agent searches for answers to questions in your notes

---

## Phase 4: Advanced Graph Reasoning

**Goal:** Unlock the full potential of the knowledge graph.

### 4.1 Inference Engine
**Status:** 🔴 Not Started

**Description:**
- New MCP tool `find_hidden_connections(topic)`:
  - Uses graph traversal to find indirect relationships
  - Example queries:
    - "What concepts connect Project A and Project B?"
    - "What skills from past projects apply to this new ticket?"
    - "Where have I solved similar problems before?"
  - Returns a ranked list of connections with explanations

**Deliverables:**
- [ ] Graph traversal algorithms (BFS/DFS)
- [ ] Semantic similarity scoring
- [ ] Connection explanation generator
- [ ] Integration with MCP tools

---

### 4.2 Natural Language CLI
**Status:** 🔴 Not Started

**Description:**
- Interactive mode: `obsidian-mcp --chat`
- User can ask questions in natural language:
  - "What's blocking the OVI project?"
  - "Summarize my work on Tailwind this month"
  - "What should I focus on today?"
- Agent uses graph + dev tools (gh/acli) to answer
- Optionally saves the Q&A to journal

**Deliverables:**
- [ ] `--chat` CLI mode
- [ ] Natural language query parser
- [ ] Response generation with citations
- [ ] Session persistence

---

### 4.3 Multi-Hop Reasoning
**Status:** 🔴 Not Started

**Description:**
- Agent can answer complex questions requiring multiple steps:
  - "What technologies from the Research Dashboard project could be reused in Accurkardia?"
  - Requires: (1) List Research Dashboard tech stack, (2) List Accurkardia requirements, (3) Find overlap
- Uses chain-of-thought prompting with Gemini
- Cites all intermediate steps

**Deliverables:**
- [ ] Chain-of-thought prompt templates
- [ ] Multi-step reasoning pipeline
- [ ] Citation tracking

---

## Implementation Priority

### **Next Sprint (Immediate)**
1. ✅ Smart Indexing (Complete)
2. ✅ Repo-Vault Mapping System (Phase 1.1)
3. ✅ Automated Pulse Scans (Phase 1.2)

### **Short-Term (Next 2-4 weeks)**
4. ✅ Priority Synthesis (Phase 2.1)
5. ✅ Gap Analysis (Phase 2.2)
6. Dev Log Integration (Phase 1.3)

### **Medium-Term (1-3 months)**
7. Drafting Loop (Phase 2.3)
8. Claim Verification (Phase 3.2)
9. Inference Engine (Phase 4.1)

### **Long-Term (3+ months)**
10. Natural Language CLI (Phase 4.2)
11. Multi-Hop Reasoning (Phase 4.3)
12. Web Search Integration (Phase 3.3)

---

## Success Metrics

### Quantitative
- **Time to Priority**: How fast can the agent generate a daily priority list?
- **Gap Discovery Rate**: How many broken links/stubs are identified per week?
- **Pulse Scan Completeness**: % of active projects with weekly pulse scans
- **Research Hit Rate**: % of drafted notes that are accepted vs rejected

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

---

## Next Steps

1. **Immediate**: Fix the 650+ broken links identified by Gap Analysis.
2. **This Week**: Implement Dev Log Integration (Phase 1.3) to make the pulse scans smarter.
3. **Next Week**: Begin Drafting Loop (Phase 2.3) for stub expansion.

---

**Last Updated:** 2026-01-20
**Version:** 0.2.1-implemented
**Maintainer:** Jishnu
