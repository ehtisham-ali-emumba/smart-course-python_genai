"""Text chunking for RAG indexing.

Splits lesson content into overlapping chunks suitable for embedding.
Uses LangChain's RecursiveCharacterTextSplitter which handles markdown,
paragraphs, and sentences intelligently.
"""

from dataclasses import dataclass
from langchain_text_splitters import RecursiveCharacterTextSplitter


@dataclass
class TextChunk:
    """A single chunk of text with its position metadata."""

    text: str
    chunk_index: int
    start_char: int
    end_char: int


# ── Configuration ─────────────────────────────────────────────
# text-embedding-3-small handles up to 8191 tokens.
# ~4 chars per token → 512 tokens ≈ 2048 chars.
# We use a conservative chunk size for better retrieval precision.
CHUNK_SIZE = 1500  # ~375 tokens per chunk
CHUNK_OVERLAP = 200  # ~50 tokens overlap (13%)

# Separators ordered from most to least preferred split point.
# The splitter tries the first separator, falls back to the next if chunks are still too big.
SEPARATORS = [
    "\n## ",  # Markdown H2 (module boundary)
    "\n### ",  # Markdown H3 (lesson boundary)
    "\n#### ",  # Markdown H4 (section boundary)
    "\n\n",  # Paragraph boundary
    "\n",  # Line boundary
    ". ",  # Sentence boundary
    " ",  # Word boundary
]


class TextChunker:
    """Splits text into overlapping chunks for RAG embedding."""

    def __init__(
        self,
        chunk_size: int = CHUNK_SIZE,
        chunk_overlap: int = CHUNK_OVERLAP,
    ):
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=SEPARATORS,
            length_function=len,
            is_separator_regex=False,
        )

    def chunk_text(self, text: str) -> list[TextChunk]:
        """Split text into chunks with position tracking.

        Args:
            text: The full text to split.

        Returns:
            List of TextChunk objects with text, index, and character positions.
        """
        if not text or not text.strip():
            return []

        docs = self._splitter.create_documents([text])

        chunks: list[TextChunk] = []
        search_start = 0

        for i, doc in enumerate(docs):
            chunk_text = doc.page_content

            # Track character positions for debugging/reference
            start_char = text.find(chunk_text[:50], search_start)
            if start_char == -1:
                start_char = search_start
            end_char = start_char + len(chunk_text)
            search_start = max(search_start, start_char + 1)

            chunks.append(
                TextChunk(
                    text=chunk_text,
                    chunk_index=i,
                    start_char=start_char,
                    end_char=end_char,
                )
            )

        return chunks
