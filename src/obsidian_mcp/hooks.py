"""
Gemini CLI Hooks Integration.

Implements the 'BeforeAgent' hook to inject project context into the session.
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Set

from .config import VAULT_PATH
from .db import get_all_repo_mappings

class ContextEngine:
    def __init__(self):
        self._mappings_cache: List[Dict] | None = None

    def _get_mappings(self) -> List[Dict]:
        """Lazy load mappings from DB."""
        if self._mappings_cache is None:
            self._mappings_cache = get_all_repo_mappings()
        return self._mappings_cache

    def extract_keywords(self, prompt: str) -> List[Dict]:
        """
        Identify projects mentioned in the prompt.
        Returns a list of mapping dicts.
        """
        mappings = self._get_mappings()
        found_projects = []
        prompt_lower = prompt.lower()
        
        for m in mappings:
            # Check vault folder name
            vault_path = m["vault_path"]
            project_name = vault_path.split("/")[-1] # e.g. "OVI"
            
            # Simple keyword matching
            # TODO: Improve with fuzzy matching or aliases
            if project_name.lower() in prompt_lower:
                found_projects.append(m)
                continue
                
            # Check repo name e.g. "ovi" from "/path/to/ovi"
            if m.get("repo_path"):
                repo_name = Path(m["repo_path"]).name
                if repo_name.lower() in prompt_lower:
                    found_projects.append(m)
                    
        return found_projects

    def get_tactical_briefing(self, mapping: Dict) -> str:
        """Read project context, using Dev Log if available, falling back to index search."""
        vault_path = mapping["vault_path"]
        project_name = vault_path.split("/")[-1]

        # --- Tier 1: Dev Log (richest, structured) ---
        dev_log_path = VAULT_PATH / vault_path / "Dev Log.md"
        if dev_log_path.exists():
            try:
                content = dev_log_path.read_text(encoding="utf-8")
                sections = []

                match = re.search(r"## 📝 Executive Summary\n(.*?)\n##", content, re.DOTALL)
                if match:
                    sections.append(f"Summary: {match.group(1).strip()}")

                match = re.search(r"## 📊 Vital Statistics\n(.*?)\n##", content, re.DOTALL)
                if match:
                    sections.append(f"Stats: {match.group(1).strip()}")

                if sections:
                    return f"Project Context ({project_name}):\n" + "\n".join(sections)

                # Dev Log exists but has no structured sections — fall through to Tier 2
            except Exception:
                pass  # Fall through to Tier 2

        # --- Tier 2: FTS Index search for project notes ---
        context_lines = [f"Project Context ({project_name}):"]
        found_anything = False

        try:
            from .db import search_fts, get_connections

            # Search for notes within this project's vault folder
            fts_results = search_fts(project_name, limit=5)
            project_notes = [r for r in fts_results if vault_path in r.get("filename", "")]

            if project_notes:
                found_anything = True
                context_lines.append("**Indexed Notes:**")
                for note in project_notes[:3]:
                    title = note.get("title") or note.get("filename", "")
                    snippet = note.get("snippet", "").replace("\n", " ")
                    context_lines.append(f"- **{title}**: {snippet}")

            # Get graph connections for the Dev Log or any key note in the project
            dev_log_name = f"{vault_path}/Dev Log"
            connections = get_connections(dev_log_name)
            all_links = connections.get("outlinks", []) + connections.get("backlinks", [])
            if all_links:
                found_anything = True
                context_lines.append("**Related Concepts:**")
                seen = set()
                for link in all_links[:5]:
                    target = link.get("target") or link.get("source", "")
                    relation = link.get("relation", "relates to")
                    if target not in seen:
                        seen.add(target)
                        context_lines.append(f"- {relation}: [[{target}]]")

        except Exception:
            pass  # DB not initialized or query failed

        # --- Tier 3: Direct folder scan (last resort) ---
        if not found_anything:
            project_dir = VAULT_PATH / vault_path
            if project_dir.exists():
                md_files = list(project_dir.glob("*.md"))
                if md_files:
                    found_anything = True
                    context_lines.append("**Notes in project folder:**")
                    for f in md_files[:5]:
                        context_lines.append(f"- {f.name}")

        if not found_anything:
            return f"Project: {project_name} (no indexed notes found — run `obsidian-mcp --index` or `--pulse` to populate)"

        return "\n".join(context_lines)

    def get_context(self, prompt: str) -> str:
        """
        Orchestrate context gathering.
        Returns JSON string for Gemini CLI hook output.
        """
        projects = self.extract_keywords(prompt)
        
        if not projects:
             return json.dumps({"hookSpecificOutput": {"additionalContext": ""}})
             
        briefings = []
        for p in projects:
            briefings.append(self.get_tactical_briefing(p))
            
        context_str = "\n\n---\n\n".join(briefings)
        
        response = {
            "hookSpecificOutput": {
                "additionalContext": context_str
            }
        }
        
        return json.dumps(response)
