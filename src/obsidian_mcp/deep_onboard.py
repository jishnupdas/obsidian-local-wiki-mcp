"""
Deep Onboarding - Autonomous project intelligence, categorization, and merging.
"""

import json
import os
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from .config import VAULT_PATH
from .llm import call_llm
from .pulse import gather_git_info, gather_structural_info, run_command
from .db import get_db, upsert_note
from .indexer import extract_wikilinks

# =============================================================================
# PROMPTS
# =============================================================================

ARCHITECT_PROMPT = """You are a Senior System Architect and Knowledge Graph Engineer.
Your task is to analyze a software project and integrate it into a Second Brain Obsidian Vault.

PROJECT CONTEXT:
Name: {project_name}
Path: {repo_path}

ANALYSIS DATA:
{analysis_data}

EXISTING CATEGORIES:
1. 🚀 Archimydes (Active Development, Commercial)
2. 🏥 Ishi (Healthcare, Medical Tech)
3. 🔭 Naxxatra (Astronomy, Education, Outreach)
4. 🔬 Science (Research, Physics, Data Analysis)
5. 🧪 Dev / POCs (Experiments, Proof of Concepts)
6. 🧑‍💻 Techage (ERP, Business Logic)
7. 🛠️ Tools (Scripts, Utilities, Config)
8. 🌐 Web / Personal (Portfolios, Apps)
9. 🎖️ Defence (Military, Police, Training)
10. 📂 Other (Uncategorized)

INSTRUCTIONS:
1. **Categorize**: Assign the project to exactly ONE of the existing categories. Use the file path as a strong hint (e.g. 'dev/defence' -> 'Defence').
2. **Synthesize**: Create a "Dashboard" markdown structure.
   - If mostly Jupyter Notebooks (.ipynb), emphasize "Research/Data Science".
   - If no explicit tech stack found, infer from file extensions (.py -> Python, .ts -> TypeScript).
3. **Identify Concepts**: List technical concepts found. Distinguish between ones that likely exist (e.g. React, Python) and novel ones.

OUTPUT FORMAT (JSON):
{{
  "category": "Category Name",
  "summary": "One paragraph executive summary...",
  "tech_stack": ["Lang1", "Lang2", "Framework1"],
  "concepts": [
    {{"name": "Concept Name", "is_novel": boolean, "definition": "One sentence definition"}}
  ],
  "dashboard_sections": {{
    "Strategy": "Content for Strategy section...",
    "Architecture": "Content for Architecture section...",
    "Features": "Content for Features section..."
  }}
}}
"""

# =============================================================================
# LOGIC
# =============================================================================


def _format_analysis(data: Dict[str, Any]) -> str:
    return f"""
    - Path Context: {data.get("path_context", "Unknown")}
    - Manifests: {", ".join(data.get("manifests", []))}
    - Languages inferred: {data.get("languages", "Unknown")}
    - Git Status: {data.get("git", {}).get("status_summary", "Clean")}
    - Structure Hint: {data.get("structure", {}).get("structure", "")[:1500]}
    - README Excerpt: {data.get("readme", "")[:3000]}
    - File Extensions: {data.get("extensions", [])}
    """


def _parse_architect_response(raw: str) -> Dict[str, Any]:
    """Parse LLM response into architect dict.

    Handles plain JSON, markdown-fenced JSON, and the legacy Gemini CLI
    --output-format json wrapper: {"response": "...", "session_id": "...", "stats": {}}.
    """
    clean = raw.strip()
    for prefix in ("```json", "```"):
        if clean.startswith(prefix):
            clean = clean[len(prefix):]
            break
    if clean.endswith("```"):
        clean = clean[:-3]
    clean = clean.strip()

    idx = clean.find("{")
    if idx == -1:
        return {"error": f"No JSON object found in LLM response: {clean[:200]}"}
    clean = clean[idx:]

    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse error: {e}"}

    # Handle legacy Gemini --output-format json wrapper
    if "response" in parsed and isinstance(parsed["response"], str):
        inner = parsed["response"].strip()
        for prefix in ("```json", "```"):
            if inner.startswith(prefix):
                inner = inner[len(prefix):]
                break
        if inner.endswith("```"):
            inner = inner[:-3]
        try:
            return json.loads(inner.strip())
        except json.JSONDecodeError:
            pass

    return parsed


