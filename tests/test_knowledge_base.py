"""
Unit tests for the knowledge base chunker.

We test the pure chunking logic directly — it's the only piece that
runs without the embedding model loaded.
"""

import pytest

from ai.knowledge_base import _split_into_chunks


class TestSplitIntoChunks:
    def test_short_text_single_chunk(self) -> None:
        text = "This is a short document."
        chunks = _split_into_chunks(text)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_empty_text_no_chunks(self) -> None:
        assert _split_into_chunks("") == []
        assert _split_into_chunks("   \n  \n") == []

    def test_paragraphs_become_chunks_when_large(self) -> None:
        paragraphs = [f"Paragraph {i}. " * 200 for i in range(5)]
        text = "\n\n".join(paragraphs)
        chunks = _split_into_chunks(text)
        assert len(chunks) >= 5

    def test_long_paragraph_splits(self) -> None:
        # A single 10,000-char paragraph should be split.
        text = "x" * 10_000
        chunks = _split_into_chunks(text)
        assert len(chunks) > 1
        # Each chunk should respect the max-chars limit
        for chunk in chunks:
            assert len(chunk) <= 2100  # max_chars + minor slack

    def test_respects_markdown_headers(self) -> None:
        text = (
            "# Section 1\n\nContent A.\n\n"
            "# Section 2\n\nContent B.\n\n"
            "# Section 3\n\nContent C."
        )
        chunks = _split_into_chunks(text)
        # All three sections fit in one chunk; we just check no crash
        # and content is preserved.
        joined = " ".join(chunks)
        assert "Section 1" in joined
        assert "Section 2" in joined
        assert "Section 3" in joined
