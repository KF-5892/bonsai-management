"""bonsai アプリ URL ルーティング。

ルート ``/`` をホームに割り当て、盆栽 CRUD と品種詳細を含める。
"""

from __future__ import annotations

from django.urls import path

from . import views

app_name = "bonsai"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("tags/", views.TagListView.as_view(), name="tag_list"),
    path("tags/new/", views.TagCreateView.as_view(), name="tag_create"),
    path("tags/<str:pk>/edit/", views.TagUpdateView.as_view(), name="tag_edit"),
    path("tags/<str:pk>/delete/", views.TagDeleteView.as_view(), name="tag_delete"),
    path("bonsai/new/", views.BonsaiPlantCreateView.as_view(), name="create"),
    path("bonsai/<str:pk>/", views.BonsaiPlantDetailView.as_view(), name="detail"),
    path("bonsai/<str:pk>/edit/", views.BonsaiPlantUpdateView.as_view(), name="edit"),
    path("bonsai/<str:pk>/delete/", views.BonsaiPlantDeleteView.as_view(), name="delete"),
    path("bonsai/<str:pk>/media/", views.BonsaiMediaGalleryView.as_view(), name="media_gallery"),
    path(
        "bonsai/<str:pk>/media/upload/",
        views.BonsaiMediaCreateView.as_view(),
        name="media_upload",
    ),
    path(
        "bonsai/<str:pk>/media/<str:media_pk>/cover/",
        views.BonsaiMediaSetCoverView.as_view(),
        name="media_set_cover",
    ),
    path(
        "bonsai/<str:pk>/media/<str:media_pk>/delete/",
        views.BonsaiMediaDeleteView.as_view(),
        name="media_delete",
    ),
    path("species/<slug:slug>/", views.BonsaiSpeciesDetailView.as_view(), name="species_detail"),
]
