"""bonsai アプリのビュー定義。

ホーム + 盆栽 CRUD + 品種詳細を提供する。
ホームは ``compose_monthly_todos`` を呼び、当月の ToDo と
ユーザーが所有する盆栽の一覧を組み合わせて描画する。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    TemplateView,
    UpdateView,
)

from apps.schedules.services.todos import compose_monthly_todos

from .forms import BonsaiPlantForm
from .models import BonsaiPlant, BonsaiSpecies


class HomeView(LoginRequiredMixin, TemplateView):
    """ホーム画面。

    - 「今月のやること」: ``compose_monthly_todos`` の結果
    - 「マイ盆栽」: ``BonsaiPlant.objects.filter(user=request.user)``
    """

    template_name = "home.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        today = timezone.localdate()
        year_month = date(today.year, today.month, 1)
        todos = compose_monthly_todos(self.request.user, year_month)
        ctx["todos"] = todos
        ctx["year_month"] = year_month
        ctx["plants"] = BonsaiPlant.objects.filter(user=self.request.user).select_related(
            "species", "cover_media"
        )
        return ctx


# ---------------------------------------------------------------------------
# Bonsai CRUD
# ---------------------------------------------------------------------------
class BonsaiPlantCreateView(LoginRequiredMixin, CreateView):
    model = BonsaiPlant
    form_class = BonsaiPlantForm
    template_name = "bonsai/form.html"

    def form_valid(self, form: BonsaiPlantForm) -> HttpResponse:
        form.instance.user = self.request.user
        return super().form_valid(form)

    def get_success_url(self) -> str:
        return reverse_lazy("bonsai:detail", kwargs={"pk": self.object.pk})


class BonsaiPlantDetailView(LoginRequiredMixin, DetailView):
    model = BonsaiPlant
    template_name = "bonsai/detail.html"
    context_object_name = "plant"

    def get_queryset(self) -> QuerySet[BonsaiPlant]:
        return BonsaiPlant.objects.filter(user=self.request.user).select_related(
            "species", "cover_media"
        )

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        plant: BonsaiPlant = ctx["plant"]
        ctx["tab"] = self.request.GET.get("tab", "overview")
        ctx["recent_logs"] = plant.logs.select_related("fertilizer").all()[:10]
        ctx["schedules"] = plant.schedules.filter(is_active=True)
        ctx["media"] = plant.media.all()[:12]
        return ctx


class BonsaiPlantUpdateView(LoginRequiredMixin, UpdateView):
    model = BonsaiPlant
    form_class = BonsaiPlantForm
    template_name = "bonsai/form.html"

    def get_queryset(self) -> QuerySet[BonsaiPlant]:
        return BonsaiPlant.objects.filter(user=self.request.user)

    def get_success_url(self) -> str:
        return reverse_lazy("bonsai:detail", kwargs={"pk": self.object.pk})


class BonsaiPlantDeleteView(LoginRequiredMixin, DeleteView):
    model = BonsaiPlant
    template_name = "bonsai/confirm_delete.html"
    success_url = reverse_lazy("bonsai:home")

    def get_queryset(self) -> QuerySet[BonsaiPlant]:
        return BonsaiPlant.objects.filter(user=self.request.user)


# ---------------------------------------------------------------------------
# Species detail (誰でも閲覧可)
# ---------------------------------------------------------------------------
class BonsaiSpeciesDetailView(DetailView):
    model = BonsaiSpecies
    template_name = "bonsai/species_detail.html"
    context_object_name = "species"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        species: BonsaiSpecies = ctx["species"]
        # 月別タスクを月ごとに整理
        tasks_by_month: dict[int, list[dict[str, Any]]] = {}
        for task in species.monthly_tasks or []:
            if not isinstance(task, dict):
                continue
            try:
                m = int(task.get("month"))
            except (TypeError, ValueError):
                continue
            tasks_by_month.setdefault(m, []).append(task)
        ctx["tasks_by_month"] = sorted(tasks_by_month.items())
        # 関連記事
        from apps.articles.models import ArticleStatus, HelpArticle

        ctx["related_articles"] = HelpArticle.objects.filter(
            related_species=species,
            status=ArticleStatus.PUBLISHED,
        ).distinct()[:10]
        return ctx


def healthcheck(request: HttpRequest) -> HttpResponse:
    """簡易ヘルスチェック（テスト・LB 等用、ログイン不要）。"""
    del request
    return HttpResponse("ok", content_type="text/plain")
