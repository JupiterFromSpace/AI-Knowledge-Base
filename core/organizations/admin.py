from django.contrib import admin

from organizations.models import Invitation, Membership, Organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ["name", "created_at", "updated_at"]
    search_fields = ["name"]
    ordering = ["name"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    """
    The user/organization/role relationship is the whole point of this
    model, so it's the whole list_display — nothing else on Membership
    is worth surfacing separately.
    """
    list_display = ["user", "organization", "role", "created_at"]
    list_filter = ["role", "organization"]
    search_fields = ["user__email", "organization__name"]
    autocomplete_fields = ["user", "organization"]
    list_select_related = ["user", "organization"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ["email", "organization", "invited_by", "accepted_at", "expires_at", "created_at"]
    list_filter = ["organization"]
    search_fields = ["email", "organization__name"]
    autocomplete_fields = ["organization", "invited_by"]
    list_select_related = ["organization", "invited_by"]
    ordering = ["-created_at"]
    # The token is a bearer credential for accepting the invite, so it's
    # kept out of list_display (no casual browsing) but left visible,
    # read-only, on the detail page — an admin may need it to manually
    # resend or verify an invite link without being able to edit it.
    readonly_fields = ["token", "created_at"]