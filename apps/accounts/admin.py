from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("プロフィール"), {"fields": ("display_name", "role", "language", "time_zone")}),
        (
            _("通知設定"),
            {"fields": ("notification_enabled", "notify_start_time", "notify_end_time")},
        ),
        (
            _("権限"),
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        (_("日時"), {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2", "display_name", "role"),
            },
        ),
    )
    list_display = ("email", "display_name", "role", "is_staff", "is_active")
    list_filter = ("role", "is_staff", "is_active")
    search_fields = ("email", "display_name")
    ordering = ("email",)
    readonly_fields = ("created_at", "updated_at", "last_login")
