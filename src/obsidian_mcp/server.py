#!/usr/bin/env python3
"""
Obsidian MCP Server - Second Brain integration for AI agents.

Usage:
    # Run MCP server (for OpenCode/Claude/etc)
    obsidian-mcp

    # Run indexer
    obsidian-mcp --index
    obsidian-mcp --index --full    # Force full rebuild

    # Show configuration
    obsidian-mcp --config

    # Show statistics
    obsidian-mcp --stats
"""

import sys
import argparse
from datetime import datetime

from mcp.server.fastmcp import FastMCP

from .config import print_config, VAULT_PATH
from .db import init_db, get_last_index_time, get_all_repo_mappings, get_repo_mapping
from .indexer import build_index, get_files_to_index, index_single_note
from .repo_manager import load_mappings_from_yaml, verify_mapping
from .onboarding import onboard_project_logic, update_project_index
from .strategy import generate_daily_strategy_logic
from .gaps import analyze_gaps_logic
from .deep_onboard import deep_onboard_logic
from .pulse import (
    gather_git_info,
    gather_github_info,
    gather_jira_info,
    gather_structural_info,
    format_pulse_markdown,
)
from . import tools
from . import dev_log
from . import hooks

# =============================================================================
# MCP SERVER SETUP
# =============================================================================

mcp = FastMCP(
    "ObsidianMCP",
    instructions="MCP server for Obsidian Second Brain integration. "
    "Provides hybrid search, note creation, wikilink management, "
    "and knowledge graph queries.",
)


# =============================================================================
# REGISTER MCP TOOLS
# =============================================================================


@mcp.tool()
def search_vault(
    query: str, include_graph: bool = True, include_fts: bool = True, limit: int = 10
) -> str:
    """
    Hybrid search across the Obsidian vault.

    Combines:
    - ripgrep for exact text matches
    - SQLite FTS5 for full-text search
    - Knowledge graph for semantic connections

    Use this to gather context before writing or to answer questions.

    Args:
        query: Search term or phrase
        include_graph: Include knowledge graph connections (default: True)
        include_fts: Include full-text search results (default: True)
        limit: Maximum results per category (default: 10)
    """
    return tools.search_vault(query, include_graph, include_fts, limit)


@mcp.tool()
def read_note(filename: str, max_lines: int = 500) -> str:
    """
    Read the full content of a specific note by filename.

    Args:
        filename: Note filename (with or without .md extension)
        max_lines: Maximum lines to return (default: 500)
    """
    return tools.read_note(filename, max_lines)


@mcp.tool()
def find_related_notes(note_name: str) -> str:
    """
    Get all connections for a note from the knowledge graph.

    Returns outlinks (what this note links to) and backlinks
    (what links to this note), along with relationship types.

    Args:
        note_name: Note filename or concept name
    """
    return tools.find_related_notes(note_name)


@mcp.tool()
def create_note(
    filename: str,
    content: str | None = None,
    folder: str = "",
    template: str = "concept",
    title: str | None = None,
    force: bool = False,
) -> str:
    """
    Create a NEW markdown note with proper frontmatter.

    Uses templates from the vault's 99_System/Templates/ folder.
    Without force=True, returns a preview. Set force=True to create.

    Args:
        filename: Note filename (e.g., 'Agent_Memory.md')
        content: Note body content (uses template if not provided)
        folder: Target folder relative to vault (e.g., '30_Resources/Concepts')
        template: Template type: concept, bridge, daily, project, ticket, web_clip
        title: Note title (defaults to filename-derived)
        force: Set to True to actually create the note
    """
    return tools.create_note(filename, content, folder, template, title, force)


