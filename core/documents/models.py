from django.db import models

import uuid

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from pgvector.django import VectorField


class DocumentStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    PROCESSING = "PROCESSING", "Processing"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"


class Document(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="documents",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="uploaded_documents",
    )
    title = models.CharField(
        max_length=255,
    )
    file = models.FileField(
        upload_to="documents/",
        validators=[
            FileExtensionValidator(
                allowed_extensions=["pdf"],
            ),
        ],
    )
    file_size = models.PositiveBigIntegerField()
    status = models.CharField(
        max_length=20,
        choices=DocumentStatus.choices,
        default=DocumentStatus.PENDING,
    )
    error_message = models.TextField(
        null=True,
        blank=True,
    )
    processed_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self):
        return self.title


class DocumentChunk(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    content = models.TextField()
    chunk_index = models.PositiveIntegerField()
    page_number = models.PositiveIntegerField(
        null=True,
        blank=True,
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
    )
    # Gemini Embedding 2, truncated via output_dimensionality=768 (see
    # documents.services.embedder). Nullable: a chunk is created by
    # the chunking stage before a later Celery step generates and
    # saves its embedding — those are two separate points in the
    # pipeline, not one atomic step.
    embedding = VectorField(
        dimensions=768,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["document", "chunk_index"],
                name="unique_document_chunk_index",
            ),
        ]
        ordering = ["chunk_index"]

    def __str__(self):
        return f"{self.document.title} - Chunk {self.chunk_index}"