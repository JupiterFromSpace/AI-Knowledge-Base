from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

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


class InvitationAcceptView(APIView):
    """
    POST /api/v1/invitations/{token}/accept/

    Not a CRUD operation on a single resource type, so no generic
    view is used: there's no single serializer.save() call that
    captures "validate this token against this user, then write two
    related rows." A plain APIView keeps that multi-step validation
    explicit and linear instead of fighting generic-view assumptions
    that don't fit this shape. There is also no request body to
    validate (everything comes from the URL token and request.user),
    so no input serializer exists either; the small composite success
    payload (organization + membership) is built directly rather than
    inventing a serializer to wrap two unrelated dicts together.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, token):
        # Unlocked read first: fail fast on expiry/already-accepted/
        # wrong-email without taking a row lock, so a doomed request
        # never blocks a legitimate concurrent one.
        invitation = get_object_or_404(Invitation.objects.select_related("organization"), token=token)

        if invitation.expires_at < timezone.now():
            return APIResponse.error(
                errors={"detail": "This invitation has expired."},
                message="This invitation has expired.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if invitation.accepted_at is not None:
            return APIResponse.error(
                errors={"detail": "This invitation has already been accepted."},
                message="This invitation has already been accepted.",
                status_code=status.HTTP_409_CONFLICT,
            )

        # Consistent with the __iexact comparison already used when
        # creating invitations (InvitationCreateSerializer.validate_email).
        if invitation.email.strip().lower() != request.user.email.strip().lower():
            return APIResponse.error(
                errors={"detail": "This invitation was issued to a different email address."},
                message="You are not authorized to accept this invitation.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        with transaction.atomic():
            # Row-lock the invitation for the rest of this
            # transaction. If a second, concurrent request for the
            # same token is already past the checks above, it blocks
            # here until this transaction commits, then re-reads
            # accepted_at as already set and exits via the check
            # below instead of creating a second Membership.
            invitation = Invitation.objects.select_for_update().select_related("organization").get(pk=invitation.pk)

            if invitation.accepted_at is not None:
                return APIResponse.error(
                    errors={"detail": "This invitation has already been accepted."},
                    message="This invitation has already been accepted.",
                    status_code=status.HTTP_409_CONFLICT,
                )

            try:
                # A nested atomic() opens a savepoint: if this insert
                # violates the (user, organization) unique constraint,
                # only this savepoint rolls back — the outer
                # transaction (and the invitation lock) is unaffected.
                with transaction.atomic():
                    membership = Membership.objects.create(
                        user=request.user,
                        organization=invitation.organization,
                        role=MembershipRole.MEMBER,
                    )
            except IntegrityError:
                # The user is already a member of this organization —
                # via this same invitation race, a different
                # invitation, or having joined some other way. Rather
                # than reject the request (or silently overwrite their
                # existing role), reuse their current Membership
                # unchanged and still close out the invitation: this
                # keeps acceptance idempotent and never downgrades an
                # existing ADMIN to MEMBER just because they accepted
                # a stray invite.
                membership = Membership.objects.get(user=request.user, organization=invitation.organization)

            invitation.accepted_at = timezone.now()
            invitation.save(update_fields=["accepted_at"])

        return APIResponse.success(
            data={
                "organization": {
                    "id": str(invitation.organization.id),
                    "name": invitation.organization.name,
                },
                "membership": {
                    "id": str(membership.id),
                    "role": membership.role,
                },
            },
            message="Invitation accepted successfully.",
        )