@mcp.tool()
def edit_note(
    filename: str,
    old_text: str | None = None,
    new_text: str | None = None,
    section: str | None = None,
    section_content: str | None = None,
    append_to_section: bool = False,
    force: bool = False,
) -> str:
    """
    Edit an existing note with text replacement or section updates.

    Two modes:
    1. **Text replacement**: old_text + new_text to find/replace content
    2. **Section update**: section + section_content to update a markdown section

    Without force=True, returns a preview. Set force=True to apply.

    Args:
        filename: The note to edit (with or without .md extension)
        old_text: Text to find and replace (for replacement mode)
        new_text: Replacement text (for replacement mode)
        section: Section header to update (e.g., "## Summary" or "Summary")
        section_content: New content for the section
        append_to_section: If True, append to section instead of replacing it
        force: Set to True to actually apply the change
    """
    return tools.edit_note(
        filename, old_text, new_text, section, section_content, append_to_section, force
    )


@mcp.tool()
def apply_wikilink(filename: str, text_to_link: str, target_note: str, force: bool = False) -> str:
    """
    Refactor a note by turning plain text into a [[WikiLink]].

    Without force=True, returns a preview. Set force=True to apply.

    Args:
        filename: The file to edit
        text_to_link: The exact phrase to find (e.g., "artificial intelligence")
        target_note: The destination note name (e.g., "AI_Overview")
        force: Set to True to actually apply the change
    """
    return tools.apply_wikilink(filename, text_to_link, target_note, force)


@mcp.tool()
def append_to_daily(
    content: str,
    section: str = "Inbox / Quick Captures",
    topic: str | None = None,
    force: bool = False,
) -> str:
    """
    Append a timestamped entry to today's daily journal note.

    Without force=True, returns a preview. Set force=True to apply.

    Args:
        content: Content to append
        section: Section header to append under (default: "Inbox / Quick Captures")
        topic: Optional topic label for the entry
        force: Set to True to actually append
    """
    return tools.append_to_daily(content, section, topic, force)


@mcp.tool()
def vault_stats() -> str:
    """
    Get knowledge graph statistics and health metrics.

    Returns:
    - Total notes, edges, and claims
    - Distribution by folder and relationship type
    - Most connected concepts
    - Orphan notes (no connections)
    """
    return tools.vault_stats()


@mcp.tool()
def index_vault(
    query: str | None = None,
    pattern: str | None = None,
    full_rebuild: bool = False,
) -> str:
    """
    Index vault files into the knowledge graph.

    By default, only indexes files modified since the last run (smart indexing).
    Use this for targeted re-indexing of specific content.

    Args:
        query: Only index files containing this text (uses ripgrep for speed)
        pattern: Only index files matching this glob pattern (e.g., "10_Projects/**/*.md")
        full_rebuild: Force re-index all matched files, ignoring content hashes

    Returns:
        Summary of indexing results including files processed, edges created, and time elapsed
    """
    from datetime import datetime

    # Get last index time for smart indexing
    modified_since = None if full_rebuild else get_last_index_time()

    # Get files to index based on filters
    file_list = get_files_to_index(
        pattern=pattern,
        query=query,
        modified_since=modified_since,
    )

    if not file_list:
        last_time = get_last_index_time()
        if last_time:
            from datetime import datetime as dt

            last_dt = dt.fromtimestamp(last_time)
            return f"No files need indexing. Last indexed: {last_dt.strftime('%Y-%m-%d %H:%M:%S')}"
        return "No files found matching the specified criteria."

    # Run the indexer with the filtered file list
    results = build_index(
        full_rebuild=full_rebuild,
        verbose=False,  # Quiet for MCP tool
        file_list=file_list,
    )

    # Format summary
    summary_lines = [
        "## Indexing Complete",
        "",
        f"- **Files processed:** {results['files_processed']}",
        f"- **Files skipped (unchanged):** {results['files_skipped']}",
        f"- **Files errored:** {results['files_errored']}",
        f"- **Time elapsed:** {results['elapsed_seconds']:.1f}s",
        "",
        f"- **Total edges in graph:** {results['total_edges']}",
        f"- **Total claims:** {results['total_claims']}",
    ]

    if query:
        summary_lines.insert(2, f"- **Query filter:** `{query}`")
    if pattern:
        summary_lines.insert(2, f"- **Pattern filter:** `{pattern}`")

    return "\n".join(summary_lines)


