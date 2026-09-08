"""logs アプリ URL ルーティング。"""

from __future__ import annotations

from django.urls import path

from . import views

app_name = "logs"

urlpatterns = [
    path("", views.CareLogListView.as_view(), name="list"),
    path("new/", views.CareLogCreateView.as_view(), name="create"),
    path("bulk/", views.BulkCareLogCreateView.as_view(), name="bulk_create"),
    # 肥料マスタ（``<str:pk>`` パターンより前に置いて誤マッチを防ぐ）
    path("fertilizers/", views.FertilizerListView.as_view(), name="fertilizer_list"),
    path("fertilizers/new/", views.FertilizerCreateView.as_view(), name="fertilizer_create"),
    path(
        "fertilizers/<str:pk>/edit/",
        views.FertilizerUpdateView.as_view(),
        name="fertilizer_edit",
    ),
    path(
        "fertilizers/<str:pk>/delete/",
        views.FertilizerDeleteView.as_view(),
        name="fertilizer_delete",
    ),
    path("<str:pk>/", views.CareLogDetailView.as_view(), name="detail"),
    path("<str:pk>/edit/", views.CareLogUpdateView.as_view(), name="edit"),
    path("<str:pk>/delete/", views.CareLogDeleteView.as_view(), name="delete"),
]
