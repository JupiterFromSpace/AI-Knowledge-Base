from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.utils.responses import APIResponse
from organizations.api.v1.serializers import (
    InvitationCreateSerializer,
    InvitationSerializer,
    MembershipSerializer,
    OrganizationCreateSerializer,
    OrganizationSerializer,
    OrganizationUpdateSerializer,
)
from organizations.models import Invitation, Membership, MembershipRole, Organization

# No invitation-expiry policy exists elsewhere in the project yet;
# 7 days is a reasonable, common default for an invite link.
INVITATION_EXPIRY = timedelta(days=7)


def _get_membership(user, organization):
    """
    The caller's Membership for this *specific* organization, or None.
    Role is always evaluated per-organization this way — being ADMIN
    in one organization must never be assumed to mean ADMIN in
    another.
    """
    return Membership.objects.filter(user=user, organization=organization).first()


def _forbidden(detail):
    return APIResponse.error(
        errors={"detail": detail},
        message="You do not have permission to perform this action.",
        status_code=status.HTTP_403_FORBIDDEN,
    )


class OrganizationListCreateView(generics.ListCreateAPIView):
    """GET (list caller's organizations) / POST (create an organization)."""
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # One JOIN gets both "which orgs" and "my role in each" at
        # once — the filter already restricts each org to the
        # caller's own membership row, so the annotation is unambiguous.
        return (
            Organization.objects.filter(memberships__user=self.request.user)
            .annotate(role=F("memberships__role"))
            .order_by("name")
        )

    def get_serializer_class(self):
        if self.request.method == "POST":
            return OrganizationCreateSerializer
        return OrganizationSerializer

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return APIResponse.success(data=serializer.data, message="Organizations retrieved successfully.")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Organization + the creator's ADMIN membership are one
        # business operation: either both persist or neither does.
        with transaction.atomic():
            organization = serializer.save()
            Membership.objects.create(user=request.user, organization=organization, role=MembershipRole.ADMIN)

        organization.role = MembershipRole.ADMIN
        output = OrganizationSerializer(organization)
        return APIResponse.success(
            data=output.data,
            message="Organization created successfully.",
            status_code=status.HTTP_201_CREATED,
        )


class OrganizationDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET / PATCH / DELETE for a single organization."""
    permission_classes = [IsAuthenticated]
    lookup_url_kwarg = "organization_id"

    def get_queryset(self):
        # Scoping the queryset to the caller's own memberships means a
        # non-member requesting any organization_id gets a plain 404 —
        # it never confirms whether the organization even exists.
        return Organization.objects.filter(memberships__user=self.request.user).distinct()

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return OrganizationUpdateSerializer
        return OrganizationSerializer

    def get_object(self):
        organization = super().get_object()
        membership = _get_membership(self.request.user, organization)
        organization.role = membership.role
        self.membership = membership
        return organization

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = OrganizationSerializer(instance)
        return APIResponse.success(data=serializer.data, message="Organization retrieved successfully.")

    def patch(self, request, *args, **kwargs):
        instance = self.get_object()
        if self.membership.role != MembershipRole.ADMIN:
            return _forbidden("Only an organization admin can update this organization.")

        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        instance.role = self.membership.role
        output = OrganizationSerializer(instance)
        return APIResponse.success(data=output.data, message="Organization updated successfully.")

    def delete(self, request, *args, **kwargs):
        instance = self.get_object()
        if self.membership.role != MembershipRole.ADMIN:
            return _forbidden("Only an organization admin can delete this organization.")

        instance.delete()
        # 204 intentionally carries no body: this task explicitly asks
        # for no unnecessary data on a successful deletion.
        return Response(status=status.HTTP_204_NO_CONTENT)


class OrganizationMemberListView(generics.ListAPIView):
    """GET /api/v1/organizations/{id}/members/ — read-only member list."""
    permission_classes = [IsAuthenticated]
    serializer_class = MembershipSerializer

    def get_organization(self):
        return get_object_or_404(
            Organization.objects.filter(memberships__user=self.request.user).distinct(),
            pk=self.kwargs["organization_id"],
        )

    def get_queryset(self):
        organization = self.get_organization()
        return Membership.objects.filter(organization=organization).select_related("user").order_by("user__email")

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return APIResponse.success(data=serializer.data, message="Members retrieved successfully.")


class InvitationCreateView(generics.CreateAPIView):
    """POST /api/v1/organizations/{id}/invitations/ — ADMIN-only invitation creation."""
    permission_classes = [IsAuthenticated]
    serializer_class = InvitationCreateSerializer

    def get_organization(self):
        return get_object_or_404(
            Organization.objects.filter(memberships__user=self.request.user).distinct(),
            pk=self.kwargs["organization_id"],
        )

    def create(self, request, *args, **kwargs):
        organization = self.get_organization()
        membership = _get_membership(request.user, organization)
        if membership.role != MembershipRole.ADMIN:
            return _forbidden("Only an organization admin can create invitations.")

        serializer = self.get_serializer(data=request.data, context={"organization": organization})
        serializer.is_valid(raise_exception=True)
        invitation = serializer.save(
            organization=organization,
            invited_by=request.user,
            expires_at=timezone.now() + INVITATION_EXPIRY,
        )

        return APIResponse.success(
            data=InvitationSerializer(invitation).data,
            message="Invitation created successfully.",
            status_code=status.HTTP_201_CREATED,
        )