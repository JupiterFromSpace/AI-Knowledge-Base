from django.utils import timezone
from rest_framework import serializers

from accounts.models.users import User
from organizations.models import Invitation, Membership, Organization


class OrganizationCreateSerializer(serializers.ModelSerializer):
    """
    Input for POST /api/v1/organizations/. Only `name` is exposed —
    there is no `role` field here at all, so nothing a client sends
    for a role is ever read. The creator's ADMIN membership is
    created explicitly by the view, not by this serializer.
    """

    class Meta:
        model = Organization
        fields = ["id", "name"]
        read_only_fields = ["id"]


class OrganizationSerializer(serializers.ModelSerializer):
    """
    Output for list/create/retrieve/update. `role` is not a model
    field on Organization — it is attached to each instance by the
    view (via queryset annotation for list, or set by hand for
    create/retrieve/update) from the caller's own Membership row,
    never from client input.
    """
    role = serializers.CharField(read_only=True)

    class Meta:
        model = Organization
        fields = ["id", "name", "role", "created_at", "updated_at"]
        read_only_fields = fields


class OrganizationUpdateSerializer(serializers.ModelSerializer):
    """Input for PATCH /api/v1/organizations/{id}/ — `name` only. No
    id/membership/role/timestamp field is writable here."""

    class Meta:
        model = Organization
        fields = ["name"]


class MemberUserSerializer(serializers.ModelSerializer):
    """Minimal, safe user representation for member listings — no
    password and no other account details."""

    class Meta:
        model = User
        fields = ["id", "email"]
        read_only_fields = fields


class MembershipSerializer(serializers.ModelSerializer):
    user = MemberUserSerializer(read_only=True)

    class Meta:
        model = Membership
        fields = ["user", "role", "created_at"]
        read_only_fields = fields


class InvitationCreateSerializer(serializers.ModelSerializer):
    """
    Input for POST /api/v1/organizations/{id}/invitations/. Validates
    that the email doesn't already belong to a member of this
    organization and doesn't already have an active invitation
    pending. `organization`, `invited_by`, `token` (model default),
    and `expires_at` are all set by the view — never accepted from
    the client.
    """

    class Meta:
        model = Invitation
        fields = ["id", "email"]
        read_only_fields = ["id"]

    def validate_email(self, value):
        organization = self.context["organization"]

        if Membership.objects.filter(organization=organization, user__email__iexact=value).exists():
            raise serializers.ValidationError("This email already belongs to a member of the organization.")

        if Invitation.objects.filter(
            organization=organization,
            email__iexact=value,
            accepted_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).exists():
            raise serializers.ValidationError("An active invitation already exists for this email.")

        return value


class InvitationSerializer(serializers.ModelSerializer):
    """
    Representation returned after creating an invitation. The token
    is included deliberately, per this task's spec, so the invite
    flow can be exercised locally before real email delivery exists —
    it is not exposed anywhere else (e.g. member listings).
    """
    invited_by = serializers.EmailField(source="invited_by.email", read_only=True)

    class Meta:
        model = Invitation
        fields = ["id", "organization", "email", "invited_by", "token", "expires_at", "accepted_at", "created_at"]
        read_only_fields = fields