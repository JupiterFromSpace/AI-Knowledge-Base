from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.utils.responses import APIResponse
from documents.api.v1.serializers import (
    DocumentCreateSerializer,
    DocumentDetailSerializer,
    DocumentListSerializer,
)
from documents.models import Document, DocumentStatus
from organizations.models import Membership, MembershipRole, Organization


def _get_membership(user, organization):
    """
    The caller's Membership for this *specific* organization, or None.
    Role is always evaluated per-organization — being ADMIN in one
    organization must never be assumed to mean ADMIN in another.
    """
    return Membership.objects.filter(user=user, organization=organization).first()


def _forbidden(detail):
    return APIResponse.error(
        errors={"detail": detail},
        message="You do not have permission to perform this action.",
        status_code=status.HTTP_403_FORBIDDEN,
    )


class DocumentListCreateView(generics.ListCreateAPIView):
    """GET (list org's documents, any member) / POST (upload, ADMIN only)."""
    permission_classes = [IsAuthenticated]

    def get_organization(self):
        # Scoping to the caller's own memberships means a non-member
        # requesting any organization_id gets a plain 404 — it never
        # confirms whether the organization even exists.
        return get_object_or_404(
            Organization.objects.filter(memberships__user=self.request.user).distinct(),
            pk=self.kwargs["organization_id"],
        )

    def get_queryset(self):
        organization = self.get_organization()
        return (
            Document.objects.filter(organization=organization)
            .select_related("uploaded_by")
            .order_by("-created_at")
        )

    def get_serializer_class(self):
        if self.request.method == "POST":
            return DocumentCreateSerializer
        return DocumentListSerializer

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return APIResponse.success(data=serializer.data, message="Documents retrieved successfully.")

    def create(self, request, *args, **kwargs):
        organization = self.get_organization()
        membership = _get_membership(request.user, organization)
        if membership.role != MembershipRole.ADMIN:
            return _forbidden("Only an organization admin can upload documents.")

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        uploaded_file = serializer.validated_data["file"]

        # No processing pipeline exists yet — the document is simply
        # persisted as PENDING; nothing here extracts, chunks, embeds,
        # or calls an LLM.
        document = serializer.save(
            organization=organization,
            uploaded_by=request.user,
            file_size=uploaded_file.size,
            status=DocumentStatus.PENDING,
        )

        output = DocumentDetailSerializer(document)
        return APIResponse.success(
            data=output.data,
            message="Document uploaded successfully.",
            status_code=status.HTTP_201_CREATED,
        )


class DocumentDetailView(generics.RetrieveDestroyAPIView):
    """GET (any member) / DELETE (ADMIN only) for a single document."""
    permission_classes = [IsAuthenticated]
    serializer_class = DocumentDetailSerializer
    lookup_url_kwarg = "document_id"

    def get_organization(self):
        return get_object_or_404(
            Organization.objects.filter(memberships__user=self.request.user).distinct(),
            pk=self.kwargs["organization_id"],
        )

    def get_object(self):
        organization = self.get_organization()
        # Tenant ownership is enforced by scoping the queryset to this
        # organization — a document that exists but belongs to a
        # different organization 404s exactly like one that doesn't
        # exist at all; a document is never looked up by id alone.
        document = get_object_or_404(
            Document.objects.filter(organization=organization).select_related("uploaded_by"),
            pk=self.kwargs["document_id"],
        )
        self.organization = organization
        return document

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return APIResponse.success(data=serializer.data, message="Document retrieved successfully.")

    def delete(self, request, *args, **kwargs):
        instance = self.get_object()
        membership = _get_membership(request.user, self.organization)
        if membership.role != MembershipRole.ADMIN:
            return _forbidden("Only an organization admin can delete this document.")

        # DocumentChunk has on_delete=CASCADE to Document, so chunks
        # are removed by the database — no extra code needed here.
        instance.delete()
        # 204 intentionally carries no body, consistent with the rest
        # of the project's delete endpoints.
        return Response(status=status.HTTP_204_NO_CONTENT)