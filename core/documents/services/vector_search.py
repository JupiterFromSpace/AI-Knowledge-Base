from django.db.models import F, FloatField, ExpressionWrapper
from pgvector.django import CosineDistance

from documents.models import DocumentChunk


class VectorSearchError(Exception):
    """Raised when vector similarity search fails."""


def search_similar_chunks(
    query_embedding,
    organization_id,
    top_k=5,
):
    """
    Search for the most semantically similar document chunks
    within a specific organization.
    """

    if not query_embedding:
        raise ValueError("Query embedding cannot be empty.")

    if len(query_embedding) != 768:
        raise ValueError("Query embedding must have 768 dimensions.")

    if top_k <= 0:
        raise ValueError("top_k must be greater than zero.")

    try:
        similarity_distance = CosineDistance(
            "embedding",
            query_embedding,
        )

        chunks = (
            DocumentChunk.objects
            .filter(
                document__organization_id=organization_id,
                embedding__isnull=False,
            )
            .annotate(
                distance=similarity_distance,
            )
            .annotate(
                similarity=ExpressionWrapper(
                    1 - F("distance"),
                    output_field=FloatField(),
                )
            )
            .order_by("distance")[:top_k]
        )

        return chunks

    except Exception as exc:
        raise VectorSearchError(
            "Failed to perform vector similarity search."
        ) from exc