@mcp.tool()
def load_repo_mappings(yaml_path: str | None = None) -> str:
    """
    Load repository mappings from repo_mapping.yaml into the database.

    This connects vault folders to git repositories, GitHub repos, and Jira projects.
    Required for pulse scans and dev workflow integration.

    Args:
        yaml_path: Path to repo_mapping.yaml (auto-detected if None)

    Returns:
        Summary of loaded mappings
    """
    from pathlib import Path

    try:
        path = Path(yaml_path) if yaml_path else None
        count = load_mappings_from_yaml(path)
        mappings = get_all_repo_mappings()

        lines = [
            f"## Loaded {count} Repo Mappings",
            "",
        ]

        for mapping in mappings:
            lines.append(f"### {mapping['vault_path']}")
            if mapping.get("repo_path"):
                lines.append(f"- **Local Repo:** `{mapping['repo_path']}`")
            if mapping.get("github_repo"):
                lines.append(f"- **GitHub:** `{mapping['github_repo']}`")
            if mapping.get("jira_project"):
                lines.append(f"- **Jira Project:** `{mapping['jira_project']}`")
            if mapping.get("description"):
                lines.append(f"- **Description:** {mapping['description']}")
            lines.append("")

        return "\n".join(lines)

    except FileNotFoundError as e:
        return f"**Error:** {e}\n\nCreate `repo_mapping.yaml` based on `repo_mapping.yaml.example`."
    except Exception as e:
        return f"**Error loading mappings:** {e}"


def _build_pulse_summary(filename: str, data: dict) -> str:
    """Build a summary string for the Dev Log."""
    summary = [f"**Pulse Scan**: [[{filename}]]"]
    
    # Git stats
    git = data.get("git", {})
    if "repos" in git:
        repo_count = len(git["repos"])
        dirty_count = sum(1 for r in git["repos"] if r.get("dirty"))
        status = "🔴 Dirty" if dirty_count else "🟢 Clean"
        summary.append(f"- **Git**: {repo_count} repos, {status}")

    # GitHub stats
    gh = data.get("github", {})
    prs = len(gh.get("prs", []))
    issues = len(gh.get("issues", []))
    if prs or issues:
        summary.append(f"- **GitHub**: {prs} PRs, {issues} Issues")

    # Jira stats
    jira = data.get("jira", {})
    tickets = len(jira.get("tickets", []))
    if tickets:
        summary.append(f"- **Jira**: {tickets} Tickets")

    return "\n".join(summary)


@mcp.tool()
def list_repo_mappings() -> str:
    """
    List all configured repository mappings.

    Returns:
        Table of vault folders and their linked repos/projects
    """
    mappings = get_all_repo_mappings()

    if not mappings:
        return "No repo mappings configured. Use `load_repo_mappings()` to load from YAML."

    lines = [
        "## Repository Mappings",
        "",
        "| Vault Path | Repo | GitHub | Jira |",
        "|------------|------|--------|------|",
    ]

    for mapping in mappings:
        repo = mapping.get("repo_path", "-")
        github = mapping.get("github_repo", "-")
        jira = mapping.get("jira_project", "-")
        lines.append(f"| {mapping['vault_path']} | `{repo}` | {github} | {jira} |")

    return "\n".join(lines)


