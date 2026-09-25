"""アプリ横断の共通ビュー。

グローバル検索（盆栽 / 作業ログ / お役立ち記事の横断検索）を提供する
（docs/サイトマップ.md §11-9）。
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.views.generic import TemplateView

from apps.articles.models import ArticleStatus, HelpArticle
from apps.bonsai.models import BonsaiPlant, BonsaiSpecies
from apps.logs.models import CareLog

RESULT_LIMIT = 20


class GlobalSearchView(LoginRequiredMixin, TemplateView):
    """盆栽・作業ログ・記事・品種を横断して検索する。"""

    template_name = "search.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        query = self.request.GET.get("q", "").strip()
        ctx["q"] = query
        if not query:
            ctx["has_query"] = False
            return ctx

        user = self.request.user
        plants = list(
            BonsaiPlant.objects.filter(user=user)
            .filter(Q(name__icontains=query) | Q(notes__icontains=query))
            .select_related("species")[:RESULT_LIMIT]
        )
        logs = list(
            CareLog.objects.filter(user=user)
            .filter(Q(notes__icontains=query) | Q(bonsai__name__icontains=query))
            .select_related("bonsai")
            .order_by("-performed_at")[:RESULT_LIMIT]
        )
        articles = list(
            HelpArticle.objects.filter(status=ArticleStatus.PUBLISHED).filter(
                Q(title__icontains=query) | Q(summary__icontains=query) | Q(body__icontains=query)
            )[:RESULT_LIMIT]
        )
        species = list(BonsaiSpecies.objects.filter(name__icontains=query)[:RESULT_LIMIT])

        ctx.update(
            {
                "has_query": True,
                "plants": plants,
                "logs": logs,
                "articles": articles,
                "species_list": species,
                "total_count": len(plants) + len(logs) + len(articles) + len(species),
            }
        )
        return ctx
