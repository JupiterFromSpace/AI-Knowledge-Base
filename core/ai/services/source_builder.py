class SourceBuildingError(Exception):
    """Raised when source building fails."""


def build_sources(chunks):
    """
    Build source metadata from retrieved document chunks.
    """

    if not chunks:
        return []

    try:
        sources = []

        for index, chunk in enumerate(chunks, start=1):
            sources.append(
                {
                    "source_number": index,
                    "document_id": str(chunk.document.id),
                    "document_title": chunk.document.title,
                    "page_number": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                }
            )

        return sources

    except Exception as exc:
        raise SourceBuildingError(
            "Failed to build sources."
        ) from exc