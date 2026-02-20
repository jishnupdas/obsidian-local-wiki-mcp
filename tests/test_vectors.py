"""
Tests for the vectors.py module and vector-related db.py helpers.

Uses mocking throughout so the tests pass even when the optional
[vector] extras (sqlite-vec, fastembed) are not installed.
"""

from __future__ import annotations

import struct
from unittest.mock import MagicMock, patch


# =============================================================================
# vectors.py tests
# =============================================================================


class TestIsAvailable:
    def test_returns_true_when_deps_present(self):
        """is_available() returns True when both sqlite_vec and fastembed import fine."""
        import obsidian_mcp.vectors as vec_module

        # Reset cached value so the import check runs fresh
        vec_module._AVAILABLE = None

        with patch.dict("sys.modules", {"sqlite_vec": MagicMock(), "fastembed": MagicMock()}):
            result = vec_module.is_available()
        assert result is True

        vec_module._AVAILABLE = None  # cleanup

    def test_returns_false_when_deps_missing(self):
        """is_available() returns False and does not raise when deps are missing."""
        import obsidian_mcp.vectors as vec_module

        vec_module._AVAILABLE = None

        with patch("builtins.__import__", side_effect=ImportError("no module")):
            result = vec_module.is_available()

        assert result is False
        vec_module._AVAILABLE = None  # cleanup

    def test_cached_after_first_call(self):
        """is_available() returns a cached value without re-importing."""
        import obsidian_mcp.vectors as vec_module

        vec_module._AVAILABLE = True
        result = vec_module.is_available()
        assert result is True

        vec_module._AVAILABLE = None  # cleanup


class TestChunkText:
    def setup_method(self):
        from obsidian_mcp.vectors import chunk_text

        self.chunk_text = chunk_text

    def test_short_text_returns_single_chunk(self):
        text = "Hello world"
        chunks = self.chunk_text(text, size=100, overlap=10)
        assert chunks == [text]

    def test_exact_size_returns_single_chunk(self):
        text = "a" * 1500
        chunks = self.chunk_text(text, size=1500, overlap=200)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_long_text_is_split(self):
        text = "a" * 3000
        chunks = self.chunk_text(text, size=1500, overlap=200)
        assert len(chunks) > 1

    def test_chunks_have_overlap(self):
        """Adjacent chunks share ``overlap`` characters."""
        text = "abcdefghij"  # 10 chars
        chunks = self.chunk_text(text, size=4, overlap=1)
        # chunk 0: "abcd", chunk 1: "defg", chunk 2: "ghij"
        assert chunks[0][-1] == chunks[1][0]  # 'd' appears in both

    def test_no_characters_lost(self):
        """Reassembling chunks without overlap covers the full original text."""
        text = "x" * 5000
        chunks = self.chunk_text(text, size=1500, overlap=200)
        step = 1500 - 200
        reconstructed = chunks[0]
        for chunk in chunks[1:]:
            reconstructed += chunk[200:]  # skip overlap
        # Should cover full length (last chunk may extend beyond step boundary)
        assert len(reconstructed) >= len(text)


class TestEmbedHelpers:
    def test_embed_returns_list_of_floats(self):
        """embed() converts numpy array to list[float]."""
        import numpy as np
        from obsidian_mcp import vectors as vec_module

        fake_model = MagicMock()
        fake_model.embed.return_value = iter([np.array([0.1] * 384, dtype=np.float32)])

        vec_module._model = None
        with patch.object(vec_module, "get_model", return_value=fake_model):
            result = vec_module.embed("hello world")

        assert isinstance(result, list)
        assert len(result) == 384
        assert all(isinstance(v, float) for v in result)

    def test_embed_batch_returns_list_of_lists(self):
        """embed_batch() returns one list[float] per input text."""
        import numpy as np
        from obsidian_mcp import vectors as vec_module

        fake_model = MagicMock()
        fake_model.embed.return_value = iter([
            np.array([0.1] * 384, dtype=np.float32),
            np.array([0.2] * 384, dtype=np.float32),
        ])

        with patch.object(vec_module, "get_model", return_value=fake_model):
            result = vec_module.embed_batch(["text one", "text two"])

        assert len(result) == 2
        assert len(result[0]) == 384
        assert len(result[1]) == 384

    def test_embed_batch_empty_returns_empty(self):
        from obsidian_mcp import vectors as vec_module

        result = vec_module.embed_batch([])
        assert result == []


