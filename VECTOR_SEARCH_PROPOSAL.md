# Proposal: Integration of Local Vector Search

**Status:** ✅ Implemented (supersedes original ChromaDB proposal)
**Date:** 2026-02-10
**Author:** Gemini Agent
**Updated:** 2026-02-20

> [!IMPORTANT]
> **Decision (2026-02-20):** The ChromaDB approach described below was superseded in favour of a lighter stack:
>
> - **Vector DB:** `sqlite-vec` — vectors stored inside the existing `vault.db` (no new files)
> - **Embeddings:** `fastembed` with `BAAI/bge-small-en-v1.5` — ONNX runtime, no PyTorch required (~85MB total)
> - **Coverage:** Full-document chunking (1500-char windows, 200-char overlap) instead of truncation
> - **Install:** `pip install -e ".[vector]"` (optional extra — core MCP works without it)
>
> All other data-flow and integration points (indexer → db → search_vault) were implemented as originally proposed.

## 1. Executive Summary

This proposal suggests enhancing the `@obsidian-mcp` server by integrating a **Local Vector Database (ChromaDB)** and a **Local Embedding Model (SentenceTransformers)**. This moves beyond the original design philosophy of "no vector DB complexity" to unlock Phase 4 capabilities (Advanced Graph Reasoning) earlier, enabling true semantic search and content similarity analysis without reliance on external APIs.

## 2. Motivation

The current "hybrid" search relies on:

1.  **Ripgrep**: Exact string matching (brittle, misses synonyms).
2.  **SQLite FTS**: Keyword matching (better, but misses conceptual similarity).
3.  **Graph Edges**: Explicit LLM-extracted relationships (high quality but sparse).

**The Gap:** There is no mechanism to find notes that discuss the _same concept_ using _different words_ (e.g., "sleep hygiene" vs. "insomnia protocol") unless they are explicitly linked or share keywords.

**Solution:** Vector embeddings map text to a high-dimensional semantic space. "King" and "Queen" are mathematically close, as are "Python" and "coding".

## 3. Proposed Architecture

### 3.1 The Stack

We will use a purely local, open-source stack to maintain privacy and offline capability.

| Component       | Choice                   | Justification                                                                                                                 |
| :-------------- | :----------------------- | :---------------------------------------------------------------------------------------------------------------------------- |
| **Vector DB**   | **ChromaDB**             | Industry standard, robust Python client, zero-config local persistence (Parquet/SQLite), handles HNSW indexing automatically. |
| **Embeddings**  | **SentenceTransformers** | HuggingFace standard. Model: `all-MiniLM-L6-v2`.                                                                              |
| **Model Specs** | `all-MiniLM-L6-v2`       | Fast inference, small footprint (~80MB), 384 dimensions. Ideal for CPU-only local environments.                               |

### 3.2 Data Flow

1.  **Indexing**:
    - `indexer.py` reads a markdown file.
    - If content changed -> Compute embedding via `sentence-transformers`.
    - Store `(ID=filename, Vector=embedding, Metadata={path, tags})` in ChromaDB.
2.  **Searching**:
    - User queries "how to fix sleep schedule".
    - Query is embedded into vector space.
    - ChromaDB returns nearest neighbors (e.g., `Huberman_Sleep_Toolkit.md`).
3.  **Storage**:
    - Database lives in `VAULT_PATH/.obsidian/chroma_db/`.

## 4. Implementation Plan

### 4.1 Dependencies

Update `pyproject.toml` to include:

```toml
chromadb>=0.4.0
sentence-transformers>=2.2.0
```

### 4.2 New Module: `src/obsidian_mcp/vectors.py`

A centralized module to handle the heavy lifting:

- `get_chroma_client()`: Returns singleton persistent client.
- `upsert_embedding(filename, content, metadata)`: Handles tokenization and storage.
- `search_vectors(query, limit)`: Performs k-NN search.

### 4.3 Integration Points

**A. `src/obsidian_mcp/indexer.py`**
Modify the main build loop to call `upsert_embedding`:

```python
# ... inside loop ...
upsert_note(...) # Existing SQLite
upsert_embedding(filename, content, ...) # NEW
```

**B. `src/obsidian_mcp/tools.py`**
Update `search_vault` to accept a `semantic` flag (or default to hybrid):

```python
def search_vault(query, ...):
    # ... ripgrep ...
    # ... fts ...
    # ... graph ...

    # NEW
    semantic_results = vectors.search_vectors(query)
    results.append("=== SEMANTIC MATCHES ===")
    # ... format results ...
```

**C. `src/obsidian_mcp/config.py`**
Add configuration for embedding model name and vector DB path.

## 5. Trade-offs

| Pros                                                           | Cons                                                                         |
| :------------------------------------------------------------- | :--------------------------------------------------------------------------- |
| **Semantic Understanding**: Finds "meaning" not just keywords. | **Dependency Weight**: Adds ~500MB+ dependencies (`torch`, `chroma`).        |
| **Zero Cost**: No API fees for embeddings.                     | **Indexing Speed**: Slower than regex. Initial full index will take minutes. |
| **Privacy**: Data never leaves the machine.                    | **Complexity**: Managing another DB state (though Chroma is simple).         |

## 6. Migration Strategy

1.  **Lazy Migration**: The first time the new version runs, it detects a missing vector store.
2.  **Background Build**: It can iterate through all notes (using existing `indexer.py` logic) to populate the vectors.
3.  **Status**: Add a `vector_store_size` metric to `vault_stats`.

## 7. Next Steps

1.  Approve this proposal.
2.  Create `vectors.py` prototype.
3.  Test performance on the current vault size.
