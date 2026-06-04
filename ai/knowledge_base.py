"""
Knowledge base loader and RAG search.

Loads every `.md` and `.txt` file from the configured directory,
splits them into overlapping chunks, embeds each chunk with
`fastembed` (BGE-small, ONNX, runs on CPU), and stores everything
in memory.

At query time:
  1. Embed the query
  2. Compute cosine similarity against all chunk embeddings
  3. Return the top-K chunks

For the data volumes this bot handles (knowledge bases up to ~10k
chunks), in-memory linear search is faster than spinning up a
vector DB and accounts for ~1ms per query. No need to over-engineer.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from fastembed import TextEmbedding
from loguru import logger


_EMBED_MODEL = "BAAI/bge-small-en-v1.5"
_CHUNK_TOKENS = 500       # approximate; we use character ~ token / 4 heuristic
_CHUNK_OVERLAP = 50       # tokens of overlap between adjacent chunks
_CHARS_PER_TOKEN = 4      # rough English average


@dataclass(frozen=True)
class Chunk:
    """A single retrievable chunk of the knowledge base."""

    source: str          # filename it came from
    text: str            # the chunk's text content
    embedding: np.ndarray = None  # type: ignore[assignment]


class KnowledgeBase:
    """In-memory RAG index for a directory of markdown/text files."""

    def __init__(self, knowledge_dir: Path, top_k: int = 3) -> None:
        self._dir = knowledge_dir
        self._top_k = top_k
        self._chunks: list[Chunk] = []
        self._embeddings: np.ndarray | None = None
        self._embedder: TextEmbedding | None = None

    def __len__(self) -> int:
        return len(self._chunks)

    async def initialize(self) -> None:
        """Load the embedding model and index all files in the directory."""
        # Embedder loads ONNX weights; happens once at startup.
        self._embedder = await asyncio.to_thread(TextEmbedding, model_name=_EMBED_MODEL)
        await self.reload()

    async def reload(self) -> int:
        """Re-read every file from disk and rebuild the index. Returns file count."""
        if self._embedder is None:
            raise RuntimeError("KnowledgeBase not initialized")

        files = sorted(
            list(self._dir.rglob("*.md")) + list(self._dir.rglob("*.txt"))
        )
        if not files:
            logger.warning("No knowledge files found in {}", self._dir)
            self._chunks = []
            self._embeddings = None
            return 0

        new_chunks: list[Chunk] = []
        for path in files:
            text = path.read_text(encoding="utf-8")
            for chunk_text in _split_into_chunks(text):
                new_chunks.append(Chunk(source=path.name, text=chunk_text))

        # Compute embeddings (blocking; offload to a thread)
        texts = [c.text for c in new_chunks]
        embeddings = await asyncio.to_thread(
            lambda: np.array(list(self._embedder.embed(texts)))  # type: ignore[union-attr]
        )

        # Replace embedding field on each chunk (frozen dataclass — use object.__setattr__)
        for chunk, vec in zip(new_chunks, embeddings):
            object.__setattr__(chunk, "embedding", vec)

        self._chunks = new_chunks
        self._embeddings = embeddings
        logger.info(
            "Indexed {} chunks from {} files in {}",
            len(new_chunks),
            len(files),
            self._dir,
        )
        return len(files)

    async def search(self, query: str) -> list[Chunk]:
        """Return the top-K chunks most similar to `query`."""
        if not self._chunks or self._embeddings is None or self._embedder is None:
            return []

        query_vec = await asyncio.to_thread(
            lambda: next(self._embedder.embed([query]))  # type: ignore[union-attr]
        )
        query_vec = np.asarray(query_vec)

        # Cosine similarity (embeddings from fastembed BGE are already L2-normalized)
        sims = self._embeddings @ query_vec
        top_idx = np.argsort(sims)[::-1][: self._top_k]

        # Filter out very low-similarity hits — better to return nothing
        # than wave a misleading chunk at the model.
        return [self._chunks[i] for i in top_idx if sims[i] > 0.35]


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def _split_into_chunks(text: str) -> list[str]:
    """
    Split markdown/text into overlapping chunks.

    We try to respect paragraph and header boundaries first. If a
    paragraph is too large to fit, we fall back to a sliding character
    window. This is simple but robust for documentation-style content.
    """
    # Split on blank lines (paragraphs) and ATX headers.
    paragraphs = re.split(r"\n{2,}|(?=^#+\s)", text, flags=re.MULTILINE)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    max_chars = _CHUNK_TOKENS * _CHARS_PER_TOKEN
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        # If adding this paragraph would overflow the chunk, emit and reset.
        if current and len(current) + len(para) + 2 > max_chars:
            chunks.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para

        # If a single paragraph is itself too long, slide-window over it.
        while len(current) > max_chars:
            chunks.append(current[:max_chars])
            current = current[max_chars - _CHUNK_OVERLAP * _CHARS_PER_TOKEN :]

    if current:
        chunks.append(current)

    return chunks
