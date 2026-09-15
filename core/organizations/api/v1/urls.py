from django.urls import path

from organizations.api.v1.views import (
    InvitationAcceptView,
    InvitationCreateView,
    OrganizationDetailView,
    OrganizationListCreateView,
    OrganizationMemberListView,
)

app_name = "organizations"

urlpatterns = [
    path("", OrganizationListCreateView.as_view(), name="list-create"),
    path("<uuid:organization_id>/", OrganizationDetailView.as_view(), name="detail"),
    path("<uuid:organization_id>/members/", OrganizationMemberListView.as_view(), name="members"),
    path("<uuid:organization_id>/invitations/", InvitationCreateView.as_view(), name="invitations"),
]

# Mounted separately, at /api/v1/invitations/, in core/urls.py — this
# endpoint isn't scoped to one organization_id in its URL (the token
# itself identifies the organization), so it doesn't belong under the
# /organizations/{id}/ prefix above.
invitation_urlpatterns = [
    path("<str:token>/accept/", InvitationAcceptView.as_view(), name="accept"),
]