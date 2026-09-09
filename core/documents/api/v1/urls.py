from django.urls import path

from documents.api.v1.views import DocumentDetailView, DocumentListCreateView

app_name = "documents"

urlpatterns = [
    path("", DocumentListCreateView.as_view(), name="list-create"),
    path("<uuid:document_id>/", DocumentDetailView.as_view(), name="detail"),
]