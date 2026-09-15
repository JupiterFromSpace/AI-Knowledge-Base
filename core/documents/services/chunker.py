"""
Text chunking.

Splits page-level extracted text (the output of
`documents.services.pdf_extractor.extract_text_by_page`) into
paragraph/sentence-aware chunks sized for embedding later. This module
knows nothing about embeddings, pgvector, Celery, or the Document
model — it's a pure function: structured pages in, structured chunk
dicts out. Persisting the result as DocumentChunk rows is a job for a
later task/service layer, not this one.
"""
import re

# Chunk size is controlled in *estimated* tokens, not characters or
# words — see estimate_tokens() below for why and how.
TARGET_CHUNK_TOKENS = 650  # midpoint of the requested 500-800 range
MAX_CHUNK_TOKENS = 800  # hard ceiling; a chunk is closed once it would exceed this
OVERLAP_TOKENS = 75  # midpoint of the requested 50-100 range

_PARAGRAPH_BOUNDARY_RE = re.compile(r"\n\s*\n")
# Splits after sentence-ending punctuation, but only when followed by
# whitespace and what looks like the start of a new sentence (capital
# letter, digit, or opening quote) — a deliberately simple heuristic,
# not a full NLP sentence tokenizer.
_SENTENCE_BOUNDARY_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z0-9"\'\(])')


def estimate_tokens(text: str) -> int:
    """
    Rough token estimate: ~4 characters per token, the same heuristic
    commonly cited for English text with GPT-family tokenizers. Cheap,
    dependency-free, and precise enough to keep chunks in the right
    ballpark — this is the one function to replace with a real
    tokenizer later, without touching the chunking algorithm itself.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


def chunk_pages(
    pages: list[dict],
    *,
    target_tokens: int = TARGET_CHUNK_TOKENS,
    max_tokens: int = MAX_CHUNK_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[dict]:
    """
    Chunk page-level text for embedding.

    `pages` matches the output of `extract_text_by_page`:
    ``[{"page_number": int, "text": str}, ...]``. Pages with empty or
    whitespace-only text are skipped entirely.

    Returns a list of chunk dicts, in document order, ready to map
    onto DocumentChunk fields:

        [
            {
                "chunk_index": 0,
                "page_number": 1,
                "content": "...",
                "metadata": {"token_estimate": 612},
            },
            ...
        ]

    `chunk_index` is 0-based and sequential across the whole document
    (not restarted per page) — it's a programmatic ordering, unlike
    the human-facing, 1-based `page_number`.
    """
    chunks = []
    chunk_index = 0

    for page in pages:
        text = (page.get("text") or "").strip()
        if not text:
            continue

        units = _build_units(text, max_tokens)
        for content in _pack_units(units, target_tokens, max_tokens, overlap_tokens):
            content = content.strip()
            if not content:
                continue
            chunks.append(
                {
                    "chunk_index": chunk_index,
                    "page_number": page["page_number"],
                    "content": content,
                    "metadata": {"token_estimate": estimate_tokens(content)},
                }
            )
            chunk_index += 1

    return chunks


def _split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in _PARAGRAPH_BOUNDARY_RE.split(text) if p.strip()]


def _split_sentences(paragraph: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_BOUNDARY_RE.split(paragraph) if s.strip()]


def _hard_split(text: str, max_tokens: int) -> list[str]:
    """
    Word-boundary fallback split, used only when a single sentence is
    itself larger than max_tokens (e.g. a huge run-on paragraph with
    no punctuation). This is what guarantees the packer below can
    always make forward progress, even on pathological input.
    """
    words = text.split()
    if not words:
        return []

    pieces = []
    current: list[str] = []
    for word in words:
        current.append(word)
        if estimate_tokens(" ".join(current)) >= max_tokens:
            pieces.append(" ".join(current))
            current = []
    if current:
        pieces.append(" ".join(current))
    return pieces


def _build_units(text: str, max_tokens: int) -> list[str]:
    """Flattens a page's text into an ordered list of sentence-sized
    "units", none of which exceed max_tokens on their own."""
    units = []
    for paragraph in _split_paragraphs(text):
        for sentence in _split_sentences(paragraph):
            if estimate_tokens(sentence) > max_tokens:
                units.extend(_hard_split(sentence, max_tokens))
            else:
                units.append(sentence)
    return units


def _take_overlap(units: list[str], overlap_tokens: int) -> list[str]:
    """
    Returns the trailing units (in original order) whose combined
    token estimate is as close as possible to overlap_tokens without
    exceeding it — used to seed the next chunk so adjacent chunks
    share context without ever cutting a sentence in half.

    A unit that alone already exceeds overlap_tokens (this only
    happens with a hard-split fallback piece from a huge, punctuation-
    less run of text) is never used as overlap at all, rather than
    seeding the next chunk with an oversized piece that could then
    combine with new content to exceed max_tokens.
    """
    if overlap_tokens <= 0:
        return []

    overlap: list[str] = []
    total = 0
    for unit in reversed(units):
        unit_tokens = estimate_tokens(unit)
        if unit_tokens > overlap_tokens:
            break
        if overlap and total + unit_tokens > overlap_tokens:
            break
        overlap.insert(0, unit)
        total += unit_tokens
    return overlap


def _pack_units(units: list[str], target_tokens: int, max_tokens: int, overlap_tokens: int) -> list[str]:
    """
    Greedily accumulates units into chunks: closes a chunk (and seeds
    the next one with overlap) once it would exceed max_tokens, or
    once it reaches target_tokens. A chunk is only ever emitted if it
    contains at least one unit beyond pure carried-over overlap, and
    never if it would be an exact duplicate of the previous chunk —
    both guard against empty/duplicate output on short or edge-case
    input.
    """
    if not units:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0
    added_new_since_flush = False

    def flush():
        nonlocal current, current_tokens, added_new_since_flush
        text = " ".join(current)
        if not chunks or chunks[-1] != text:
            chunks.append(text)
        current = _take_overlap(current, overlap_tokens)
        current_tokens = sum(estimate_tokens(u) for u in current)
        added_new_since_flush = False

    for unit in units:
        unit_tokens = estimate_tokens(unit)

        if current and current_tokens + unit_tokens > max_tokens:
            flush()

        current.append(unit)
        current_tokens += unit_tokens
        added_new_since_flush = True

        if current_tokens >= target_tokens:
            flush()

    if current and added_new_since_flush:
        text = " ".join(current)
        if not chunks or chunks[-1] != text:
            chunks.append(text)

    return chunks