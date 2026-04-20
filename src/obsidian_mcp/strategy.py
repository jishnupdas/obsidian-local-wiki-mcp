"""
Strategy Module - Generates Daily Strategy based on project activity.
"""

from datetime import datetime
from pathlib import Path
from .config import VAULT_PATH
from .llm import call_llm


def get_strategy_prompt(date_str: str) -> str:
    return f"""You are the Chief of Staff for a busy developer.
Your goal is to synthesize a "Daily Strategy" based on the provided project updates (Pulse Scans).

Date: {date_str}

Analyze the following project activity summaries and identify:
1. Top 3 Priorities: What requires immediate attention? (Look for dirty working trees, uncommitted changes, open PRs, or urgent TODOs)
2. Blockers/Issues: Any red flags, errors, or stale branches?
3. Quick Wins: Small tasks that can be cleared easily.

Output Format (Markdown):
# 🎯 Daily Strategy - {date_str}

## 🚨 Top Priorities
1. **[Project Name]**: [Task/Focus] - *[Reason]*
2. ...
3. ...

## ⚠️ Issues & Blockers
- [Project]: [Issue]

## ⚡ Quick Wins
- [Project]: [Task]

## 📝 Notes
[Any other observations or synthesis of the work state]
"""


def call_llm_strategy(context: str, date_str: str) -> str:
    """Call the configured LLM to generate strategy."""
    full_input = f"{get_strategy_prompt(date_str)}\n\nCONTEXT:\n{context}"
    try:
        return call_llm(full_input, timeout=60)
    except RuntimeError as e:
        return f"Error generating strategy: {e}"


def generate_daily_strategy_logic(force: bool = False) -> str:
    """
    Generate a Daily Strategy note based on recent Pulse Scans.
    """
    today = datetime.now().strftime("%Y-%m-%d")

    # Find all Pulse files
    pulse_files = list(VAULT_PATH.glob("**/Pulse - *.md"))

    # Filter for recent ones (last 3 days) to ensure relevance
    # Actually, simpler to just take the most recent 10 pulses overall,
    # assuming they represent the active context.
    # Sorting by modification time might be better than name if files were updated recently.
    # But Pulse files are usually created once.
    # Let's sort by filename (Date) descending.
    pulse_files.sort(key=lambda p: p.name, reverse=True)

    recent_pulses = pulse_files[:15]  # Take top 15 to get a good spread

    if not recent_pulses:
        return "No Pulse Scans found. Run 'pulse_scan' on some projects first."

    context = ""
    projects_included = []

    for p in recent_pulses:
        # Avoid duplicate projects if multiple pulses exist
        project_name = p.parent.name
        if project_name in projects_included:
            continue

        projects_included.append(project_name)

        try:
            content = p.read_text(encoding="utf-8")
            # Truncate content if too long to avoid token limits
            if len(content) > 5000:
                content = content[:5000] + "\n... (truncated)"
            context += f"--- PROJECT: {project_name} (File: {p.name}) ---\n{content}\n\n"
        except Exception as e:
            print(f"Error reading {p}: {e}")

    if not context:
        return "No readable Pulse Scans found."

    # Generate Strategy
    strategy_content = call_llm_strategy(context, today)

    # Save
    filename = f"Daily Strategy - {today}.md"
    inbox_path = VAULT_PATH / "00_Inbox" / filename

    if not force:
        return (
            f"⚠️ PREVIEW (use force=True to save):\n\n**Target:** {inbox_path}\n\n{strategy_content}"
        )

    try:
        inbox_path.parent.mkdir(parents=True, exist_ok=True)
        inbox_path.write_text(strategy_content, encoding="utf-8")
        return f"✅ Daily Strategy generated: [[{filename}]]"
    except Exception as e:
        return f"❌ Error saving strategy: {e}"
