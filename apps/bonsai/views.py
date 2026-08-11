"""bonsai アプリのビュー定義。

ホーム + 盆栽 CRUD + 品種詳細を提供する。
ホームは ``compose_monthly_todos`` を呼び、当月の ToDo と
ユーザーが所有する盆栽の一覧を組み合わせて描画する。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from django.contrib import messages
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
from .models import BonsaiPlant, BonsaiSpecies, HealthStatus, TaskType

# 盆栽カードの「次の作業」行に出す Material Symbols アイコン（Stitch _2 準拠）
TASK_TYPE_ICONS: dict[str, str] = {
    TaskType.WATERING.value: "water_drop",
    TaskType.LEAF_MISTING.value: "water_drop",
    TaskType.FERTILIZING.value: "compost",
    TaskType.PRUNING.value: "content_cut",
    TaskType.BUD_PINCHING.value: "content_cut",
    TaskType.DEFOLIATION.value: "content_cut",
    TaskType.REPOTTING.value: "potted_plant",
    TaskType.PEST_CONTROL.value: "pest_control",
    TaskType.OBSERVATION.value: "visibility",
    TaskType.WIRING.value: "cable",
    TaskType.UNWIRING.value: "cable",
}
DEFAULT_TASK_ICON = "eco"


class HomeView(LoginRequiredMixin, TemplateView):
    """ホーム画面。

    - 「今月のやること」: ``compose_monthly_todos`` の結果
    - 「マイ盆栽」: ``BonsaiPlant.objects.filter(user=request.user)``
      に名前検索（``?q=``）と健康状態絞り込み（``?status=``）を適用
    """

    template_name = "home.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        today = timezone.localdate()
        year_month = date(today.year, today.month, 1)
        todos = compose_monthly_todos(self.request.user, year_month)
        ctx["todos"] = todos
        ctx["year_month"] = year_month

        base_qs = BonsaiPlant.objects.filter(user=self.request.user).select_related(
            "species", "cover_media"
        )
        # 空状態の判定は絞り込み前の所持数で行う（検索 0 件と未登録を区別する）
        ctx["has_plants"] = base_qs.exists()

        q = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "")
        if status not in HealthStatus.values:
            status = ""
        if q:
            base_qs = base_qs.filter(name__icontains=q)
        if status:
            base_qs = base_qs.filter(health_status=status)
        plants = list(base_qs)

        # 各盆栽の「次の作業」= 当月 ToDo のうち未完了で個体に紐付く先頭のもの
        next_tasks: dict[str, dict[str, str]] = {}
        for todo in todos:
            if not todo.bonsai_id or todo.bonsai_id in next_tasks:
                continue
            if todo.completion and todo.completion.get("status") == "done":
                continue
            try:
                label = str(TaskType(todo.task_type).label)
            except ValueError:
                label = todo.title
            if todo.period:
                label = f"{label}（{todo.period}）"
            next_tasks[todo.bonsai_id] = {
                "icon": TASK_TYPE_ICONS.get(todo.task_type, DEFAULT_TASK_ICON),
                "label": label,
            }
        for plant in plants:
            plant.next_task = next_tasks.get(plant.id)

        ctx["plants"] = plants
        ctx["q"] = q
        ctx["status_filter"] = status
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
        response = super().form_valid(form)
        messages.success(self.request, f"盆栽「{self.object.name}」を登録しました。")
        return response

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

    def form_valid(self, form: BonsaiPlantForm) -> HttpResponse:
        response = super().form_valid(form)
        messages.success(self.request, f"盆栽「{self.object.name}」を更新しました。")
        return response

    def get_success_url(self) -> str:
        return reverse_lazy("bonsai:detail", kwargs={"pk": self.object.pk})


class BonsaiPlantDeleteView(LoginRequiredMixin, DeleteView):
    model = BonsaiPlant
    template_name = "bonsai/confirm_delete.html"
    success_url = reverse_lazy("bonsai:home")

    def get_queryset(self) -> QuerySet[BonsaiPlant]:
        return BonsaiPlant.objects.filter(user=self.request.user)

    def form_valid(self, form: Any) -> HttpResponse:
        response = super().form_valid(form)
        messages.success(self.request, f"盆栽「{self.object.name}」を削除しました。")
        return response


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
