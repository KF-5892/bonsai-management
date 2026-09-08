"""accounts アプリのビュー定義。

設定ゾーン（プロフィール / 通知設定 / ライブラリ入口）を担当する。
マスタ類（タグ・肥料・品種）は「ライブラリ」画面から各アプリの画面へ遷移する
（docs/サイトマップ.md §11 「マスタ管理画面の入口統合」）。
"""

from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views.generic import TemplateView, UpdateView

from apps.bonsai.models import BonsaiPlant, BonsaiSpecies, Tag
from apps.logs.models import Fertilizer

from .forms import NotificationSettingForm, ProfileForm
from .models import User


class SettingsView(LoginRequiredMixin, TemplateView):
    """設定トップ。プロフィール・通知設定・ライブラリ・アカウント操作の入口。"""

    template_name = "accounts/settings.html"


class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    """プロフィール編集。"""

    model = User
    form_class = ProfileForm
    template_name = "accounts/profile_form.html"
    success_url = reverse_lazy("accounts:settings")

    def get_object(self, queryset: Any = None) -> User:
        return self.request.user  # type: ignore[return-value]

    def form_valid(self, form: ProfileForm) -> HttpResponse:
        response = super().form_valid(form)
        messages.success(self.request, "プロフィールを更新しました。")
        return response


class NotificationSettingView(LoginRequiredMixin, UpdateView):
    """通知設定（配信は Phase 3。ここでは設定値のみ保持する）。"""

    model = User
    form_class = NotificationSettingForm
    template_name = "accounts/notification_form.html"
    success_url = reverse_lazy("accounts:settings")

    def get_object(self, queryset: Any = None) -> User:
        return self.request.user  # type: ignore[return-value]

    def form_valid(self, form: NotificationSettingForm) -> HttpResponse:
        response = super().form_valid(form)
        messages.success(self.request, "通知設定を保存しました。")
        return response


class LibraryView(LoginRequiredMixin, TemplateView):
    """ライブラリ（メディア / タグ / 肥料 / 品種マスタ）の統合入口。"""

    template_name = "accounts/library.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        ctx["tag_count"] = Tag.objects.filter(user=user).count()
        ctx["fertilizer_count"] = Fertilizer.objects.visible_to(user).count()
        ctx["species_list"] = BonsaiSpecies.objects.all()[:50]
        ctx["plants"] = BonsaiPlant.objects.filter(user=user).select_related("species")
        return ctx
