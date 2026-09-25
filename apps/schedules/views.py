"""schedules アプリのビュー定義。

- 月別スケジュール一覧（year, month クエリで切替、デフォルト: 当月）
  作業種別 / 盆栽 / 品種 / タグでの絞り込みに対応
- 年間スケジュール（12 か月の俯瞰）
- 月末レビュー（対象月の完了率と振り返り）
- 個別スケジュール CRUD
- ToDo 完了アクション（``mark_todo_done`` 経由）
"""

from __future__ import annotations

import csv
from datetime import date, datetime, time
from typing import Any
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View
from django.views.generic import CreateView, DeleteView, UpdateView

from apps.bonsai.models import BonsaiPlant, BonsaiSpecies, Tag, TaskType
from apps.logs.models import CareLog

from .forms import CareScheduleForm
from .models import CareSchedule
from .services.todos import (
    Todo,
    compose_monthly_todos,
    compose_todos_for_range,
    compose_yearly_summaries,
    summarize_monthly_todos,
)


def _resolve_year_month(request: HttpRequest) -> date:
    """``?year=YYYY&month=MM`` を読んで対象月の 1 日を返す。

    パース失敗時は当月の 1 日を返す。
    """
    today = timezone.localdate()
    try:
        year = int(request.GET.get("year", today.year))
        month = int(request.GET.get("month", today.month))
        return date(year, month, 1)
    except (TypeError, ValueError):
        return date(today.year, today.month, 1)


def _prev_month(year_month: date) -> date:
    """前月の 1 日を返す。"""
    if year_month.month == 1:
        return date(year_month.year - 1, 12, 1)
    return date(year_month.year, year_month.month - 1, 1)


def _next_month(year_month: date) -> date:
    """翌月の 1 日を返す。"""
    if year_month.month == 12:
        return date(year_month.year + 1, 1, 1)
    return date(year_month.year, year_month.month + 1, 1)


def _start_of_day(value: date) -> datetime:
    """その日の 0 時をカレントタイムゾーンの aware な日時にして返す。"""
    return timezone.make_aware(datetime.combine(value, time.min))


def _resolve_review_month(request: HttpRequest) -> date:
    """月末レビューの対象月を返す（既定は先月）。"""
    raw_year = request.GET.get("year")
    raw_month = request.GET.get("month")
    if raw_year and raw_month and raw_year.isdigit() and raw_month.isdigit():
        month = min(max(int(raw_month), 1), 12)
        return date(int(raw_year), month, 1)
    today = timezone.localdate()
    return _prev_month(date(today.year, today.month, 1))


def _read_filters(request: HttpRequest) -> dict[str, str]:
    """月別スケジュールの絞り込み条件をクエリから読む。"""
    return {
        "task_type": request.GET.get("task_type", ""),
        "bonsai": request.GET.get("bonsai", ""),
        "species": request.GET.get("species", ""),
        "tag": request.GET.get("tag", ""),
    }


def _filter_query(filters: dict[str, str]) -> str:
    """現在の絞り込みを URL クエリ文字列（先頭の & 付き）に変換する。"""
    parts = [f"{key}={quote(value)}" for key, value in filters.items() if value]
    return ("&" + "&".join(parts)) if parts else ""


def filter_todos(user: Any, todos: list[Todo], filters: dict[str, str]) -> list[Todo]:
    """ToDo リストを作業種別 / 盆栽 / 品種 / タグで絞り込む。

    品種・タグは盆栽 ID の集合に展開してから ``bonsai_id`` で突き合わせる
    （ToDo は品種マスタ由来の仮想タスクを含み、DB クエリで絞れないため）。
    """
    task_type = filters.get("task_type")
    if task_type:
        todos = [t for t in todos if t.task_type == task_type]

    bonsai_id = filters.get("bonsai")
    if bonsai_id:
        todos = [t for t in todos if t.bonsai_id == bonsai_id]

    allowed_ids: set[str] | None = None
    species_id = filters.get("species")
    if species_id:
        allowed_ids = set(
            BonsaiPlant.objects.filter(user=user, species_id=species_id).values_list(
                "id", flat=True
            )
        )
    tag_id = filters.get("tag")
    if tag_id:
        tag_plant_ids = set(
            BonsaiPlant.objects.filter(user=user, tags__id=tag_id).values_list("id", flat=True)
        )
        allowed_ids = tag_plant_ids if allowed_ids is None else allowed_ids & tag_plant_ids

    if allowed_ids is not None:
        todos = [t for t in todos if t.bonsai_id in allowed_ids]
    return todos


