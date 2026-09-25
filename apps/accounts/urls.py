"""accounts アプリ URL ルーティング（設定ゾーン）。"""

from __future__ import annotations

from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.SettingsView.as_view(), name="settings"),
    path("profile/", views.ProfileUpdateView.as_view(), name="profile"),
    path("notifications/", views.NotificationSettingView.as_view(), name="notifications"),
    path("library/", views.LibraryView.as_view(), name="library"),
]