# =============================================================================
# db.py vector helper tests
# =============================================================================


class TestSearchVaultSemanticFlag:
    def test_no_semantic_section_when_unavailable(self, tmp_path):
        """search_vault does not crash and skips semantic when vectors unavailable."""
        with patch("obsidian_mcp.tools.vectors") as mock_vec:
            mock_vec.is_available.return_value = False

            from obsidian_mcp.tools import search_vault

            with (
                patch("obsidian_mcp.tools.search_fts", return_value=[]),
                patch("obsidian_mcp.tools.search_edges", return_value=[]),
                patch("subprocess.run") as mock_run,
            ):
                mock_run.return_value = MagicMock(stdout="", returncode=1)
                result = search_vault("test query", include_semantic=True)

        assert "SEMANTIC MATCHES" not in result

    def test_semantic_section_present_when_available(self):
        """search_vault includes SEMANTIC MATCHES when vectors available and results found."""
        import numpy as np

        with patch("obsidian_mcp.tools.vectors") as mock_vec:
            mock_vec.is_available.return_value = True
            mock_vec.embed.return_value = [0.1] * 384

            with (
                patch("obsidian_mcp.tools.search_vectors") as mock_sv,
                patch("obsidian_mcp.tools.search_fts", return_value=[]),
                patch("obsidian_mcp.tools.search_edges", return_value=[]),
                patch("subprocess.run") as mock_run,
            ):
                mock_run.return_value = MagicMock(stdout="", returncode=1)
                mock_sv.return_value = [{"filename": "Test_Note.md", "distance": 0.1}]

                from obsidian_mcp.tools import search_vault

                result = search_vault("semantic concept", include_semantic=True)

        assert "SEMANTIC MATCHES" in result
        assert "Test_Note.md" in result


class TestVaultStatsVectorCount:
    def test_stats_include_vector_count_when_available(self):
        """vault_stats shows vector store count when sqlite-vec is installed."""
        with patch("obsidian_mcp.tools.vectors") as mock_vec:
            mock_vec.is_available.return_value = True

            with (
                patch("obsidian_mcp.tools.get_vector_count", return_value=42),
                patch("obsidian_mcp.tools.get_stats", return_value={
                    "total_notes": 10, "total_edges": 5, "total_claims": 3,
                    "folders": {}, "relations": {},
                }),
                patch("obsidian_mcp.tools.get_orphan_notes", return_value=[]),
                patch("obsidian_mcp.tools.get_most_connected", return_value=[]),
            ):
                from obsidian_mcp.tools import vault_stats

                result = vault_stats()

        assert "42 notes embedded" in result

    def test_stats_no_vector_line_when_unavailable(self):
        """vault_stats omits vector store line when sqlite-vec is not installed."""
        with patch("obsidian_mcp.tools.vectors") as mock_vec:
            mock_vec.is_available.return_value = False

            with (
                patch("obsidian_mcp.tools.get_stats", return_value={
                    "total_notes": 10, "total_edges": 5, "total_claims": 3,
                    "folders": {}, "relations": {},
                }),
                patch("obsidian_mcp.tools.get_orphan_notes", return_value=[]),
                patch("obsidian_mcp.tools.get_most_connected", return_value=[]),
            ):
                from obsidian_mcp.tools import vault_stats

                result = vault_stats()

        assert "Vector Store" not in result
