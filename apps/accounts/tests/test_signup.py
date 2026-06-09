"""allauth サインアップ/ログイン画面のスモークテスト。

カスタム User は ``username`` を廃止しているため、
``ACCOUNT_USER_MODEL_USERNAME_FIELD = None`` が設定されていないと
signup フォームが存在しない username フィールドを参照して 500 になる。
本テストはその回帰を防ぐ。
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


@pytest.mark.django_db
def test_signup_page_renders(client):
    """サインアップ画面が 200 で表示される（username 参照で落ちない）。"""
    resp = client.get(reverse("account_signup"))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_login_page_renders(client):
    resp = client.get(reverse("account_login"))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_signup_creates_user_with_email(client):
    """email + パスワードのみでユーザー登録できる。"""
    resp = client.post(
        reverse("account_signup"),
        {
            "email": "newbie@example.com",
            "password1": "Str0ngPass!23",
            "password2": "Str0ngPass!23",
        },
    )
    assert resp.status_code == 302
    assert User.objects.filter(email="newbie@example.com").exists()
