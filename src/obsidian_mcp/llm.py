"""
LLM provider abstraction for obsidian-mcp.

Configure via environment variables:
  LLM_PROVIDER  — gemini (default), claude, openai
  LLM_MODEL     — model name; per-provider defaults apply when unset
"""

import subprocess
from .config import LLM_PROVIDER, LLM_MODEL


def call_llm(prompt: str, timeout: int = 120) -> str:
    """
    Send a prompt to the configured LLM and return the raw text response.

    Raises:
        RuntimeError: on subprocess failure, binary not found, or API error
    """
    provider = LLM_PROVIDER.lower()
    if provider == "gemini":
        return _call_subprocess(["gemini", "--model", LLM_MODEL], prompt, timeout, "Gemini CLI")
    elif provider == "claude":
        return _call_subprocess(["claude", "--model", LLM_MODEL, "--print"], prompt, timeout, "Claude CLI")
    elif provider == "openai":
        return _call_openai(prompt, timeout)
    else:
        raise RuntimeError(
            f"Unknown LLM_PROVIDER '{provider}'. Supported: gemini, claude, openai"
        )


def _call_subprocess(cmd: list[str], prompt: str, timeout: int, name: str) -> str:
    proc = None
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = proc.communicate(input=prompt, timeout=timeout)
        if proc.returncode != 0:
            raise RuntimeError(f"{name} exited {proc.returncode}: {stderr[:300]}")
        return stdout.strip()
    except subprocess.TimeoutExpired:
        if proc:
            proc.kill()
        raise RuntimeError(f"{name} timed out after {timeout}s")
    except FileNotFoundError:
        hints = {
            "Gemini CLI": "npm install -g @google/gemini-cli",
            "Claude CLI": "npm install -g @anthropic-ai/claude-code",
        }
        raise RuntimeError(f"{name} not found. Install: {hints.get(name, 'check PATH')}")


def _call_openai(prompt: str, timeout: int) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError(
            "openai package not installed. Run: pip install 'obsidian-mcp[openai]'"
        )
    client = OpenAI()  # reads OPENAI_API_KEY from env
    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            timeout=float(timeout),
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        raise RuntimeError(f"OpenAI API error: {e}") from e
