"""盆栽アプリの Django Admin 登録。"""

from __future__ import annotations

from django.contrib import admin

from .models import BonsaiMedia, BonsaiPlant, BonsaiSpecies, BonsaiTag, Tag


@admin.register(BonsaiSpecies)
class BonsaiSpeciesAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "category", "scientific_name", "updated_at")
    list_filter = ("category",)
    search_fields = ("name", "slug", "scientific_name")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("name",)


class BonsaiTagInline(admin.TabularInline):
    model = BonsaiTag
    extra = 0
    autocomplete_fields = ("tag",)


class BonsaiMediaInline(admin.TabularInline):
    model = BonsaiMedia
    extra = 0
    fields = ("image_original", "caption", "taken_at", "created_at")
    readonly_fields = ("created_at",)


@admin.register(BonsaiPlant)
class BonsaiPlantAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "species", "health_status", "acquired_at", "created_at")
    list_filter = ("health_status", "species__category")
    search_fields = ("name", "user__email", "species__name")
    autocomplete_fields = ("species", "cover_media")
    date_hierarchy = "created_at"
    inlines = [BonsaiTagInline, BonsaiMediaInline]


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "color", "created_at")
    search_fields = ("name", "user__email")
    list_filter = ("user",)


@admin.register(BonsaiMedia)
class BonsaiMediaAdmin(admin.ModelAdmin):
    list_display = ("bonsai", "caption", "taken_at", "created_at")
    search_fields = ("bonsai__name", "caption")
    autocomplete_fields = ("bonsai",)
    date_hierarchy = "created_at"
    readonly_fields = ("image_medium", "image_thumbnail", "created_at")