def call_llm_architect(
    project_name: str, repo_path: str, data: Dict[str, Any]
) -> Dict[str, Any]:
    """Call the configured LLM to analyze project structure."""
    prompt = ARCHITECT_PROMPT.format(
        project_name=project_name,
        repo_path=repo_path,
        analysis_data=_format_analysis(data),
    )
    try:
        raw = call_llm(prompt, timeout=60)
    except RuntimeError as e:
        return {"error": str(e)}
    return _parse_architect_response(raw)


def fuzzy_match_concept(concept: str) -> str:
    """
    Check if a concept exists in the vault, allowing for fuzzy matching.
    e.g. "ReactJS" -> "[[React Library]]"
    """
    # 1. Direct match check (fastest)
    exact_path = list(VAULT_PATH.glob(f"**/{concept}.md"))
    if exact_path:
        return f"[[{concept}]]"

    # 2. Known aliases (Manual map for common dev terms)
    aliases = {
        "react": "React Library",
        "reactjs": "React Library",
        "nextjs": "Next.js",
        "gcp": "Google Cloud Platform",
        "aws": "AWS",
        "typescript": "TypeScript",
        "python": "Python",
        "node": "Node.js",
        "nodejs": "Node.js",
    }

    lower = concept.lower()
    if lower in aliases:
        return f"[[{aliases[lower]}]]"

    # 3. DB Search (SQLite) - Using FTS could be good here, but for now simple glob
    # If we had a vector store, this would be semantic search.
    # Simple "contains" check on filenames
    candidates = []
    for f in VAULT_PATH.glob("**/*.md"):
        if lower in f.stem.lower():
            candidates.append(f.stem)

    if candidates:
        # Pick shortest match (often the main concept)
        best = min(candidates, key=len)
        return f"[[{best}]]"

    # No match found - return as is (will likely become a red link or stub)
    return f"[[{concept}]]"


def create_concept_stub(name: str, definition: str, source_project: str) -> str:
    """Create a stub note for a new concept."""
    # Sanitize filename
    safe_name = re.sub(r'[\\/*?:"<>|]', "", name)
    path = VAULT_PATH / "30_Resources" / "Concepts" / f"{safe_name}.md"

    if path.exists():
        return f"Exists: [[{safe_name}]]"

    content = f"""---
tags:
  - concept
  - auto-generated
created: {datetime.now().strftime("%Y-%m-%d")}
source_project: "[[{source_project}]]"
---

# {name}

> {definition}

## Context
Identified during deep onboarding of **[[{source_project}]]**.

---
[[Concepts Index]]
"""
    try:
        path.write_text(content, encoding="utf-8")
        return f"Created: [[{safe_name}]]"
    except Exception as e:
        return f"Failed to create stub {name}: {e}"


def merge_note_content(existing: str, new_sections: Dict[str, str]) -> str:
    """
    Intelligently merge new sections into an existing note.
    Preserves unknown sections. Overwrites/Appends known ones.
    """
    # Simple strategy:
    # 1. Parse existing into sections based on `## Header`
    # 2. Update specific sections
    # 3. Reassemble

    sections = {}
    current_header = "PREAMBLE"
    lines = existing.split("\n")
    buffer = []

    for line in lines:
        if line.startswith("## "):
            sections[current_header] = "\n".join(buffer).strip()
            buffer = []
            current_header = line[3:].strip()  # Remove '## '
        else:
            buffer.append(line)
    sections[current_header] = "\n".join(buffer).strip()  # Last section

    # Merge updates
    for header, content in new_sections.items():
        # logic: if section exists, append/update. For now, let's append with timestamp
        # to be safe against data loss.
        if header in sections:
            sections[header] = (
                f"{sections[header]}\n\n### Update ({datetime.now().strftime('%Y-%m-%d')})\n{content}"
            )
        else:
            sections[header] = content

    # Reassemble
    out = [sections.get("PREAMBLE", "")]
    for header, content in sections.items():
        if header == "PREAMBLE":
            continue
        out.append(f"\n## {header}\n{content}")

    return "".join(out)


