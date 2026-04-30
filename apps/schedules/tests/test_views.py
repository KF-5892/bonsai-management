"""schedules アプリのビュー最小スモークテスト。"""

from __future__ import annotations

from django.urls import reverse


def test_schedules_list_requires_login(client):
    res = client.get(reverse("schedules:list"))
    assert res.status_code == 302


def test_schedules_list_renders(client, user):
    client.force_login(user)
    res = client.get(reverse("schedules:list"))
    assert res.status_code == 200
    assert "todos" in res.context


def test_todo_complete_redirects_to_log_create(client, user):
    client.force_login(user)
    res = client.post(
        reverse(
            "schedules:todo_complete",
            kwargs={"source_type": "advice", "source_ref": "advice:abc-123"},
        ),
        data={"year": 2026, "month": 5, "task_type": "watering"},
    )
    assert res.status_code == 302
    assert reverse("logs:create") in res.url
    assert "source_type=advice" in res.url
    assert "year_month=2026-05" in res.url
