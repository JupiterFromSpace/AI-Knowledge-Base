from django.contrib import admin

from documents.models import Document, DocumentChunk


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["title", "organization", "uploaded_by", "status", "file_size", "created_at", "processed_at"]
    list_filter = ["status", "organization"]
    search_fields = ["title", "organization__name", "uploaded_by__email"]
    autocomplete_fields = ["organization", "uploaded_by"]
    list_select_related = ["organization", "uploaded_by"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ["document", "chunk_index", "page_number", "created_at"]
    search_fields = ["document__title"]
    autocomplete_fields = ["document"]
    list_select_related = ["document"]
    ordering = ["document", "chunk_index"]
    readonly_fields = ["created_at"]