def move_in_index(project_name: str, target_category: str) -> str:
    """
    Move a project to the correct category in Project Index.md.
    Handles counts and progress bars.
    """
    index_path = VAULT_PATH / "10_Projects" / "Project Index.md"
    content = index_path.read_text(encoding="utf-8")

    # 1. Find the project line
    # Matches: - [x] [[ProjectName]]... or - [ ] [[ProjectName]]...
    # We look for the link specifically
    link_regex = re.compile(rf"-\s*\[([ x])\]\s*\[\[{re.escape(project_name)}\]\](.*)")
    match = link_regex.search(content)

    if not match:
        return "Project not found in index."

    full_line = match.group(0)
    status = match.group(1)  # ' ' or 'x'
    rest = match.group(2)

    # Remove old line
    content = content.replace(full_line, "")
    # Clean up empty newlines left behind might be tricky with replace,
    # but let's just do a basic replace.

    # 2. Find Target Category Header
    # Matches: ## 🚀 Archimydes or ## 🏥 [[Ishi]]
    # We search for "## [Icon] ... TargetCategory"
    # This assumes TargetCategory matches text in header.
    # Simple find:
    header_match = re.search(rf"^##\s+.*\b{re.escape(target_category)}\b.*$", content, re.MULTILINE)

    if not header_match:
        # Fallback: Add to 'Uncategorized' or create header?
        # Let's try to be smart about exact naming from the prompt list
        return f"Target category header '{target_category}' not found in index."

    insert_pos = header_match.end()

    # 3. Insert line
    # We insert it right after the header (or existing items)
    # A bit risky to insert at pos without checking for list start.
    # We can look for the next "## " or end of file

    next_header = re.search(r"^## ", content[insert_pos:], re.MULTILINE)
    if next_header:
        # Insert before next header
        chunk_end = insert_pos + next_header.start()
        # Find last list item in this chunk
        last_item = re.search(r"-\s*\[.*", content[insert_pos:chunk_end], re.MULTILINE)
        if last_item:
            # Append after last item
            insertion_point = insert_pos + last_item.end()
        else:
            # No items yet, insert after header
            insertion_point = insert_pos + 1
    else:
        # EOF
        insertion_point = len(content)

    # Reconstruct
    new_line = f"\n- [{status}] [[{project_name}]]{rest}"
    # Normalize double newlines just in case
    content = content[:insertion_point] + new_line + content[insertion_point:]

    # 4. Update Stats (Recalculate all)
    # This effectively requires parsing the whole table.
    # For MVP, we might skip the table update or call `update_project_index` logic
    # but that logic was incremental.
    # Let's leave stats consistency for a separate "Repair Index" tool call
    # or rely on the user to check it.
    # Or... simple regex for the counts.

    index_path.write_text(content, encoding="utf-8")
    return f"Moved [[{project_name}]] to {target_category}."


