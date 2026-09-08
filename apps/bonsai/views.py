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
from django.db.models import Count, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
)

from apps.logs.models import CareLog
from apps.schedules.services.todos import (
    compose_monthly_todos,
    compose_todos_for_range,
    current_week_range,
)

from .forms import BonsaiMediaForm, BonsaiPlantForm, TagForm
from .models import (
    BonsaiMedia,
    BonsaiPlant,
    BonsaiSpecies,
    HealthStatus,
    SpeciesCategory,
    Tag,
    TaskType,
)

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

# 盆栽詳細のタブ構成（docs/サイトマップ.md §1「盆栽 詳細」）
DETAIL_TABS: list[tuple[str, str]] = [
    ("overview", "概要"),
    ("logs", "作業履歴"),
    ("schedules", "スケジュール"),
    ("media", "メディア"),
    ("repotting", "植え替え履歴"),
    ("compare", "成長比較"),
]
DETAIL_TAB_KEYS = {key for key, _label in DETAIL_TABS}

# 植え替えの目安年数（品種カテゴリ別）。品種未設定は広葉樹相当として扱う。
REPOTTING_INTERVAL_YEARS: dict[str, int] = {
    SpeciesCategory.CONIFER.value: 3,
    SpeciesCategory.BROADLEAF.value: 2,
    SpeciesCategory.FLOWERING.value: 2,
    SpeciesCategory.FRUITING.value: 2,
    SpeciesCategory.OTHER.value: 2,
}
DEFAULT_REPOTTING_INTERVAL_YEARS = 2

# マイ盆栽一覧の表示切替（docs/サイトマップ.md §11-4）
VIEW_MODES: list[tuple[str, str]] = [
    ("card", "カード"),
    ("species", "品種別"),
    ("tag", "タグ別"),
]


def estimate_next_repotting(plant: BonsaiPlant, last_repot: Any) -> date | None:
    """次回植え替えの目安日を返す（履歴が無ければ ``None``）。

    品種カテゴリ別の目安年数を最終植え替え日に加算する簡易ルール。
    ``date.replace`` は 2/29 で失敗するため、その場合は 2/28 に丸める。
    """
    if last_repot is None:
        return None
    category = plant.species.category if plant.species else ""
    years = REPOTTING_INTERVAL_YEARS.get(category, DEFAULT_REPOTTING_INTERVAL_YEARS)
    base = timezone.localtime(last_repot.performed_at).date()
    try:
        return base.replace(year=base.year + years)
    except ValueError:  # 2/29
        return base.replace(year=base.year + years, day=28)


def group_plants(plants: list[BonsaiPlant], view_mode: str) -> list[tuple[str, list[BonsaiPlant]]]:
    """マイ盆栽の表示切替（カード / 品種別 / タグ別）に応じてグルーピングする。

    ``card`` は単一グループ、``species`` は品種名、``tag`` はタグ名で束ねる
    （タグ別では複数タグを持つ盆栽は各グループに現れる）。
    """
    if view_mode == "species":
        groups: dict[str, list[BonsaiPlant]] = {}
        for plant in plants:
            key = plant.species.name if plant.species else "品種未設定"
            groups.setdefault(key, []).append(plant)
        return sorted(groups.items())
    if view_mode == "tag":
        groups = {}
        for plant in plants:
            tags = list(plant.tags.all())
            if not tags:
                groups.setdefault("タグなし", []).append(plant)
                continue
            for tag in tags:
                groups.setdefault(tag.name, []).append(plant)
        return sorted(groups.items())
    return [("", plants)]


