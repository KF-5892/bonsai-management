"""本番運用まわりの回帰テスト（ヘルスチェック / 静的資産の自前配信）。"""

from __future__ import annotations

from unittest import mock

from django.db import DatabaseError
from django.urls import reverse


def test_healthz_returns_ok_without_login(client):
    res = client.get(reverse("healthz"))
    assert res.status_code == 200
    assert res.content == b"ok"


def test_healthz_reports_db_outage(client):
    with mock.patch("apps.common.views.connection.cursor", side_effect=DatabaseError("down")):
        res = client.get(reverse("healthz"))
    assert res.status_code == 503


def test_pages_do_not_depend_on_cdn(client):
    """Tailwind / Alpine / htmx はビルド済みファイルを配信し、CDN を参照しない。"""
    html = client.get(reverse("account_login")).content.decode()
    for host in ("cdn.tailwindcss.com", "unpkg.com", "cdn.jsdelivr.net"):
        assert host not in html, host
    assert "/static/css/tailwind.css" in html
    assert "/static/js/alpine.min.js" in html
