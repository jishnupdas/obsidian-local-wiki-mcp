"""
Vector Embedding Module for Obsidian MCP.

Provides local semantic embeddings using fastembed (ONNX Runtime — no PyTorch required).
Supports full-document coverage via overlapping chunking.

All public functions degrade gracefully when vector dependencies are not installed.
Install with: pip install -e ".[vector]"
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastembed import TextEmbedding

from .config import VECTOR_MODEL, VECTOR_CHUNK_SIZE, VECTOR_CHUNK_OVERLAP

# =============================================================================
# AVAILABILITY CHECK
# =============================================================================

_AVAILABLE: bool | None = None  # Cached result after first check


def is_available() -> bool:
    """
    Return True if vector dependencies (sqlite_vec + fastembed) are installed.

    Cached after first call. Safe to call frequently.
    """
    global _AVAILABLE
    if _AVAILABLE is not None:
        return _AVAILABLE

    try:
        import sqlite_vec  # noqa: F401
        import fastembed  # noqa: F401

        _AVAILABLE = True
    except ImportError:
        _AVAILABLE = False

    return _AVAILABLE


# =============================================================================
# MODEL (LAZY SINGLETON)
# =============================================================================

_model: TextEmbedding | None = None


def get_model() -> TextEmbedding:
    """
    Return the singleton TextEmbedding model, loading it on first call.

    Model: BAAI/bge-small-en-v1.5 (default for fastembed)
    - 384 dimensions
    - 67MB ONNX weights, cached in ~/.cache/fastembed/
    - 512-token context window (~1,600 chars)
    """
    global _model
    if _model is None:
        from fastembed import TextEmbedding

        _model = TextEmbedding(model_name=VECTOR_MODEL)
    return _model


# =============================================================================
# CHUNKING
# =============================================================================


def chunk_text(text: str, size: int = VECTOR_CHUNK_SIZE, overlap: int = VECTOR_CHUNK_OVERLAP) -> list[str]:
    """
    Split text into overlapping character-level windows.

    Args:
        text:    Full document content to split.
        size:    Characters per chunk (default: VECTOR_CHUNK_SIZE = 1500).
                 Chosen to stay safely within the model's 512-token limit.
        overlap: Characters shared between adjacent chunks (default: 200).
                 Prevents context loss at chunk boundaries.

    Returns:
        List of text chunks. Returns [text] unchanged if shorter than ``size``.

    Example:
        chunk_text("abcdefgh", size=4, overlap=1)
        → ["abcd", "defg", "efgh"]
    """
    if len(text) <= size:
        return [text]

    chunks = []
    start = 0
    step = size - overlap

    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start += step

    return chunks


# =============================================================================
# EMBEDDING HELPERS
# =============================================================================


def embed(text: str) -> list[float]:
    """
    Embed a single text string.

    fastembed.embed() returns a generator of numpy arrays; this helper
    materialises the first (and only) result and converts to list[float]
    for compatibility with sqlite-vec.

    Args:
        text: Text to embed (should be ≤ VECTOR_CHUNK_SIZE chars).

    Returns:
        384-dimensional embedding as list[float].
    """
    model = get_model()
    embedding = next(model.embed([text]))
    return embedding.tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    """
    Embed a batch of text strings efficiently.

    Passes all texts to fastembed in one call, which parallelises
    inference via ONNX data-parallelism.

    Args:
        texts: List of strings to embed.

    Returns:
        List of 384-dimensional embeddings, one per input text.
    """
    if not texts:
        return []
    model = get_model()
    return [emb.tolist() for emb in model.embed(texts)]
