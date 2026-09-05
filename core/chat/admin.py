from django.contrib import admin

from chat.models import Conversation, Message


class MessageInline(admin.TabularInline):
    """Lets an admin read a conversation's messages in place, in order,
    instead of jumping to the separate Message list and filtering."""
    model = Message
    extra = 0
    fields = ["role", "content", "created_at"]
    readonly_fields = ["role", "content", "created_at"]
    can_delete = False
    ordering = ["created_at"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ["title", "user", "organization", "created_at", "updated_at"]
    list_filter = ["organization"]
    search_fields = ["title", "user__email", "organization__name"]
    autocomplete_fields = ["user", "organization"]
    list_select_related = ["user", "organization"]
    ordering = ["-updated_at"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [MessageInline]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ["conversation", "role", "created_at"]
    list_filter = ["role"]
    search_fields = ["conversation__title", "conversation__user__email"]
    autocomplete_fields = ["conversation"]
    list_select_related = ["conversation"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at"]