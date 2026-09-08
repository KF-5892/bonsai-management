"""articles アプリのビュー定義。

公開コンテンツ（誰でも閲覧可）。
本文は ``markdown`` パッケージで HTML へ変換し、テンプレート側で
``safe`` フィルタで描画する。
"""

from __future__ import annotations

from typing import Any

import markdown as md
from django.db.models import Count, QuerySet
from django.utils import timezone
from django.views.generic import DetailView, ListView

from .models import ArticleCategory, ArticleStatus, HelpArticle


class ArticleListView(ListView):
    """お役立ちトップ（特集 + サブカテゴリ + 最新記事）。

    docs/サイトマップ.md §11-7 に従い、旧 _4 / _6 の 2 案を 1 画面へ統合し
    サブカテゴリ（作業TIPS / 品種ガイド / 病害虫対策 / ギャラリー）で絞り込む。
    """

    model = HelpArticle
    template_name = "articles/list.html"
    context_object_name = "articles"
    paginate_by = 20

    def get_category(self) -> str:
        category = self.request.GET.get("category", "")
        return category if category in ArticleCategory.values else ""

    def get_queryset(self) -> QuerySet[HelpArticle]:
        now = timezone.now()
        qs = HelpArticle.objects.filter(
            status=ArticleStatus.PUBLISHED,
            published_at__lte=now,
        ).order_by("-published_at")
        category = self.get_category()
        if category:
            qs = qs.filter(category=category)
        return qs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        now = timezone.now()
        published = HelpArticle.objects.filter(
            status=ArticleStatus.PUBLISHED,
            published_at__lte=now,
        )
        ctx["category"] = self.get_category()
        ctx["categories"] = ArticleCategory.choices
        ctx["category_counts"] = {
            row["category"]: row["count"]
            for row in published.values("category").annotate(count=Count("id"))
        }
        # 特集は絞り込みに関わらずトップに出す
        ctx["featured"] = published.filter(is_featured=True).order_by("-published_at")[:3]
        return ctx


class ArticleDetailView(DetailView):
    model = HelpArticle
    template_name = "articles/detail.html"
    context_object_name = "article"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_queryset(self) -> QuerySet[HelpArticle]:
        now = timezone.now()
        return HelpArticle.objects.filter(
            status=ArticleStatus.PUBLISHED,
            published_at__lte=now,
        )

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        article: HelpArticle = ctx["article"]
        ctx["body_html"] = md.markdown(
            article.body,
            extensions=["fenced_code", "tables"],
        )
        ctx["related_species"] = article.related_species.all()
        # 関連記事: 同カテゴリの新着（自分自身は除く）
        ctx["related_articles"] = (
            self.get_queryset().filter(category=article.category).exclude(pk=article.pk)[:5]
        )
        if self.request.user.is_authenticated:
            # 記事の関連品種に該当する自分の盆栽（docs/サイトマップ.md §1 _3）
            from apps.bonsai.models import BonsaiPlant

            ctx["my_related_plants"] = BonsaiPlant.objects.filter(
                user=self.request.user,
                species__in=article.related_species.all(),
            ).select_related("species")
        return ctx
