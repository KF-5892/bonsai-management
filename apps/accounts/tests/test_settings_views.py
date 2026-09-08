"""設定ゾーン（設定トップ / プロフィール / 通知設定 / ライブラリ）のテスト。"""

from __future__ import annotations

from django.urls import reverse


def test_settings_requires_login(client):
    res = client.get(reverse("accounts:settings"))
    assert res.status_code == 302


def test_settings_renders(client, user):
    client.force_login(user)
    res = client.get(reverse("accounts:settings"))
    assert res.status_code == 200
    assert user.email in res.content.decode()


def test_profile_update(client, user):
    client.force_login(user)
    res = client.post(
        reverse("accounts:profile"),
        {"display_name": "盆栽好き", "language": "ja"},
    )
    assert res.status_code == 302
    user.refresh_from_db()
    assert user.display_name == "盆栽好き"


def test_notification_setting_update(client, user):
    client.force_login(user)
    res = client.post(
        reverse("accounts:notifications"),
        {"notify_start_time": "08:00", "notify_end_time": "20:00"},
    )
    assert res.status_code == 302
    user.refresh_from_db()
    # チェックボックス未送信は False として保存される
    assert user.notification_enabled is False
    assert str(user.notify_start_time) == "08:00:00"


def test_library_renders(client, user):
    client.force_login(user)
    res = client.get(reverse("accounts:library"))
    assert res.status_code == 200
    assert res.context["tag_count"] == 0