class ScheduleListView(LoginRequiredMixin, View):
    """当月の ToDo 一覧（作業種別 / 盆栽 / 品種 / タグで絞り込み可）。"""

    template_name = "schedules/list.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        from django.shortcuts import render

        year_month = _resolve_year_month(request)
        todos = compose_monthly_todos(request.user, year_month)
        filters = _read_filters(request)
        todos = filter_todos(request.user, todos, filters)

        # 前月・次月のリンク
        if year_month.month == 1:
            prev_ym = date(year_month.year - 1, 12, 1)
        else:
            prev_ym = date(year_month.year, year_month.month - 1, 1)
        if year_month.month == 12:
            next_ym = date(year_month.year + 1, 1, 1)
        else:
            next_ym = date(year_month.year, year_month.month + 1, 1)
        return render(
            request,
            self.template_name,
            {
                "todos": todos,
                "year_month": year_month,
                "prev_ym": prev_ym,
                "next_ym": next_ym,
                "filters": filters,
                "filter_query": _filter_query(filters),
                "task_types": TaskType.choices,
                "plants": BonsaiPlant.objects.filter(user=request.user),
                "species_list": BonsaiSpecies.objects.filter(plants__user=request.user).distinct(),
                "tags": Tag.objects.filter(user=request.user),
            },
        )


class TodoExportView(LoginRequiredMixin, View):
    """ToDo を CSV でエクスポートする（家族・代理人への共有用）。

    ``?from=YYYY-MM-DD&to=YYYY-MM-DD`` があればその期間、無ければ
    ``?year=&month=``（既定は当月）の 1 か月分を出力する。
    Excel で開けるよう UTF-8 BOM 付きで返す（docs/サイトマップ.md §11-2）。
    """

    def get(self, request: HttpRequest) -> HttpResponse:
        start = parse_date(request.GET.get("from", "") or "")
        end = parse_date(request.GET.get("to", "") or "")
        if start and end:
            todos = compose_todos_for_range(request.user, start, end)
            label = f"{start:%Y%m%d}-{end:%Y%m%d}"
        else:
            year_month = _resolve_year_month(request)
            todos = compose_monthly_todos(request.user, year_month)
            label = f"{year_month:%Y%m}"

        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="todos_{label}.csv"'
        response.write("\ufeff")  # Excel 用 BOM

        writer = csv.writer(response)
        writer.writerow(["対象の盆栽", "品種", "時期", "やること", "説明", "状態"])
        for todo in todos:
            done = todo.completion and todo.completion.get("status") == "done"
            writer.writerow(
                [
                    todo.bonsai_name or "全体",
                    todo.species_name or "",
                    todo.period or "",
                    todo.title,
                    todo.description,
                    "完了" if done else "未完了",
                ]
            )
        return response


class YearlyScheduleView(LoginRequiredMixin, View):
    """年間スケジュール（12 か月の月カード縦リスト）。

    docs/サイトマップ.md §9-4 の選択肢 A（月カード縦リスト）を採用する。
    """

    template_name = "schedules/year.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        from django.shortcuts import render

        raw_year = request.GET.get("year")
        year = int(raw_year) if raw_year and raw_year.isdigit() else timezone.localdate().year
        summaries = compose_yearly_summaries(request.user, year)
        today = timezone.localdate()
        return render(
            request,
            self.template_name,
            {
                "year": year,
                "prev_year": year - 1,
                "next_year": year + 1,
                "summaries": summaries,
                "current_month": today.month if today.year == year else None,
                "task_type_labels": dict(TaskType.choices),
            },
        )


