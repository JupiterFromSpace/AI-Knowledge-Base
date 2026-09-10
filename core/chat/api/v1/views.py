from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from chat.api.v1.serializers import (
    ConversationCreateSerializer,
    ConversationDetailSerializer,
    ConversationListSerializer,
    MessageCreateSerializer,
    MessageSerializer,
)
from chat.models import Conversation, Message, MessageRole
from core.utils.responses import APIResponse
from organizations.models import Organization


class ConversationListCreateView(generics.ListCreateAPIView):
    """GET (list the caller's own conversations) / POST (create a conversation).

    No role restriction here beyond membership — any member of the
    organization may create a conversation; there is no ADMIN-only
    rule for this endpoint, unlike document upload.
    """
    permission_classes = [IsAuthenticated]

    def get_organization(self):
        # Cached per-request: nothing else on this view calls it more
        # than once, but caching keeps that true even as the view
        # evolves, without having to re-audit call sites later.
        if not hasattr(self, "_organization"):
            # Scoping to the caller's own memberships means a
            # non-member requesting any organization_id gets a plain
            # 404 — it never confirms whether the organization exists.
            self._organization = get_object_or_404(
                Organization.objects.filter(memberships__user=self.request.user).distinct(),
                pk=self.kwargs["organization_id"],
            )
        return self._organization

    def get_queryset(self):
        organization = self.get_organization()
        # Both the tenant scope and the ownership scope are applied in
        # the database query itself, not filtered in Python.
        return (
            Conversation.objects.filter(organization=organization, user=self.request.user)
            .order_by("-updated_at")
        )

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ConversationCreateSerializer
        return ConversationListSerializer

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return APIResponse.success(data=serializer.data, message="Conversations retrieved successfully.")

    def create(self, request, *args, **kwargs):
        organization = self.get_organization()

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        conversation = serializer.save(user=request.user, organization=organization)

        output = ConversationDetailSerializer(conversation)
        return APIResponse.success(
            data=output.data,
            message="Conversation created successfully.",
            status_code=status.HTTP_201_CREATED,
        )


class ConversationDetailView(generics.RetrieveDestroyAPIView):
    """GET / DELETE for a single conversation. No update endpoint
    exists — this task doesn't ask for one."""
    permission_classes = [IsAuthenticated]
    serializer_class = ConversationDetailSerializer
    lookup_url_kwarg = "conversation_id"

    def get_organization(self):
        if not hasattr(self, "_organization"):
            self._organization = get_object_or_404(
                Organization.objects.filter(memberships__user=self.request.user).distinct(),
                pk=self.kwargs["organization_id"],
            )
        return self._organization

    def get_object(self):
        organization = self.get_organization()
        # Tenant scope AND ownership are enforced by one filtered
        # query: a conversation that exists but belongs to a
        # different organization, or to a different user, 404s
        # exactly like one that doesn't exist — it is never looked up
        # by id alone.
        return get_object_or_404(
            Conversation.objects.filter(organization=organization, user=self.request.user),
            pk=self.kwargs["conversation_id"],
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return APIResponse.success(data=serializer.data, message="Conversation retrieved successfully.")

    def delete(self, request, *args, **kwargs):
        instance = self.get_object()
        # Message has on_delete=CASCADE to Conversation, so messages
        # are removed by the database — no extra code needed here.
        instance.delete()
        # 204 intentionally carries no body, consistent with the rest
        # of the project's delete endpoints.
        return Response(status=status.HTTP_204_NO_CONTENT)


class MessageListCreateView(generics.ListCreateAPIView):
    """
    GET (list a conversation's messages) / POST (create a USER
    message). Only saves the message at this stage — no LLM call, no
    retrieval, no assistant reply; those are a separate later task.
    """
    permission_classes = [IsAuthenticated]

    def get_organization(self):
        if not hasattr(self, "_organization"):
            self._organization = get_object_or_404(
                Organization.objects.filter(memberships__user=self.request.user).distinct(),
                pk=self.kwargs["organization_id"],
            )
        return self._organization

    def get_conversation(self):
        # Cached for the same reason as get_organization(): this
        # method is only called once per request today, but caching
        # guarantees that stays true — membership and ownership are
        # each checked with exactly one query, never per-message.
        if not hasattr(self, "_conversation"):
            organization = self.get_organization()
            self._conversation = get_object_or_404(
                Conversation.objects.filter(organization=organization, user=self.request.user),
                pk=self.kwargs["conversation_id"],
            )
        return self._conversation

    def get_queryset(self):
        conversation = self.get_conversation()
        # Message.Meta.ordering is already ["created_at"], but the
        # task calls out chronological order explicitly, so it's
        # stated here too rather than relied on implicitly.
        return Message.objects.filter(conversation=conversation).order_by("created_at")

    def get_serializer_class(self):
        if self.request.method == "POST":
            return MessageCreateSerializer
        return MessageSerializer

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return APIResponse.success(data=serializer.data, message="Messages retrieved successfully.")

    def create(self, request, *args, **kwargs):
        # get_conversation() already enforces: caller is a member of
        # the organization, the conversation belongs to that
        # organization, and the caller owns the conversation.
        conversation = self.get_conversation()

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = serializer.save(conversation=conversation, role=MessageRole.USER)

        output = MessageSerializer(message)
        return APIResponse.success(
            data=output.data,
            message="Message created successfully.",
            status_code=status.HTTP_201_CREATED,
        )