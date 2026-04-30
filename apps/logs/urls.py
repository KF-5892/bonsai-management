"""logs アプリ URL ルーティング。"""

from __future__ import annotations

from django.urls import path

from . import views

app_name = "logs"

urlpatterns = [
    path("", views.CareLogListView.as_view(), name="list"),
    path("new/", views.CareLogCreateView.as_view(), name="create"),
    path("<str:pk>/", views.CareLogDetailView.as_view(), name="detail"),
    path("<str:pk>/edit/", views.CareLogUpdateView.as_view(), name="edit"),
    path("<str:pk>/delete/", views.CareLogDeleteView.as_view(), name="delete"),
]
