"""schedules アプリ URL ルーティング。"""

from __future__ import annotations

from django.urls import path

from . import views

app_name = "schedules"

urlpatterns = [
    path("", views.ScheduleListView.as_view(), name="list"),
    path("new/", views.CareScheduleCreateView.as_view(), name="create"),
    path("<str:pk>/edit/", views.CareScheduleUpdateView.as_view(), name="edit"),
    path("<str:pk>/delete/", views.CareScheduleDeleteView.as_view(), name="delete"),
    path(
        "todos/<str:source_type>/<path:source_ref>/complete/",
        views.TodoCompleteRedirectView.as_view(),
        name="todo_complete",
    ),
]
