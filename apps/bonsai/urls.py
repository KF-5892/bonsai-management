"""bonsai アプリ URL ルーティング。

ルート ``/`` をホームに割り当て、盆栽 CRUD と品種詳細を含める。
"""

from __future__ import annotations

from django.urls import path

from . import views

app_name = "bonsai"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("bonsai/new/", views.BonsaiPlantCreateView.as_view(), name="create"),
    path("bonsai/<str:pk>/", views.BonsaiPlantDetailView.as_view(), name="detail"),
    path("bonsai/<str:pk>/edit/", views.BonsaiPlantUpdateView.as_view(), name="edit"),
    path("bonsai/<str:pk>/delete/", views.BonsaiPlantDeleteView.as_view(), name="delete"),
    path("species/<slug:slug>/", views.BonsaiSpeciesDetailView.as_view(), name="species_detail"),
]
