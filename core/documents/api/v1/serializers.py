from rest_framework import serializers

from accounts.models.users import User
from documents.models import Document

# The model's FileExtensionValidator already rejects non-PDF
# extensions, but it enforces no size limit at all, so the 20 MB
# limit is only ever enforced here, at the API level.
MAX_DOCUMENT_SIZE_BYTES = 20 * 1024 * 1024


class DocumentCreateSerializer(serializers.ModelSerializer):
    """
    Input for POST .../documents/. Only `title` and `file` are
    accepted — `organization` comes from the URL and `uploaded_by`
    from request.user (both set explicitly by the view), and
    `status`/`error_message`/`processed_at` don't exist on this
    serializer at all, so nothing a client sends for them is ever read.
    """

    class Meta:
        model = Document
        fields = ["id", "title", "file"]
        read_only_fields = ["id"]

    def validate_file(self, value):
        if not value.name.lower().endswith(".pdf"):
            raise serializers.ValidationError("Only PDF files are allowed.")
        if value.size > MAX_DOCUMENT_SIZE_BYTES:
            raise serializers.ValidationError("File size must not exceed 20 MB.")
        return value


class DocumentUploaderSerializer(serializers.ModelSerializer):
    """Minimal, safe uploader representation — no password or other account details."""

    class Meta:
        model = User
        fields = ["id", "email"]
        read_only_fields = fields


class DocumentListSerializer(serializers.ModelSerializer):
    """
    Output for GET .../documents/. `file` serializes to its URL (DRF's
    default FileField representation), never a filesystem path.
    """
    uploaded_by = DocumentUploaderSerializer(read_only=True)

    class Meta:
        model = Document
        fields = ["id", "title", "file", "file_size", "status", "uploaded_by", "created_at", "processed_at"]
        read_only_fields = fields


class DocumentDetailSerializer(serializers.ModelSerializer):
    """Output for the create response and GET .../documents/{id}/ —
    adds `organization` and `error_message` on top of the list fields."""
    uploaded_by = DocumentUploaderSerializer(read_only=True)

    class Meta:
        model = Document
        fields = [
            "id",
            "title",
            "organization",
            "uploaded_by",
            "file",
            "file_size",
            "status",
            "error_message",
            "created_at",
            "updated_at",
            "processed_at",
        ]
        read_only_fields = fields