class HomeView(LoginRequiredMixin, TemplateView):
    """ホーム画面。

    - 「やること」: ``compose_monthly_todos`` / ``compose_todos_for_range``
      の結果（``?range=month|week|custom`` で期間を切替）
    - 「最近の活動」: 直近の作業ログ（写真付きタイムライン）
    - 「マイ盆栽」: ``BonsaiPlant.objects.filter(user=request.user)``
      に名前検索（``?q=``）と健康状態絞り込み（``?status=``）を適用し、
      ``?view=card|species|tag`` で表示をグルーピングする
    """

    template_name = "home.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        today = timezone.localdate()
        year_month = date(today.year, today.month, 1)
        ctx["year_month"] = year_month

        ctx.update(self._todo_context(today, year_month))

        base_qs = (
            BonsaiPlant.objects.filter(user=self.request.user)
            .select_related("species", "cover_media")
            .prefetch_related("tags")
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
        for todo in ctx["monthly_todos"]:
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

        view_mode = self.request.GET.get("view", "card")
        if view_mode not in {"card", "species", "tag"}:
            view_mode = "card"
        ctx["view_mode"] = view_mode
        ctx["view_modes"] = VIEW_MODES
        ctx["plant_groups"] = group_plants(plants, view_mode)

        ctx["plants"] = plants
        ctx["q"] = q
        ctx["status_filter"] = status

        # 最近の活動（写真付きタイムライン）
        ctx["recent_activities"] = (
            CareLog.objects.filter(user=self.request.user)
            .select_related("bonsai")
            .order_by("-performed_at")[:5]
        )
        return ctx

    def _todo_context(self, today: date, year_month: date) -> dict[str, Any]:
        """期間切替（今月 / 今週 / カスタム）に応じた ToDo を組み立てる。"""
        range_mode = self.request.GET.get("range", "month")
        if range_mode not in {"month", "week", "custom"}:
            range_mode = "month"

        monthly_todos = compose_monthly_todos(self.request.user, year_month)
        range_start: date | None = None
        range_end: date | None = None

        if range_mode == "week":
            range_start, range_end = current_week_range(today)
        elif range_mode == "custom":
            range_start = parse_date(self.request.GET.get("from", "")) or today
            range_end = parse_date(self.request.GET.get("to", "")) or range_start

        if range_start is not None and range_end is not None:
            todos = compose_todos_for_range(self.request.user, range_start, range_end)
        else:
            todos = monthly_todos

        done = sum(
            1 for todo in todos if todo.completion and todo.completion.get("status") == "done"
        )
        return {
            "todos": todos,
            "monthly_todos": monthly_todos,
            "range_mode": range_mode,
            "range_start": range_start,
            "range_end": range_end,
            "todo_total": len(todos),
            "todo_done": done,
        }


# ---------------------------------------------------------------------------
# Bonsai CRUD
# ---------------------------------------------------------------------------
class BonsaiPlantCreateView(LoginRequiredMixin, CreateView):
    model = BonsaiPlant
    form_class = BonsaiPlantForm
    template_name = "bonsai/form.html"

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

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
        tab = self.request.GET.get("tab", "overview")
        if tab not in DETAIL_TAB_KEYS:
            tab = "overview"
        ctx["tab"] = tab
        ctx["tabs"] = DETAIL_TABS

        # 概要タブ: 当月 ToDo のうちこの個体に紐づくもの
        today = timezone.localdate()
        year_month = date(today.year, today.month, 1)
        ctx["year_month"] = year_month
        ctx["plant_todos"] = [
            todo
            for todo in compose_monthly_todos(self.request.user, year_month)
            if todo.bonsai_id == plant.id
        ]

        ctx["recent_logs"] = plant.logs.select_related("fertilizer").all()[:10]
        ctx["schedules"] = plant.schedules.filter(is_active=True)
        ctx["media"] = plant.media.all()[:12]
        ctx["media_count"] = plant.media.count()

        # 植え替え履歴タブ
        repot_logs = list(plant.logs.filter(task_type=TaskType.REPOTTING)[:20])
        ctx["repot_logs"] = repot_logs
        last_repot = repot_logs[0] if repot_logs else None
        ctx["last_repot"] = last_repot
        ctx["next_repot_estimate"] = estimate_next_repotting(plant, last_repot)

        # 成長比較タブ: 既定は「最古 × 最新」、?before=&after= で上書き
        ctx["compare_before"], ctx["compare_after"] = self._resolve_compare_pair(plant)
        ctx["compare_candidates"] = plant.media.all()[:60]
        return ctx

    def _resolve_compare_pair(
        self, plant: BonsaiPlant
    ) -> tuple[BonsaiMedia | None, BonsaiMedia | None]:
        """成長比較タブで並べる Before / After の 2 枚を決める。"""
        media_qs = plant.media.all()
        before_id = self.request.GET.get("before")
        after_id = self.request.GET.get("after")
        before = media_qs.filter(pk=before_id).first() if before_id else None
        after = media_qs.filter(pk=after_id).first() if after_id else None
        if before is None or after is None:
            ordered = list(media_qs.order_by("created_at"))
            if len(ordered) >= 2:
                before = before or ordered[0]
                after = after or ordered[-1]
        return before, after


class BonsaiPlantUpdateView(LoginRequiredMixin, UpdateView):
    model = BonsaiPlant
    form_class = BonsaiPlantForm
    template_name = "bonsai/form.html"

    def get_queryset(self) -> QuerySet[BonsaiPlant]:
        return BonsaiPlant.objects.filter(user=self.request.user)

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

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
        # ログイン中なら、この品種に該当する自分の盆栽を並べる
        if self.request.user.is_authenticated:
            ctx["my_plants"] = BonsaiPlant.objects.filter(
                user=self.request.user, species=species
            ).select_related("cover_media")
        return ctx


# ---------------------------------------------------------------------------
# メディア（年別ギャラリー / アップロード / カバー設定 / 削除）
# ---------------------------------------------------------------------------
class BonsaiMediaGalleryView(LoginRequiredMixin, DetailView):
    """盆栽 1 個体の写真を年 → 月でグルーピングして表示する（Stitch _12）。"""

    model = BonsaiPlant
    template_name = "bonsai/media_gallery.html"
    context_object_name = "plant"

    def get_queryset(self) -> QuerySet[BonsaiPlant]:
        return BonsaiPlant.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        plant: BonsaiPlant = ctx["plant"]
        media = list(plant.media.all())

        # 撮影日（未設定なら登録日）を基準に年・月でまとめる
        def sort_key(item: BonsaiMedia) -> date:
            return item.taken_at or timezone.localtime(item.created_at).date()

        years = sorted({sort_key(m).year for m in media}, reverse=True)
        selected = self.request.GET.get("year")
        selected_year = int(selected) if selected and selected.isdigit() else None
        if selected_year not in years:
            selected_year = years[0] if years else None

        by_month: dict[int, list[BonsaiMedia]] = {}
        for item in media:
            key = sort_key(item)
            if selected_year is not None and key.year != selected_year:
                continue
            by_month.setdefault(key.month, []).append(item)

        ctx["years"] = years
        ctx["selected_year"] = selected_year
        ctx["media_by_month"] = sorted(by_month.items(), reverse=True)
        ctx["total_count"] = len(media)
        return ctx


class BonsaiMediaCreateView(LoginRequiredMixin, CreateView):
    """写真アップロード。最初の 1 枚は自動的にカバー画像にする。"""

    model = BonsaiMedia
    form_class = BonsaiMediaForm
    template_name = "bonsai/media_form.html"

    def get_plant(self) -> BonsaiPlant:
        return get_object_or_404(BonsaiPlant, pk=self.kwargs["pk"], user=self.request.user)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx["plant"] = self.get_plant()
        return ctx

    def form_valid(self, form: BonsaiMediaForm) -> HttpResponse:
        plant = self.get_plant()
        form.instance.bonsai = plant
        response = super().form_valid(form)
        if plant.cover_media_id is None:
            plant.cover_media = self.object
            plant.save(update_fields=["cover_media", "updated_at"])
        messages.success(self.request, "写真をアップロードしました。")
        return response

    def get_success_url(self) -> str:
        return reverse_lazy("bonsai:media_gallery", kwargs={"pk": self.kwargs["pk"]})


class BonsaiMediaSetCoverView(LoginRequiredMixin, View):
    """指定した写真をカバー画像に設定する（POST のみ）。"""

    def post(self, request: HttpRequest, pk: str, media_pk: str) -> HttpResponse:
        plant = get_object_or_404(BonsaiPlant, pk=pk, user=request.user)
        media = get_object_or_404(BonsaiMedia, pk=media_pk, bonsai=plant)
        plant.cover_media = media
        plant.save(update_fields=["cover_media", "updated_at"])
        messages.success(request, "カバー画像を変更しました。")
        return redirect("bonsai:media_gallery", pk=plant.pk)


class BonsaiMediaDeleteView(LoginRequiredMixin, View):
    """写真を削除する（POST のみ）。カバーだった場合は別の写真へ付け替える。"""

    def post(self, request: HttpRequest, pk: str, media_pk: str) -> HttpResponse:
        plant = get_object_or_404(BonsaiPlant, pk=pk, user=request.user)
        media = get_object_or_404(BonsaiMedia, pk=media_pk, bonsai=plant)
        was_cover = plant.cover_media_id == media.pk
        media.delete()
        if was_cover:
            plant.cover_media = plant.media.first()
            plant.save(update_fields=["cover_media", "updated_at"])
        messages.success(request, "写真を削除しました。")
        return redirect("bonsai:media_gallery", pk=plant.pk)


# ---------------------------------------------------------------------------
# Tag CRUD（ライブラリ配下）
# ---------------------------------------------------------------------------
class TagListView(LoginRequiredMixin, ListView):
    """タグ管理一覧。各タグの利用件数も併せて表示する。"""

    model = Tag
    template_name = "bonsai/tag_list.html"
    context_object_name = "tags"

    def get_queryset(self) -> QuerySet[Tag]:
        return (
            Tag.objects.filter(user=self.request.user)
            .annotate(plant_count=Count("bonsai_plants"))
            .order_by("name")
        )


class TagCreateView(LoginRequiredMixin, CreateView):
    model = Tag
    form_class = TagForm
    template_name = "bonsai/tag_form.html"
    success_url = reverse_lazy("bonsai:tag_list")

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form: TagForm) -> HttpResponse:
        form.instance.user = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, f"タグ「{self.object.name}」を作成しました。")
        return response


class TagUpdateView(LoginRequiredMixin, UpdateView):
    model = Tag
    form_class = TagForm
    template_name = "bonsai/tag_form.html"
    success_url = reverse_lazy("bonsai:tag_list")

    def get_queryset(self) -> QuerySet[Tag]:
        return Tag.objects.filter(user=self.request.user)

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form: TagForm) -> HttpResponse:
        response = super().form_valid(form)
        messages.success(self.request, f"タグ「{self.object.name}」を更新しました。")
        return response


class TagDeleteView(LoginRequiredMixin, DeleteView):
    model = Tag
    template_name = "bonsai/tag_confirm_delete.html"
    success_url = reverse_lazy("bonsai:tag_list")
    context_object_name = "tag"

    def get_queryset(self) -> QuerySet[Tag]:
        return Tag.objects.filter(user=self.request.user)

    def form_valid(self, form: Any) -> HttpResponse:
        name = self.object.name if self.object else ""
        response = super().form_valid(form)
        messages.success(self.request, f"タグ「{name}」を削除しました。")
        return response


def healthcheck(request: HttpRequest) -> HttpResponse:
    """簡易ヘルスチェック（テスト・LB 等用、ログイン不要）。"""
    del request
    return HttpResponse("ok", content_type="text/plain")
