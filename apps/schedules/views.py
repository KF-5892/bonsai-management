"""schedules アプリのビュー定義。

- 月別スケジュール一覧（year, month クエリで切替、デフォルト: 当月）
- 個別スケジュール CRUD
- ToDo 完了アクション（``mark_todo_done`` 経由）
"""

from __future__ import annotations

from datetime import date
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, UpdateView

from .forms import CareScheduleForm
from .models import CareSchedule
from .services.todos import compose_monthly_todos


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


class ScheduleListView(LoginRequiredMixin, View):
    """当月の ToDo 一覧。"""

    template_name = "schedules/list.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        from django.shortcuts import render

        year_month = _resolve_year_month(request)
        todos = compose_monthly_todos(request.user, year_month)
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

    def form_valid(self, form: CareScheduleForm) -> HttpResponse:
        form.instance.user = self.request.user
        return super().form_valid(form)


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


class CareScheduleDeleteView(LoginRequiredMixin, DeleteView):
    model = CareSchedule
    template_name = "schedules/confirm_delete.html"
    success_url = reverse_lazy("schedules:list")

    def get_queryset(self) -> QuerySet[CareSchedule]:
        return CareSchedule.objects.filter(user=self.request.user)


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