@mcp.tool()
def verify_repo_mappings() -> str:
    """
    Verify all repository mappings and check for configuration issues.

    Returns:
        Status report for each mapping
    """
    mappings = get_all_repo_mappings()

    if not mappings:
        return "No repo mappings configured."

    lines = [
        "## Repo Mapping Verification",
        "",
    ]

    for mapping in mappings:
        status = verify_mapping(mapping)
        lines.append(f"### {status['vault_path']}")

        # Status indicators
        checks = [
            ("Vault exists", status["vault_exists"]),
            ("Repo exists", status["repo_exists"]),
            ("Is git repo", status["is_git_repo"]),
        ]

        if mapping.get("github_repo"):
            checks.append(("GitHub accessible", status["github_accessible"]))
        if mapping.get("jira_project"):
            checks.append(("Jira accessible", status["jira_accessible"]))

        for check_name, check_result in checks:
            icon = "✅" if check_result else "❌"
            lines.append(f"- {icon} {check_name}")

        if status["warnings"]:
            lines.append("")
            lines.append("**Warnings:**")
            for warning in status["warnings"]:
                lines.append(f"- ⚠️  {warning}")

        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def pulse_scan(project_name: str, force: bool = False) -> str:
    """
    Perform a pulse scan for a project and save it to the vault.
    Gathers info from Git, GitHub, and Jira.

    Args:
        project_name: The vault_path identifier for the project (e.g., "10_Projects/OVI")
        force: Set to True to actually create the file (otherwise returns preview)
    """
    import os
    from pathlib import Path

    mapping = get_repo_mapping(project_name)
    if not mapping:
        return f"❌ No active mapping found for project: {project_name}. Use `list_repo_mappings()` to check available projects."

    data = {}

    # 1. Git
    if mapping.get("repo_path"):
        repo_path = Path(os.path.expanduser(mapping["repo_path"]))
        if repo_path.exists():
            data["git"] = gather_git_info(repo_path)
            data["structure"] = gather_structural_info(repo_path)
        else:
            data["git"] = {"error": f"Repo path not found: {repo_path}"}

    # 2. GitHub
    if mapping.get("github_repo"):
        data["github"] = gather_github_info(mapping["github_repo"])

    # 3. Jira
    if mapping.get("jira_project"):
        data["jira"] = gather_jira_info(mapping["jira_project"])

    # Format
    markdown = format_pulse_markdown(project_name.split("/")[-1], data)

    # Determine save path
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"Pulse - {today}.md"
    project_vault_dir = VAULT_PATH / mapping["vault_path"]
    target_path = project_vault_dir / filename

    if not force:
        return f"⚠️ PREVIEW (use force=True to save to vault)\n\n**Target Path:** {target_path.relative_to(VAULT_PATH)}\n\n{markdown}"

    try:
        project_vault_dir.mkdir(parents=True, exist_ok=True)
        target_path.write_text(markdown, encoding="utf-8")
        index_single_note(target_path) # Index the new note

        # Also append to Dev Log if it exists
        summary = _build_pulse_summary(filename, data)
        dev_log.append_to_dev_log(project_vault_dir, summary)

        return f"✅ Pulse scan saved to: {target_path.relative_to(VAULT_PATH)}"
    except Exception as e:
        return f"❌ Error saving pulse scan: {e}"


@mcp.tool()
def onboard_project(repo_path: str, project_name: str, force: bool = False) -> str:
    """
    Onboard a project into the vault following the Project Onboarding Protocol.
    Creates a Dev Log.md and updates the Project Index.

    Args:
        repo_path: Absolute path to the git repository
        project_name: Name of the project (folder name in vault)
        force: Set to True to actually create files and update index
    """
    result = onboard_project_logic(repo_path, project_name)

    if "error" in result:
        return f"❌ {result['error']}"

    target_dir = result["target_dir"]
    dev_log_path = target_dir / "Dev Log.md"
    content = result["content"]

    if not force:
        return f"⚠️ PREVIEW (use force=True to onboard)\n\n**Dev Log Path:** {dev_log_path.relative_to(VAULT_PATH)}\n\n{content}"

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        dev_log_path.write_text(content, encoding="utf-8")

        # Phase 3: Index update
        update_project_index(project_name)

        return f"✅ Onboarding complete!\n- Created: {dev_log_path.relative_to(VAULT_PATH)}\n- Project index updated."
    except Exception as e:
        return f"❌ Onboarding failed: {e}"


@mcp.tool()
def append_to_dev_log(project_name: str, content: str, title: str | None = None) -> str:
    """
    Append an entry to a project's Dev Log.
    
    Args:
        project_name: Vault path of the project (e.g. '10_Projects/OVI')
        content: Markdown content to append
        title: Optional title for the entry
    """
    mapping = get_repo_mapping(project_name)
    if not mapping:
        return f"❌ Project '{project_name}' not found in repo mappings."
    
    project_vault_dir = VAULT_PATH / mapping["vault_path"]
    try:
        path = dev_log.append_to_dev_log(project_vault_dir, content, title)
        return f"✅ Appended to {path.relative_to(VAULT_PATH)}"
    except Exception as e:
        return f"❌ Error appending to log: {e}"


