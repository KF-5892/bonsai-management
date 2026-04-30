"""articles アプリの Django Admin 登録。

運営者（is_staff=True かつ role=admin 想定）が
お役立ち記事と関連品種を編集するための画面。
"""

from __future__ import annotations

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import ArticleSpeciesRelation, HelpArticle


class ArticleSpeciesRelationInline(admin.TabularInline):
    """HelpArticle 編集画面に表示する関連品種インライン。"""

    model = ArticleSpeciesRelation
    extra = 1
    autocomplete_fields = ("species",)
    fields = ("species", "relevance")
    verbose_name = _("関連品種")
    verbose_name_plural = _("関連品種")


@admin.register(HelpArticle)
class HelpArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "author", "published_at")
    list_filter = ("status",)
    search_fields = ("title", "slug")
    prepopulated_fields = {"slug": ("title",)}
    autocomplete_fields = ("author",)
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "published_at"
    inlines = (ArticleSpeciesRelationInline,)
    fieldsets = (
        (None, {"fields": ("title", "slug", "summary", "cover_image")}),
        (_("本文"), {"fields": ("body",)}),
        (_("公開"), {"fields": ("status", "published_at", "author")}),
        (_("日時"), {"fields": ("created_at", "updated_at")}),
    )


@admin.register(ArticleSpeciesRelation)
class ArticleSpeciesRelationAdmin(admin.ModelAdmin):
    list_display = ("article", "species", "relevance", "created_at")
    list_filter = ("relevance",)
    search_fields = ("article__title", "article__slug")
    autocomplete_fields = ("article", "species")
    readonly_fields = ("created_at",)
