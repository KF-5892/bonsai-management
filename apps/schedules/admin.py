"""schedules アプリの Django Admin 登録。"""

from __future__ import annotations

from django.contrib import admin

from .models import CareSchedule, CareScheduleCompletion, MonthlyAdvice


@admin.register(CareSchedule)
class CareScheduleAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "bonsai",
        "user",
        "task_type",
        "repeat_type",
        "next_run_at",
        "is_active",
    )
    list_filter = ("task_type", "is_active", "repeat_type")
    search_fields = ("title", "bonsai__name", "user__email")
    autocomplete_fields = ("bonsai", "user")
    date_hierarchy = "next_run_at"
    ordering = ("next_run_at",)


@admin.register(MonthlyAdvice)
class MonthlyAdviceAdmin(admin.ModelAdmin):
    list_display = ("month", "title", "category", "is_published")
    list_filter = ("month", "category", "is_published")
    search_fields = ("title", "advice_text")
    ordering = ("month", "title")


@admin.register(CareScheduleCompletion)
class CareScheduleCompletionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "source_type",
        "source_ref",
        "bonsai",
        "year_month",
        "status",
        "completed_at",
    )
    list_filter = ("source_type", "status")
    search_fields = ("source_ref", "user__email", "bonsai__name")
    autocomplete_fields = ("user", "bonsai", "log")
    date_hierarchy = "year_month"
    ordering = ("-completed_at",)