@mcp.tool()
def generate_daily_strategy(force: bool = False) -> str:
    """
    Generate a Daily Strategy note based on recent project activity (Pulse Scans).

    Identifies top priorities, blockers, and quick wins.
    Saves to 00_Inbox/Daily Strategy - [Date].md.

    Args:
        force: Set to True to actually create the note (otherwise returns preview)
    """
    return generate_daily_strategy_logic(force)


@mcp.tool()
def analyze_gaps(project_name: str | None = None) -> str:
    """
    Identify knowledge gaps in the vault.

    Finds:
    1. Broken wikilinks (citations of missing notes)
    2. Stub notes (files with little content)
    3. Orphans (notes with no backlinks)

    Args:
        project_name: Optional filter to check only a specific project folder

    Returns:
        A markdown report of the gaps.
    """
    return analyze_gaps_logic(project_name)


@mcp.tool()
def deep_onboard(repo_path: str, project_name: str | None = None, force: bool = False) -> str:
    """
    Perform an autonomous deep onboarding of a local repository.
    Categorizes the project, explores code, creates/updates vault notes,
    and integrates concepts.

    Args:
        repo_path: Path to the local git repository
        project_name: Optional name (defaults to folder name)
        force: Set to True to apply changes (otherwise returns proposal)
    """
    return deep_onboard_logic(repo_path, project_name, force)


# =============================================================================
# CLI ENTRYPOINT
# =============================================================================


def main():
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Obsidian MCP Server - Second Brain integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  obsidian-mcp                    # Start MCP server
  obsidian-mcp --index            # Smart index (only new/modified files)
  obsidian-mcp --index --full     # Force full rebuild
  obsidian-mcp --index --limit 20 # Index only 20 files (for testing)
  obsidian-mcp --stats            # Show vault statistics
  obsidian-mcp --config           # Show configuration
  obsidian-mcp --load-mappings    # Load repo mappings from YAML
  obsidian-mcp --list-mappings    # List configured repo mappings
  obsidian-mcp --verify-mappings  # Verify repo mapping configuration
  obsidian-mcp --pulse "10_Projects/Accurkardia" # Run project pulse scan
  obsidian-mcp --strategy         # Generate Daily Strategy note
  obsidian-mcp --gaps             # Run gap analysis
  obsidian-mcp --deep-onboard "." # Deep onboard current directory
