import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from documents.models import Document, DocumentChunk, DocumentStatus
from documents.services.chunker import chunk_pages
from documents.services.embedder import (
    EmbeddingGenerationError,
    generate_document_embedding,
)
from documents.services.pdf_extractor import (
    PDFExtractionError,
    extract_text_by_page,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 60
MAX_RETRY_DELAY = 600


@shared_task(
    bind=True,
    max_retries=MAX_RETRIES,
    name="documents.process_document",
)
def process_document(self, document_id: str) -> None:
    """
    Process a document in the background:

    PDF extraction
    -> chunking
    -> chunk persistence
    -> embedding generation
    -> embedding persistence
    -> COMPLETED
    """

    is_retry = self.request.retries > 0

    document = _acquire_document_for_processing(
        document_id=document_id,
        is_retry=is_retry,
    )

    if document is None:
        return

    try:
        # On the first attempt, rebuild all derived chunks from the PDF.
        # On retries, keep existing chunks so already-generated embeddings
        # do not need to be generated again.
        if not is_retry:
            _prepare_fresh_processing(document)

        if not is_retry or not document.chunks.exists():
            pages = extract_text_by_page(document.file)
            chunks = chunk_pages(pages)

            if not chunks:
                _mark_failed(
                    document.id,
                    "The document contains no extractable text.",
                )
                return

            _persist_chunks(document, chunks)

        _generate_missing_embeddings(document)

        _mark_completed(document.id)

        logger.info(
            "Document %s processed successfully.",
            document.id,
        )

    except PDFExtractionError:
        logger.exception(
            "PDF extraction failed for document %s.",
            document.id,
        )

        _mark_failed(
            document.id,
            "The document could not be processed as a PDF.",
        )

    except EmbeddingGenerationError as exc:
        logger.exception(
            "Embedding generation failed for document %s. "
            "Retry %s/%s.",
            document.id,
            self.request.retries,
            MAX_RETRIES,
        )

        if self.request.retries < MAX_RETRIES:
            countdown = min(
                INITIAL_RETRY_DELAY * (2 ** self.request.retries),
                MAX_RETRY_DELAY,
            )

            raise self.retry(
                exc=exc,
                countdown=countdown,
            ) from exc

        _mark_failed(
            document.id,
            "Embedding generation failed after multiple attempts.",
        )

    except Exception:
        logger.exception(
            "Unexpected document processing failure for document %s.",
            document.id,
        )

        _mark_failed(
            document.id,
            "The document could not be processed.",
        )

        raise


def _acquire_document_for_processing(
    *,
    document_id: str,
    is_retry: bool,
) -> Document | None:
    """
    Atomically decide whether this task is allowed to process the document.

    Fresh task:
        PENDING / FAILED -> PROCESSING

    Retry:
        PROCESSING -> continue

    Already completed documents are ignored.
    A second fresh task arriving while another task is processing is ignored.
    """

    try:
        with transaction.atomic():
            document = (
                Document.objects
                .select_for_update()
                .get(pk=document_id)
            )

            if document.status == DocumentStatus.COMPLETED:
                logger.info(
                    "Document %s is already completed.",
                    document.id,
                )
                return None

            if is_retry:
                if document.status != DocumentStatus.PROCESSING:
                    logger.warning(
                        "Retry received for document %s, but its status is %s.",
                        document.id,
                        document.status,
                    )
                    return None

                return document

            if document.status == DocumentStatus.PROCESSING:
                logger.warning(
                    "Document %s is already being processed.",
                    document.id,
                )
                return None

            if document.status not in (
                DocumentStatus.PENDING,
                DocumentStatus.FAILED,
            ):
                logger.warning(
                    "Document %s has unsupported status %s.",
                    document.id,
                    document.status,
                )
                return None

            document.status = DocumentStatus.PROCESSING
            document.error_message = None
            document.processed_at = None
            document.save(
                update_fields=[
                    "status",
                    "error_message",
                    "processed_at",
                    "updated_at",
                ]
            )

            return document

    except Document.DoesNotExist:
        logger.warning(
            "Document %s no longer exists.",
            document_id,
        )
        return None


def _prepare_fresh_processing(document: Document) -> None:
    """
    Delete derived chunks from a previous processing attempt.

    Document itself is never deleted.
    """

    DocumentChunk.objects.filter(
        document=document,
    ).delete()


def _persist_chunks(
    document: Document,
    chunks: list[dict],
) -> None:
    """
    Persist extracted chunks with NULL embeddings.

    Embeddings are generated separately so we never hold a database
    transaction open while waiting for Gemini.
    """

    chunk_objects = [
        DocumentChunk(
            document=document,
            chunk_index=chunk["chunk_index"],
            page_number=chunk["page_number"],
            content=chunk["content"],
            metadata=chunk.get("metadata", {}),
        )
        for chunk in chunks
    ]

    DocumentChunk.objects.bulk_create(chunk_objects)


def _generate_missing_embeddings(document: Document) -> None:
    """
    Generate and save embeddings only for chunks that do not already
    have one.

    This makes Celery retries resumable.
    """

    chunks = list(
        DocumentChunk.objects
        .filter(document=document)
        .order_by("chunk_index")
    )

    if not chunks:
        raise EmbeddingGenerationError(
            "No document chunks are available for embedding."
        )

    for chunk in chunks:
        if chunk.embedding is not None:
            continue

        embedding = generate_document_embedding(
            chunk.content,
            title=document.title,
        )

        with transaction.atomic():
            DocumentChunk.objects.filter(
                pk=chunk.pk,
                embedding__isnull=True,
            ).update(
                embedding=embedding,
            )


def _mark_completed(document_id: str) -> None:
    """
    Mark the document completed only when every chunk has an embedding.
    """

    with transaction.atomic():
        document = (
            Document.objects
            .select_for_update()
            .get(pk=document_id)
        )

        if DocumentChunk.objects.filter(
            document=document,
            embedding__isnull=True,
        ).exists():
            raise EmbeddingGenerationError(
                "Not all document chunks have embeddings."
            )

        document.status = DocumentStatus.COMPLETED
        document.error_message = None
        document.processed_at = timezone.now()

        document.save(
            update_fields=[
                "status",
                "error_message",
                "processed_at",
                "updated_at",
            ]
        )


def _mark_failed(
    document_id: str,
    message: str,
) -> None:
    """
    Store only a safe human-readable error in the database.
    """

    try:
        with transaction.atomic():
            document = (
                Document.objects
                .select_for_update()
                .get(pk=document_id)
            )

            document.status = DocumentStatus.FAILED
            document.error_message = message
            document.processed_at = None

            document.save(
                update_fields=[
                    "status",
                    "error_message",
                    "processed_at",
                    "updated_at",
                ]
            )

    except Document.DoesNotExist:
        logger.warning(
            "Could not mark missing document %s as failed.",
            document_id,
        )