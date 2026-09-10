from django.urls import path

from chat.api.v1.views import ConversationDetailView, ConversationListCreateView, MessageListCreateView

app_name = "chat"

urlpatterns = [
    path("", ConversationListCreateView.as_view(), name="list-create"),
    path("<uuid:conversation_id>/", ConversationDetailView.as_view(), name="detail"),
    path("<uuid:conversation_id>/messages/", MessageListCreateView.as_view(), name="messages"),
]