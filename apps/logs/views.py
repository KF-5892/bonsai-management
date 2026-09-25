"""logs アプリのビュー定義。

- 作業ログ一覧（自分のログのみ。``?q=`` 検索と 盆栽 / 作業種別 / 期間 の絞り込み）
- 作業ログ CRUD、CSV エクスポート、ワンタップ記録（クイック記録）
- ToDo プリフィル（``?bonsai=&task_type=&source_type=&source_ref=&year_month=YYYY-MM``）
  に対応し、保存時に ``mark_todo_done`` を呼んで完了状態を記録する
"""

from __future__ import annotations

import csv
from datetime import date, datetime, time, timedelta
from typing import Any
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.html import format_html
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    FormView,
    ListView,
    UpdateView,
)

from apps.bonsai.models import BonsaiPlant, TaskType
from apps.schedules.services.todos import mark_todo_done

from .forms import BulkCareLogForm, CareLogForm, FertilizerMasterForm
from .models import CareLog, Fertilizer


def _read_log_filters(request: HttpRequest) -> dict[str, str]:
    """作業ログ一覧の絞り込み条件（検索語 / 盆栽 / 作業種別 / 期間）を読む。"""
    return {
        "q": request.GET.get("q", "").strip(),
        "bonsai": request.GET.get("bonsai", ""),
        "task_type": request.GET.get("task_type", ""),
        "from": request.GET.get("from", ""),
        "to": request.GET.get("to", ""),
    }


def _filtered_logs(user: Any, filters: dict[str, str]) -> QuerySet[CareLog]:
    """絞り込み条件を適用したログの QuerySet（一覧と CSV で共用）。"""
    qs = (
        CareLog.objects.filter(user=user)
        .select_related("bonsai", "fertilizer")
        .order_by("-performed_at")
    )
    if filters["q"]:
        qs = qs.filter(Q(notes__icontains=filters["q"]) | Q(bonsai__name__icontains=filters["q"]))
    if filters["bonsai"]:
        qs = qs.filter(bonsai_id=filters["bonsai"])
    if filters["task_type"] in TaskType.values:
        qs = qs.filter(task_type=filters["task_type"])
    date_from = parse_date(filters["from"]) if filters["from"] else None
    date_to = parse_date(filters["to"]) if filters["to"] else None
    if date_from:
        qs = qs.filter(performed_at__gte=_start_of_day(date_from))
    if date_to:
        qs = qs.filter(performed_at__lt=_start_of_day(date_to + timedelta(days=1)))
    return qs


def _start_of_day(value: date) -> datetime:
    """その日の 0 時をカレントタイムゾーンの aware な日時にして返す。"""
    return timezone.make_aware(datetime.combine(value, time.min))


def _filter_query(filters: dict[str, str]) -> str:
    """現在の絞り込みを URL クエリ文字列（先頭の & 付き）に変換する。"""
    parts = [f"{key}={quote(value)}" for key, value in filters.items() if value]
    return ("&" + "&".join(parts)) if parts else ""


class CareLogListView(LoginRequiredMixin, ListView):
    """作業ログ一覧。検索語に加え、盆栽 / 作業種別 / 期間で絞り込める。"""

    model = CareLog
    template_name = "logs/list.html"
    context_object_name = "logs"
    paginate_by = 30

    def get_queryset(self) -> QuerySet[CareLog]:
        return _filtered_logs(self.request.user, _read_log_filters(self.request))

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        filters = _read_log_filters(self.request)
        ctx["filters"] = filters
        ctx["q"] = filters["q"]
        ctx["filter_query"] = _filter_query(filters)
        ctx["is_filtered"] = any(filters.values())
        ctx["plants"] = BonsaiPlant.objects.filter(user=self.request.user)
        ctx["task_types"] = TaskType.choices
        ctx["selected_plant"] = (
            ctx["plants"].filter(pk=filters["bonsai"]).first() if filters["bonsai"] else None
        )
        return ctx


class CareLogExportView(LoginRequiredMixin, View):
    """作業ログを CSV でエクスポートする（絞り込み条件は一覧と共通）。

    事業者の帳票・記録保全や、他ツールへの持ち出しに使う。
    Excel で開けるよう UTF-8 BOM 付きで返す。
    """

    def get(self, request: HttpRequest) -> HttpResponse:
        filters = _read_log_filters(request)
        logs = _filtered_logs(request.user, filters)

        response = HttpResponse(content_type="text/csv; charset=utf-8")
        stamp = timezone.localdate().strftime("%Y%m%d")
        response["Content-Disposition"] = f'attachment; filename="care_logs_{stamp}.csv"'
        response.write("\ufeff")  # Excel 用 BOM

        writer = csv.writer(response)
        writer.writerow(
            [
                "実施日時",
                "盆栽",
                "作業種別",
                "天候",
                "気温(℃)",
                "肥料",
                "肥料の量",
                "状態評価",
                "メモ",
            ]
        )
        for log in logs.iterator():
            writer.writerow(
                [
                    timezone.localtime(log.performed_at).strftime("%Y-%m-%d %H:%M"),
                    log.bonsai.name,
                    log.get_task_type_display()
                    if log.task_type != TaskType.OTHER or not log.task_type_other
                    else log.task_type_other,
                    log.get_weather_display() if log.weather else "",
                    "" if log.temperature_c is None else str(log.temperature_c),
                    log.fertilizer.name if log.fertilizer else "",
                    log.fertilizer_amount,
                    log.get_health_evaluation_display() if log.health_evaluation else "",
                    log.notes,
                ]
            )
        return response


