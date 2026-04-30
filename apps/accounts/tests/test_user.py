"""User モデルの基本動作スモークテスト。"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

User = get_user_model()


def test_create_user_with_email_as_login_id():
    user = User.objects.create_user(
        email="alice@example.com",
        password="strongpass123",
        display_name="Alice",
    )
    assert user.email == "alice@example.com"
    assert user.check_password("strongpass123")
    # 平文で保存されていないこと
    assert user.password != "strongpass123"
    assert user.role == User.Role.USER
    assert user.is_admin is False
    assert user.username is None
    assert User.USERNAME_FIELD == "email"


def test_create_superuser_is_admin():
    admin = User.objects.create_superuser(
        email="admin@example.com",
        password="adminpass123",
    )
    assert admin.is_superuser is True
    assert admin.is_staff is True
    assert admin.is_admin is True


def test_email_must_be_unique():
    User.objects.create_user(email="dup@example.com", password="x")
    with pytest.raises(IntegrityError):
        User.objects.create_user(email="dup@example.com", password="y")


def test_create_user_requires_email():
    with pytest.raises(ValueError, match="メールアドレスは必須です"):
        User.objects.create_user(email="", password="x")