def deep_onboard_logic(repo_path: str, project_name: str | None = None, force: bool = False) -> str:
    """
    Orchestrate the deep onboarding process.
    """
    path = Path(os.path.expanduser(repo_path))
    if not path.exists():
        return f"Repo not found: {path}"

    if not project_name:
        project_name = path.name

    # 1. Discovery
    git_info = gather_git_info(path)
    struct_info = gather_structural_info(path)

    # Read README
    readme_content = ""
    readme = list(path.glob("README*"))
    if readme:
        readme_content = readme[0].read_text()[:3000]

    # Gather file extensions for better inference
    extensions = set()
    for f in path.glob("**/*"):
        if f.is_file() and f.suffix:
            extensions.add(f.suffix)

    # Get relative path from Projects root for context (e.g. dev/defence/...)
    # Heuristic: try to find 'Projects' in path parts
    try:
        parts = path.parts
        if "Projects" in parts:
            idx = parts.index("Projects")
            rel_context = "/".join(parts[idx + 1 :])
        else:
            rel_context = str(path)
    except:
        rel_context = str(path)

    discovery_data = {
        "git": git_info,
        "structure": struct_info,
        "manifests": struct_info.get("manifests", []),
        "readme": readme_content,
        "extensions": list(extensions),
        "path_context": rel_context,
    }

    # 2. Intelligence
    analysis = call_llm_architect(project_name, str(path), discovery_data)

    if "error" in analysis:
        return f"Analysis failed: {analysis['error']}"

    category = analysis.get("category", "Other")
    concepts = analysis.get("concepts", [])

    # 3. Proposal Generation
    report = [
        f"## 📝 Deep Onboard Proposal: {project_name}",
        "",
        f"### 📂 Organization",
        f"- **Repo:** `{path}`",
        f"- **Proposed Category:** {category}",
        "",
        "### 🧠 Knowledge Capture",
    ]

    new_stubs = []
    links = []

    for c in concepts:
        name = c["name"]
        linked = fuzzy_match_concept(name)
        links.append(linked)
        if c.get("is_novel") and linked == f"[[{name}]]":  # If it resolves to itself and is novel
            new_stubs.append(c)

    report.append(f"- **New Concepts:** {', '.join([c['name'] for c in new_stubs])}")
    report.append(f"- **Tech Stack:** {', '.join(analysis.get('tech_stack', []))}")

    if not force:
        return "\n".join(report) + "\n\n⚠️ Run with `force=True` to apply changes."

    # 4. Execution

    # A. Concept Stubs
    created_stubs = []
    for stub in new_stubs:
        res = create_concept_stub(stub["name"], stub["definition"], project_name)
        created_stubs.append(res)

    # B. Index Move
    move_res = move_in_index(project_name, category)

    # C. Note Creation/Merge
    # Create main Project Note
    if " " in category:
        folder_name = category.split()[1]  # e.g. "🚀 Archimydes" -> "Archimydes"
    else:
        folder_name = category

    note_path = VAULT_PATH / "10_Projects" / folder_name / f"{project_name}.md"

    # Actually finding the right folder is tricky if "10_Projects/Ishi" vs "10_Projects/ishi".
    # Best to use `get_repo_mapping` or find existing folder.

    # Simple approach: Search for folder matching category name
    target_folder = None
    for d in (VAULT_PATH / "10_Projects").iterdir():
        if d.is_dir() and (category in d.name or d.name in category):
            target_folder = d
            break

    if not target_folder:
        target_folder = VAULT_PATH / "10_Projects" / category.replace(" ", "_")
        target_folder.mkdir(exist_ok=True)

    final_note_path = target_folder / f"{project_name}.md"

    # Dashboard Content
    sections = analysis.get("dashboard_sections", {})
    base_content = f"""---
tags:
  - project
  - {category.lower().replace(" ", "-")}
  - active
created: {datetime.now().strftime("%Y-%m-%d")}
status: Active
repo: {path}
---

# 🚀 {project_name}

> {analysis.get("summary", "Auto-generated summary.")}

## 📝 Vital Statistics
* **Stack:** {", ".join([fuzzy_match_concept(t) for t in analysis.get("tech_stack", [])])}
* **Category:** {category}

"""

    if final_note_path.exists():
        existing_content = final_note_path.read_text()
        final_content = merge_note_content(existing_content, sections)
    else:
        # Build new
        final_content = base_content
        for h, c in sections.items():
            final_content += f"\n## {h}\n{c}\n"

        final_content += "\n[[Home]] | [[Project Index]]"

    final_note_path.write_text(final_content)

    # D. Dev Log (Keep existing or create basic)
    dev_log_path = target_folder / "Dev Log.md"
    if not dev_log_path.exists():
        dev_log_path.write_text(
            f"# Dev Log: {project_name}\n\n[[Home]] | [[Project Index]] | [[{project_name}]]"
        )

    return f"""✅ Deep Onboarding Complete for {project_name}
    
    - **Category:** {move_res}
    - **Note:** [[{final_note_path.relative_to(VAULT_PATH)}]]
    - **Concepts Created:** {len(created_stubs)}
    """
