"""
Text embedding generation via Gemini Embedding 2.

A small, focused service: format a document chunk's text the way
Gemini Embedding 2 expects for retrieval, call the API, and return a
plain vector. It does not know about DocumentChunk, Celery, pgvector,
or API views — persisting or searching the vector is a job for a
later stage.
"""
import logging

from django.conf import settings
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "gemini-embedding-2"
EMBEDDING_DIMENSIONS = 768


class EmbeddingGenerationError(Exception):
    """
    Raised whenever an embedding could not be produced — a Gemini API
    failure, a missing/invalid API key, or an unexpected response shape.

    Wraps the real cause (logged separately via `logger.exception`,
    never included in this message) so callers only ever need to
    handle one predictable exception type instead of depending on the
    Gemini SDK's own exception hierarchy. The message here is always
    safe to surface to a caller or log without leaking API keys or
    document content.
    """


_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """
    Lazily builds and caches a single genai.Client for the process,
    rather than constructing a new one for every embedding call.
    Django settings (backed by python-decouple, matching this
    project's existing configuration style) is the only source of the
    API key — it is never hard-coded.
    """
    global _client
    if _client is None:
        api_key = getattr(settings, "GEMINI_API_KEY", None)
        if not api_key:
            raise EmbeddingGenerationError("Gemini API key is not configured.")
        _client = genai.Client(api_key=api_key)
    return _client


def generate_document_embedding(content: str, *, title: str | None = None) -> list[float]:
    """
    Generate a retrieval-oriented embedding for a document chunk.

    Gemini Embedding 2 has no `task_type` parameter (unlike the older
    gemini-embedding-001) — retrieval intent is conveyed through the
    input text itself, using Google's recommended document format:

        title: {title} | text: {content}

    or, when no title is available:

        title: none | text: {content}

    That formatting is applied only to the text sent to Gemini —
    DocumentChunk.content itself is never touched or reshaped.

    Raises:
        ValueError: `content` is empty or whitespace-only. This is a
            caller-input error, checked before any API call is made,
            so it's kept distinct from EmbeddingGenerationError below.
        EmbeddingGenerationError: the API call fails, the API key is
            missing, or the response is missing/malformed. An empty
            or partial vector is never returned silently.
    """
    if not content or not content.strip():
        raise ValueError("content must not be empty.")

    formatted_text = _format_document_text(content, title)
    return _embed(formatted_text)


def _format_document_text(content: str, title: str | None) -> str:
    title_value = title.strip() if title and title.strip() else "none"
    return f"title: {title_value} | text: {content}"


def _embed(text: str) -> list[float]:
    """
    The actual Gemini call and response validation, shared by every
    embedding "flavor". A future `generate_query_embedding(query)`
    would apply its own, query-oriented text formatting and then call
    this same function — the client, the API call, and the response
    validation never need to be duplicated for that to work.
    """
    client = _get_client()

    try:
        response = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text,
            config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIMENSIONS),
        )
    except Exception as exc:
        # Never log the text itself (it may be sensitive document
        # content) or the API key — only enough to debug from.
        logger.exception("Gemini embedding request failed for a %d-character input", len(text))
        raise EmbeddingGenerationError("The embedding provider request failed.") from exc

    return _extract_and_validate_vector(response)


def _extract_and_validate_vector(response) -> list[float]:
    embeddings = getattr(response, "embeddings", None)
    if not embeddings:
        raise EmbeddingGenerationError("The embedding provider returned no embedding.")

    values = getattr(embeddings[0], "values", None)
    if not values:
        raise EmbeddingGenerationError("The embedding provider returned no embedding.")

    if len(values) != EMBEDDING_DIMENSIONS:
        raise EmbeddingGenerationError(
            f"The embedding provider returned {len(values)} dimensions, expected {EMBEDDING_DIMENSIONS}."
        )

    if not all(isinstance(v, (int, float)) for v in values):
        raise EmbeddingGenerationError("The embedding provider returned non-numeric values.")

    return list(values)