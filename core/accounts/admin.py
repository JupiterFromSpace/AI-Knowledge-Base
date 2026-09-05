from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from accounts.models.users import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """
    Admin for the custom, email-based User model.

    Subclasses Django's built-in UserAdmin rather than plain
    ModelAdmin so we keep its battle-tested password-change flow
    (the password is never shown or editable in plain text — only a
    "change password" link is exposed) instead of reimplementing it.
    Its username-based fieldsets/add_fieldsets are overridden below
    since this project has no username field.
    """
    model = User
    ordering = ["email"]
    list_display = ["email", "first_name", "last_name", "is_active", "is_staff", "created_at"]
    list_filter = ["is_active", "is_staff", "is_superuser"]
    search_fields = ["email", "first_name", "last_name"]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name")}),
        ("Permissions", {
            "fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions"),
        }),
        ("Important dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "password1", "password2", "is_staff", "is_active"),
        }),
    )
    readonly_fields = ["last_login", "created_at", "updated_at"]