# 詳細画面のワンタップ記録で受け付ける作業種別（頻度が高く、付帯情報なしで成立するもの）
QUICK_LOG_TASK_TYPES: tuple[str, ...] = (
    TaskType.WATERING,
    TaskType.LEAF_MISTING,
    TaskType.OBSERVATION,
)


class QuickCareLogCreateView(LoginRequiredMixin, View):
    """潅水などの高頻度作業を、フォームを開かずに「今」の日時で 1 タップ記録する。

    POST: ``bonsai``（自分の盆栽 ID）と ``task_type``（``QUICK_LOG_TASK_TYPES``）。
    完了後は ``next``（同一オリジンの相対パスのみ）か盆栽詳細へ戻し、
    メッセージから詳細の追記（編集画面）へ進めるようにする。
    """

    def post(self, request: HttpRequest) -> HttpResponse:
        plant = get_object_or_404(BonsaiPlant, pk=request.POST.get("bonsai"), user=request.user)
        task_type = request.POST.get("task_type", "")
        if task_type not in QUICK_LOG_TASK_TYPES:
            return HttpResponseBadRequest("この作業種別はクイック記録に対応していません。")

        log = CareLog.objects.create(
            user=request.user,
            bonsai=plant,
            task_type=task_type,
            performed_at=timezone.now(),
        )
        edit_url = reverse("logs:edit", kwargs={"pk": log.pk})
        messages.success(
            request,
            format_html(
                '「{}」に{}を記録しました。<a href="{}" class="underline font-bold">詳細を追記</a>',
                plant.name,
                log.get_task_type_display(),
                edit_url,
            ),
        )
        next_url = request.POST.get("next", "")
        if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            next_url = reverse("bonsai:detail", kwargs={"pk": plant.pk})
        return redirect(next_url)


def _parse_year_month(value: str | None) -> date | None:
    """``YYYY-MM`` 形式の文字列を当月 1 日の ``date`` に変換する。"""
    if not value:
        return None
    try:
        year_str, month_str = value.split("-", 1)
        return date(int(year_str), int(month_str), 1)
    except (TypeError, ValueError):
        return None


class CareLogCreateView(LoginRequiredMixin, CreateView):
    model = CareLog
    form_class = CareLogForm
    template_name = "logs/form.html"

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_initial(self) -> dict[str, Any]:
        initial = super().get_initial()
        bonsai_id = self.request.GET.get("bonsai")
        task_type = self.request.GET.get("task_type")
        if bonsai_id:
            initial["bonsai"] = bonsai_id
        if task_type:
            initial["task_type"] = task_type
        return initial

    def form_valid(self, form: CareLogForm) -> HttpResponse:
        form.instance.user = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, "作業ログを記録しました。")
        # ToDo 由来のプリフィルなら mark_todo_done する
        source_type = self.request.GET.get("source_type") or self.request.POST.get("source_type")
        source_ref = self.request.GET.get("source_ref") or self.request.POST.get("source_ref")
        year_month = _parse_year_month(
            self.request.GET.get("year_month") or self.request.POST.get("year_month")
        )
        if source_type and source_ref and year_month:
            mark_todo_done(
                self.request.user,
                source_type,
                source_ref,
                year_month,
                log=self.object,
                bonsai=self.object.bonsai,
            )
        return response

    def get_success_url(self) -> str:
        return reverse_lazy("logs:detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx["source_type"] = self.request.GET.get("source_type", "")
        ctx["source_ref"] = self.request.GET.get("source_ref", "")
        ctx["year_month"] = self.request.GET.get("year_month", "")
        return ctx


class CareLogDetailView(LoginRequiredMixin, DetailView):
    model = CareLog
    template_name = "logs/detail.html"
    context_object_name = "log"

    def get_queryset(self) -> QuerySet[CareLog]:
        return CareLog.objects.filter(user=self.request.user).select_related("bonsai", "fertilizer")


class CareLogUpdateView(LoginRequiredMixin, UpdateView):
    model = CareLog
    form_class = CareLogForm
    template_name = "logs/form.html"

    def get_queryset(self) -> QuerySet[CareLog]:
        return CareLog.objects.filter(user=self.request.user)

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form: CareLogForm) -> HttpResponse:
        response = super().form_valid(form)
        messages.success(self.request, "作業ログを更新しました。")
        return response

    def get_success_url(self) -> str:
        return reverse_lazy("logs:detail", kwargs={"pk": self.object.pk})


