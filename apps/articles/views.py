"""articles アプリのビュー定義。

公開コンテンツ（誰でも閲覧可）。
本文は ``markdown`` パッケージで HTML へ変換し、テンプレート側で
``safe`` フィルタで描画する。
"""

from __future__ import annotations

from typing import Any

import markdown as md
from django.db.models import QuerySet
from django.utils import timezone
from django.views.generic import DetailView, ListView

from .models import ArticleStatus, HelpArticle


class ArticleListView(ListView):
    """公開記事の単純な一覧（カテゴリなし）。"""

    model = HelpArticle
    template_name = "articles/list.html"
    context_object_name = "articles"
    paginate_by = 20

    def get_queryset(self) -> QuerySet[HelpArticle]:
        now = timezone.now()
        return HelpArticle.objects.filter(
            status=ArticleStatus.PUBLISHED,
            published_at__lte=now,
        ).order_by("-published_at")


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
        return ctx
