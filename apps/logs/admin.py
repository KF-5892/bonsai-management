"""作業ログアプリの Django Admin 登録。"""

from __future__ import annotations

from django.contrib import admin

from .models import CareLog, Fertilizer


@admin.register(Fertilizer)
class FertilizerAdmin(admin.ModelAdmin):
    list_display = ("name", "form_type", "n", "p", "k", "is_organic", "is_common", "user")
    list_filter = ("form_type", "is_organic")
    search_fields = ("name", "user__email")
    autocomplete_fields = ("user",)
    ordering = ("name",)

    @admin.display(boolean=True, description="共通マスタ")
    def is_common(self, obj: Fertilizer) -> bool:
        return obj.is_common


@admin.register(CareLog)
class CareLogAdmin(admin.ModelAdmin):
    list_display = ("bonsai", "task_type", "performed_at", "health_evaluation", "user")
    list_filter = ("task_type", "weather", "health_evaluation")
    search_fields = ("bonsai__name", "notes", "user__email")
    date_hierarchy = "performed_at"
    autocomplete_fields = ("bonsai", "fertilizer", "user")
