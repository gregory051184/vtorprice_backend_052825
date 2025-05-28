from django.contrib import admin
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

User = get_user_model()


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        "id",
        "last_name",
        "first_name",
        "phone",
        "email",
        "role",
        "company",
        "status",
        "is_active",
        "date_joined",
        "phone",
    )
    search_fields = ("first_name", "last_name", "email", "phone")
    list_select_related = ("company",)
    list_filter = ("is_active", "status")
    autocomplete_fields = ("company",)
    ordering = ("last_name",)

    fieldsets = (
        (None, {"fields": ("phone", "password")}),
        (
            _("Personal info"),
            {
                "fields": (
                    "last_name",
                    "first_name",
                    "middle_name",
                    "email",
                    "birth_date",
                    "company",
                )
            },
        ),
        (
            _("Permissions"),
            {
                "fields": (
                    "role",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("phone", "password1", "password2"),
            },
        ),
    )
