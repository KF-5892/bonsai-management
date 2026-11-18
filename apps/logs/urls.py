"""logs アプリ URL ルーティング。"""

from __future__ import annotations

from django.urls import path

from . import views

app_name = "logs"

urlpatterns = [
    path("", views.CareLogListView.as_view(), name="list"),
    path("new/", views.CareLogCreateView.as_view(), name="create"),
    path("bulk/", views.BulkCareLogCreateView.as_view(), name="bulk_create"),
    path("quick/", views.QuickCareLogCreateView.as_view(), name="quick_create"),
    path("export/", views.CareLogExportView.as_view(), name="export"),
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
    # 薬剤マスタ
    path("pesticides/", views.PesticideListView.as_view(), name="pesticide_list"),
    path("pesticides/new/", views.PesticideCreateView.as_view(), name="pesticide_create"),
    path(
        "pesticides/<str:pk>/edit/",
        views.PesticideUpdateView.as_view(),
        name="pesticide_edit",
    ),
    path(
        "pesticides/<str:pk>/delete/",
        views.PesticideDeleteView.as_view(),
        name="pesticide_delete",
    ),
    path("<str:pk>/", views.CareLogDetailView.as_view(), name="detail"),
    path("<str:pk>/edit/", views.CareLogUpdateView.as_view(), name="edit"),
    path("<str:pk>/delete/", views.CareLogDeleteView.as_view(), name="delete"),
]
