from django.urls import path

from organizations.api.v1.views import (
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