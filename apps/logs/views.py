"""logs アプリのビュー定義。

- 作業ログ一覧（自分のログのみ、検索 ``?q=`` で notes / bonsai__name フィルタ）
- 作業ログ CRUD
- ToDo プリフィル（``?bonsai=&task_type=&source_type=&source_ref=&year_month=YYYY-MM``）
  に対応し、保存時に ``mark_todo_done`` を呼んで完了状態を記録する
"""

from __future__ import annotations

from datetime import date
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, QuerySet
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from apps.schedules.services.todos import mark_todo_done

from .forms import CareLogForm
from .models import CareLog


class CareLogListView(LoginRequiredMixin, ListView):
    model = CareLog
    template_name = "logs/list.html"
    context_object_name = "logs"
    paginate_by = 30

    def get_queryset(self) -> QuerySet[CareLog]:
        qs = (
            CareLog.objects.filter(user=self.request.user)
            .select_related("bonsai", "fertilizer")
            .order_by("-performed_at")
        )
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(notes__icontains=q) | Q(bonsai__name__icontains=q))
        return qs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = self.request.GET.get("q", "")
        return ctx


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

    def get_success_url(self) -> str:
        return reverse_lazy("logs:detail", kwargs={"pk": self.object.pk})


class CareLogDeleteView(LoginRequiredMixin, DeleteView):
    model = CareLog
    template_name = "logs/confirm_delete.html"
    success_url = reverse_lazy("logs:list")

    def get_queryset(self) -> QuerySet[CareLog]:
        return CareLog.objects.filter(user=self.request.user)