""",
    )

    parser.add_argument(
        "--index", action="store_true", help="Run the knowledge graph indexer instead of MCP server"
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Force full rebuild when indexing (ignore timestamps and content hashes)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force execution for tools like deep-onboard",
    )
    parser.add_argument(
        "--limit",
        type=int,
        metavar="N",
        help="Limit indexing to N files (useful for testing)",
    )
    parser.add_argument("--stats", action="store_true", help="Show vault statistics and exit")
    parser.add_argument("--config", action="store_true", help="Show current configuration and exit")
    parser.add_argument(
        "--load-mappings",
        action="store_true",
        help="Load repo mappings from repo_mapping.yaml",
    )
    parser.add_argument(
        "--list-mappings", action="store_true", help="List all configured repo mappings"
    )
    parser.add_argument(
        "--verify-mappings",
        action="store_true",
        help="Verify repo mapping configuration",
    )
    parser.add_argument(
        "--pulse",
        metavar="PROJECT",
        help="Run a pulse scan for a project (vault_path)",
    )
    parser.add_argument(
        "--dev-log",
        metavar="PROJECT",
        help="Show action items for a project",
    )
    parser.add_argument(
        "--strategy",
        action="store_true",
        help="Generate Daily Strategy based on recent activity",
    )
    parser.add_argument(
        "--gaps",
        action="store_true",
        help="Run gap analysis (broken links, stubs, orphans)",
    )
    parser.add_argument(
        "--deep-onboard",
        metavar="PATH",
        help="Run deep onboarding for a repository path",
    )
    parser.add_argument(
        "--context-hook",
        metavar="PROMPT",
        help="Run ContextEngine hook (outputs JSON)",
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress verbose output")

    args = parser.parse_args()

    # Show config and exit
    if args.config:
        print_config()
        return

    # Show stats and exit
    if args.stats:
        init_db()
        print(tools.vault_stats())
        return

    # Load repo mappings
    if args.load_mappings:
        init_db()
        print(load_repo_mappings())
        return

    # List mappings
    if args.list_mappings:
        init_db()
        print(list_repo_mappings())
        return

    # Verify mappings
    if args.verify_mappings:
        init_db()
        print(verify_repo_mappings())
        return

    # Pulse scan
    if args.pulse:
        init_db()
        print(pulse_scan(args.pulse, force=True))
        return

        print(pulse_scan(args.pulse, force=True))
        return

    # Dev Log action items
    if args.dev_log:
        init_db()
        mapping = get_repo_mapping(args.dev_log)
        if not mapping:
             print(f"❌ Project '{args.dev_log}' not found in repo mappings.")
             return
        
        path = VAULT_PATH / mapping["vault_path"] / "Dev Log.md"
        if not path.exists():
            print(f"❌ Dev Log not found at {path}")
            return
            
        try:
            content = path.read_text(encoding="utf-8")
            items = dev_log.extract_action_items(content)
            print(f"🏗️  Action Items for {args.dev_log}:")
            if not items:
                print("   (No open items found)")
            for item in items:
                print(f"   {item}")
        except Exception as e:
             print(f"❌ Error reading log: {e}")
        return

    # Strategy generation
    if args.strategy:
        init_db()
        print(generate_daily_strategy(force=True))
        return

    # Gap analysis
    if args.gaps:
        init_db()
        print(analyze_gaps())
        return

    # Deep onboard
    if args.deep_onboard:
        init_db()
        # For CLI, we might want to default force=True if user confirms,
        # but for safety, let's just print the proposal first unless --force flag is added?
        # Current argparse structure doesn't easily support a separate --force flag for this specific command without global pollution.
        # Let's assume CLI usage implies intent, OR we print the proposal.
        # Actually, let's just run it with force=False first to show the proposal.
        # User can add a --force flag if we added one.
        # Let's add a global --force flag.
        print(deep_onboard(args.deep_onboard, force=getattr(args, "force", False)))
        return

    # Context Hook
    if args.context_hook:
        init_db()
        engine = hooks.ContextEngine()
        print(engine.get_context(args.context_hook))
        return

    # Run indexer
    if args.index:
        if not VAULT_PATH.exists():
            print(f"❌ Vault not found: {VAULT_PATH}")
            sys.exit(1)

        verbose = not args.quiet

        # Smart indexing: only process files modified since last run
        if args.full:
            # Full rebuild - ignore timestamps
            if verbose:
                print("🔄 Full rebuild requested - ignoring timestamps")
            build_index(full_rebuild=True, verbose=verbose, limit=args.limit)
        else:
            # Smart mode - only files modified since last index
            last_index_time = get_last_index_time()

            if last_index_time and verbose:
                from datetime import datetime

                last_dt = datetime.fromtimestamp(last_index_time)
                print(f"⏰ Last indexed: {last_dt.strftime('%Y-%m-%d %H:%M:%S')}")
                print("📂 Finding files modified since then...")

            # Get files modified since last run
            file_list = get_files_to_index(modified_since=last_index_time)

            if not file_list and last_index_time:
                if verbose:
                    print("✅ No files modified since last index. Nothing to do.")
                    print("   Use --full to force a complete rebuild.")
                return

            build_index(
                full_rebuild=False,
                verbose=verbose,
                limit=args.limit,
                file_list=file_list if last_index_time else None,
            )
        return

    # Default: Run MCP server
    if not VAULT_PATH.exists():
        print(f"❌ Vault not found: {VAULT_PATH}", file=sys.stderr)
        print("Set VAULT_PATH in .env or environment", file=sys.stderr)
        sys.exit(1)

    init_db()
    mcp.run()


if __name__ == "__main__":
    main()
