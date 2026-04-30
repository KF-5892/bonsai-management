"""カスタム User モデル。

決定事項（docs/開発前検討事項.md §3.1）:
- AbstractUser を継承して統合（UserProfile 1:1 ではない）
- email をログイン ID として使用、`username` は廃止
- 主キーは UUIDv7（URL 列挙攻撃の防御 + 時系列ソート可）
- time_zone は MVP では JST 固定。Phase 3 通知導入時に B 方式（個別保持）へ移行
"""

from __future__ import annotations

import uuid_extensions
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _


def _uuid7() -> str:
    """UUIDv7 を発行する。"""
    return str(uuid_extensions.uuid7())


class UserManager(BaseUserManager["User"]):
    """email を主軸としたカスタムマネージャ。"""

    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra_fields: object) -> User:
        if not email:
            raise ValueError("メールアドレスは必須です")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields: object) -> User:
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(
        self, email: str, password: str | None = None, **extra_fields: object
    ) -> User:
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.ADMIN)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser は is_staff=True が必須です")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser は is_superuser=True が必須です")
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """盆栽管理アプリのユーザー。"""

    class Role(models.TextChoices):
        USER = "user", _("一般ユーザー")
        ADMIN = "admin", _("管理者")

    # username 廃止
    username = None  # type: ignore[assignment]

    id = models.CharField(
        primary_key=True,
        max_length=36,
        default=_uuid7,
        editable=False,
    )
    email = models.EmailField(_("メールアドレス"), unique=True)
    display_name = models.CharField(_("表示名"), max_length=80, blank=True)
    role = models.CharField(
        _("役割"),
        max_length=16,
        choices=Role.choices,
        default=Role.USER,
    )

    # タイムゾーン: MVP は Asia/Tokyo 固定。Phase 3 で個別保持に拡張可能。
    time_zone = models.CharField(
        _("タイムゾーン"),
        max_length=64,
        default="Asia/Tokyo",
    )
    language = models.CharField(_("言語"), max_length=8, default="ja")

    # 通知設定（Phase 3 で利用）
    notification_enabled = models.BooleanField(_("通知を有効化"), default=True)
    notify_start_time = models.TimeField(_("通知開始時刻"), null=True, blank=True)
    notify_end_time = models.TimeField(_("通知終了時刻"), null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()  # type: ignore[assignment, misc]

    class Meta:
        verbose_name = _("ユーザー")
        verbose_name_plural = _("ユーザー")

    def __str__(self) -> str:
        return self.display_name or self.email

    @property
    def is_admin(self) -> bool:
        return self.role == self.Role.ADMIN or self.is_superuser