class MonthlyReviewView(LoginRequiredMixin, View):
    """月末レビュー（既定は先月）。完了率と作業実績の振り返りを表示する。"""

    template_name = "schedules/review.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        from django.shortcuts import render

        year_month = _resolve_review_month(request)
        summary = summarize_monthly_todos(request.user, year_month)

        month_end = _next_month(year_month)
        # performed_at は DateTimeField のため、当月の範囲を aware な日時に変換する
        start_dt = _start_of_day(year_month)
        end_dt = _start_of_day(month_end)
        logs = (
            CareLog.objects.filter(
                user=request.user,
                performed_at__gte=start_dt,
                performed_at__lt=end_dt,
            )
            .select_related("bonsai")
            .order_by("-performed_at")
        )

        # 未完了 ToDo（次月へ持ち越す候補）
        pending_todos = [
            todo
            for todo in summary.todos
            if not (todo.completion and todo.completion.get("status") == "done")
        ]

        return render(
            request,
            self.template_name,
            {
                "summary": summary,
                "year_month": year_month,
                "prev_ym": _prev_month(year_month),
                "next_ym": month_end,
                "pending_todos": pending_todos,
                "log_count": logs.count(),
                "logs": logs[:20],
                "task_type_labels": dict(TaskType.choices),
            },
        )


class CareScheduleCreateView(LoginRequiredMixin, CreateView):
    model = CareSchedule
    form_class = CareScheduleForm
    template_name = "schedules/form.html"
    success_url = reverse_lazy("schedules:list")

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_initial(self) -> dict[str, Any]:
        """盆栽詳細から ``?bonsai=`` 付きで来た場合に対象を初期選択する。"""
        initial = super().get_initial()
        bonsai_id = self.request.GET.get("bonsai")
        if bonsai_id:
            initial["bonsai"] = bonsai_id
        return initial

    def form_valid(self, form: CareScheduleForm) -> HttpResponse:
        form.instance.user = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, "スケジュールを作成しました。")
        return response


class CareScheduleUpdateView(LoginRequiredMixin, UpdateView):
    model = CareSchedule
    form_class = CareScheduleForm
    template_name = "schedules/form.html"
    success_url = reverse_lazy("schedules:list")

    def get_queryset(self) -> QuerySet[CareSchedule]:
        return CareSchedule.objects.filter(user=self.request.user)

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form: CareScheduleForm) -> HttpResponse:
        response = super().form_valid(form)
        messages.success(self.request, "スケジュールを更新しました。")
        return response


class CareScheduleDeleteView(LoginRequiredMixin, DeleteView):
    model = CareSchedule
    template_name = "schedules/confirm_delete.html"
    success_url = reverse_lazy("schedules:list")

    def get_queryset(self) -> QuerySet[CareSchedule]:
        return CareSchedule.objects.filter(user=self.request.user)

    def form_valid(self, form: Any) -> HttpResponse:
        response = super().form_valid(form)
        messages.success(self.request, "スケジュールを削除しました。")
        return response


class TodoCompleteRedirectView(LoginRequiredMixin, View):
    """ToDo の「完了として記録」アクション。

    POST されるとログ作成画面へ source_type / source_ref / year_month /
    bonsai / task_type をクエリパラメータでプリフィルしてリダイレクトする。
    実際の ``mark_todo_done`` 呼び出しはログ保存時に行う（重複防止）。
    """

    def post(
        self,
        request: HttpRequest,
        source_type: str,
        source_ref: str,
    ) -> HttpResponseRedirect:
        # year_month
        try:
            year = int(request.POST.get("year", timezone.localdate().year))
            month = int(request.POST.get("month", timezone.localdate().month))
        except (TypeError, ValueError):
            today = timezone.localdate()
            year, month = today.year, today.month
        bonsai_id = request.POST.get("bonsai", "")
        task_type = request.POST.get("task_type", "")
        url = reverse("logs:create")
        params = (
            f"?source_type={source_type}&source_ref={source_ref}&year_month={year:04d}-{month:02d}"
        )
        if bonsai_id:
            params += f"&bonsai={bonsai_id}"
        if task_type:
            params += f"&task_type={task_type}"
        return redirect(url + params)
