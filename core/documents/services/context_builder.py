class ContextBuildingError(Exception):
    """Raised when context building fails."""


def build_context(chunks):
    """
    Build a structured context string from retrieved document chunks.
    """

    if not chunks:
        return ""

    try:
        context_parts = []

        for index, chunk in enumerate(chunks, start=1):
            context_parts.append(
                f"[Source {index}]\n"
                f"Document: {chunk.document.title}\n"
                f"Page: {chunk.page_number}\n"
                f"Content:\n{chunk.content}"
            )

        return "\n\n".join(context_parts)

    except Exception as exc:
        raise ContextBuildingError(
            "Failed to build context from document chunks."
        ) from exc