class CareLogDeleteView(LoginRequiredMixin, DeleteView):
    model = CareLog
    template_name = "logs/confirm_delete.html"
    success_url = reverse_lazy("logs:list")

    def get_queryset(self) -> QuerySet[CareLog]:
        return CareLog.objects.filter(user=self.request.user)

    def form_valid(self, form: Any) -> HttpResponse:
        response = super().form_valid(form)
        messages.success(self.request, "作業ログを削除しました。")
        return response


# ---------------------------------------------------------------------------
# 一括ログ記録（多鉢運用）
# ---------------------------------------------------------------------------
class BulkCareLogCreateView(LoginRequiredMixin, FormView):
    """複数の盆栽 × 同一作業をまとめて記録する（docs/サイトマップ.md §11-3）。"""

    template_name = "logs/bulk_form.html"
    form_class = BulkCareLogForm
    success_url = reverse_lazy("logs:list")

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_initial(self) -> dict[str, Any]:
        """盆栽一覧などから ``?bonsai=`` を複数渡された場合に初期選択する。"""
        initial = super().get_initial()
        bonsai_ids = self.request.GET.getlist("bonsai")
        if bonsai_ids:
            initial["bonsai"] = bonsai_ids
        task_type = self.request.GET.get("task_type")
        if task_type:
            initial["task_type"] = task_type
        return initial

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        form = ctx["form"]
        # 対象の盆栽はテンプレート側で品種ごとにまとめて描画する（すべて選択 / 品種単位の選択用）
        plants = list(
            BonsaiPlant.objects.filter(user=self.request.user)
            .select_related("species")
            .prefetch_related("tags")
            .order_by("species__name", "name")
        )
        raw_selected = (
            form.data.getlist("bonsai") if form.is_bound else (form.initial.get("bonsai") or [])
        )
        selected_ids = {str(value) for value in raw_selected}
        groups: dict[str, list[BonsaiPlant]] = {}
        for plant in plants:
            key = plant.species.name if plant.species else "品種未設定"
            groups.setdefault(key, []).append(plant)
        ctx["plant_groups"] = list(groups.items())
        ctx["selected_ids"] = selected_ids
        ctx["plant_count"] = len(plants)
        return ctx

    def form_valid(self, form: BulkCareLogForm) -> HttpResponse:
        logs = form.create_logs(self.request.user)
        messages.success(self.request, f"{len(logs)} 件の作業ログを記録しました。")
        return super().form_valid(form)


# ---------------------------------------------------------------------------
# 肥料マスタ CRUD（ライブラリ配下）
# ---------------------------------------------------------------------------
class FertilizerListView(LoginRequiredMixin, ListView):
    """肥料マスタ一覧（共通マスタ + 自分の登録）。"""

    model = Fertilizer
    template_name = "logs/fertilizer_list.html"
    context_object_name = "fertilizers"

    def get_queryset(self) -> QuerySet[Fertilizer]:
        return Fertilizer.objects.visible_to(self.request.user).order_by("user_id", "name")


class FertilizerCreateView(LoginRequiredMixin, CreateView):
    model = Fertilizer
    form_class = FertilizerMasterForm
    template_name = "logs/fertilizer_form.html"
    success_url = reverse_lazy("logs:fertilizer_list")

    def form_valid(self, form: FertilizerMasterForm) -> HttpResponse:
        form.instance.user = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, f"肥料「{self.object.name}」を登録しました。")
        return response


class FertilizerUpdateView(LoginRequiredMixin, UpdateView):
    model = Fertilizer
    form_class = FertilizerMasterForm
    template_name = "logs/fertilizer_form.html"
    success_url = reverse_lazy("logs:fertilizer_list")

    def get_queryset(self) -> QuerySet[Fertilizer]:
        # 共通マスタは編集させない（Admin 管理）
        return Fertilizer.objects.personal(self.request.user)

    def form_valid(self, form: FertilizerMasterForm) -> HttpResponse:
        response = super().form_valid(form)
        messages.success(self.request, f"肥料「{self.object.name}」を更新しました。")
        return response


class FertilizerDeleteView(LoginRequiredMixin, DeleteView):
    model = Fertilizer
    template_name = "logs/fertilizer_confirm_delete.html"
    success_url = reverse_lazy("logs:fertilizer_list")
    context_object_name = "fertilizer"

    def get_queryset(self) -> QuerySet[Fertilizer]:
        return Fertilizer.objects.personal(self.request.user)

    def form_valid(self, form: Any) -> HttpResponse:
        name = self.object.name if self.object else ""
        response = super().form_valid(form)
        messages.success(self.request, f"肥料「{name}」を削除しました。")
        return response
