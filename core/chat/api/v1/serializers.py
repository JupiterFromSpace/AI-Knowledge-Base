from rest_framework import serializers

from chat.models import Conversation, Message


class ConversationCreateSerializer(serializers.ModelSerializer):
    """
    Input for POST .../conversations/. Only `title` is accepted —
    `user` comes from request.user and `organization` from the URL
    (both set explicitly by the view), so neither can be supplied by
    the client. `title` is optional because the model field is
    `blank=True`.
    """

    class Meta:
        model = Conversation
        fields = ["id", "title"]
        read_only_fields = ["id"]


class ConversationListSerializer(serializers.ModelSerializer):
    """
    Output for GET .../conversations/. `organization` is left out —
    every row in this list is already scoped to the one organization
    in the URL, so repeating it per-row adds nothing.
    """

    class Meta:
        model = Conversation
        fields = ["id", "title", "created_at", "updated_at"]
        read_only_fields = fields


class ConversationDetailSerializer(serializers.ModelSerializer):
    """Output for the create response and GET .../conversations/{id}/ —
    adds `organization` on top of the list fields, mirroring the same
    list/detail split used by the documents app."""

    class Meta:
        model = Conversation
        fields = ["id", "title", "organization", "created_at", "updated_at"]
        read_only_fields = fields


class MessageCreateSerializer(serializers.ModelSerializer):
    """
    Input for POST .../messages/. Only `content` is accepted — `role`
    is always forced to USER and `conversation` always comes from the
    URL, both set explicitly by the view. Neither field exists on this
    serializer, so nothing a client sends for them is ever read.
    """

    class Meta:
        model = Message
        fields = ["id", "content"]
        read_only_fields = ["id"]


class MessageSerializer(serializers.ModelSerializer):
    """Output for both message creation and GET .../messages/.
    `conversation` is left out for the same reason as `organization`
    above — every row here is already scoped to the one conversation
    in the URL."""

    class Meta:
        model = Message
        fields = ["id", "role", "content", "created_at"]
        read_only_fields = fields