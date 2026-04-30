"""作業ログ・肥料マスタのドメインモデル。

設計（docs/技術要件書.md §1, §4 / docs/開発前検討事項.md §4.3）:
- 主キーは UUIDv7（URL 列挙耐性 + 時系列ソート可）
- 作業種別 `task_type` は `apps.bonsai.models.TaskType` を再利用し、
  「その他」フォールバック時は `task_type_other` に自由入力を保持する
- 肥料マスタはハイブリッド方式（共通マスタ + ユーザー個別）を
  `Fertilizer.user` の null/非null で表現する（MVP）
- 状態評価は 1〜5 の 5 段階（5_1〜5_5 に対応）
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

# bonsai 側で既に定義済みの TaskType を再利用する（拡張候補が同じ列挙）。
from apps.bonsai.models import TaskType
from apps.common.utils import uuid7_str


# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------
class FertilizerForm(models.TextChoices):
    """肥料の形状区分。"""

    SOLID = "solid", _("固形")
    LIQUID = "liquid", _("液体")
    OTHER = "other", _("その他")


class Weather(models.TextChoices):
    """作業時の天候。

    UI からは label（日本語）で扱い、DB には value を保持する。
    """

    SUNNY = "sunny", _("晴れ")
    CLOUDY = "cloudy", _("曇り")
    RAINY = "rainy", _("雨")
    SNOWY = "snowy", _("雪")
    OTHER = "other", _("その他")


class HealthEvaluation(models.IntegerChoices):
    """5 段階状態評価（5_1〜5_5 の 5 段階に対応）。"""

    VERY_BAD = 1, _("1: 非常に悪い")
    BAD = 2, _("2: 悪い")
    NORMAL = 3, _("3: 普通")
    GOOD = 4, _("4: 良い")
    VERY_GOOD = 5, _("5: 非常に良い")


# ---------------------------------------------------------------------------
# 肥料マスタ
# ---------------------------------------------------------------------------
class FertilizerQuerySet(models.QuerySet):
    """共通マスタ / ユーザー個別を区別するための QuerySet ヘルパー。"""

    def common(self) -> FertilizerQuerySet:
        """共通マスタ（user=None）のみを返す。"""
        return self.filter(user__isnull=True)

    def personal(self, user) -> FertilizerQuerySet:
        """指定ユーザーの個別登録のみを返す。"""
        return self.filter(user=user)

    def visible_to(self, user) -> FertilizerQuerySet:
        """指定ユーザーが選択可能な肥料（共通マスタ + 自分の個別）を返す。"""
        return self.filter(models.Q(user__isnull=True) | models.Q(user=user))


class Fertilizer(models.Model):
    """肥料マスタ（共通マスタ + ユーザー個別 のハイブリッド）。

    `user` が NULL の場合は管理者が編集する共通マスタとして扱い、
    非 NULL の場合はそのユーザー個別の登録として扱う。
    """

    id = models.CharField(
        primary_key=True,
        max_length=36,
        default=uuid7_str,
        editable=False,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="fertilizers",
        verbose_name=_("登録ユーザー"),
        help_text=_("NULL の場合は共通マスタ（管理者編集）"),
    )
    name = models.CharField(_("肥料名"), max_length=100)
    form_type = models.CharField(
        _("形状"),
        max_length=16,
        choices=FertilizerForm.choices,
        default=FertilizerForm.SOLID,
    )
    n = models.DecimalField(
        _("窒素 (N) %"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    p = models.DecimalField(
        _("リン酸 (P) %"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    k = models.DecimalField(
        _("カリウム (K) %"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    is_organic = models.BooleanField(_("有機肥料"), default=False)
    note = models.TextField(_("メモ"), blank=True)
    created_at = models.DateTimeField(_("作成日時"), auto_now_add=True)
    updated_at = models.DateTimeField(_("更新日時"), auto_now=True)

    objects = FertilizerQuerySet.as_manager()

    class Meta:
        verbose_name = _("肥料")
        verbose_name_plural = _("肥料")
        ordering = ["name"]
        indexes = [
            models.Index(fields=["user", "name"]),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def is_common(self) -> bool:
        """共通マスタ（管理者編集の全ユーザー共有エントリ）かどうか。"""
        return self.user_id is None


# ---------------------------------------------------------------------------
# 作業実績ログ
# ---------------------------------------------------------------------------
class CareLog(models.Model):
    """盆栽 1 個体に対する作業実績ログ。"""

    id = models.CharField(
        primary_key=True,
        max_length=36,
        default=uuid7_str,
        editable=False,
    )
    bonsai = models.ForeignKey(
        "bonsai.BonsaiPlant",
        on_delete=models.CASCADE,
        related_name="logs",
        verbose_name=_("盆栽"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="care_logs",
        verbose_name=_("実施ユーザー"),
        help_text=_("通常は bonsai.user と同じ値（権限チェック簡略化のため冗長保持）"),
    )
    task_type = models.CharField(
        _("作業種別"),
        max_length=32,
        choices=TaskType.choices,
        default=TaskType.OBSERVATION,
    )
    task_type_other = models.CharField(
        _("作業種別（その他）"),
        max_length=80,
        blank=True,
        help_text=_("task_type が「その他」のときの自由入力"),
    )
    performed_at = models.DateTimeField(_("実施日時"), default=timezone.now)
    weather = models.CharField(
        _("天候"),
        max_length=16,
        choices=Weather.choices,
        blank=True,
    )
    temperature_c = models.DecimalField(
        _("気温 (℃)"),
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
    )
    notes = models.TextField(_("メモ"), blank=True)
    photo = models.ImageField(
        _("写真"),
        upload_to="care_logs/%Y/%m/",
        blank=True,
    )
    fertilizer = models.ForeignKey(
        Fertilizer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logs",
        verbose_name=_("使用した肥料"),
        help_text=_("施肥時のみ指定する"),
    )
    fertilizer_amount = models.CharField(
        _("肥料の量"),
        max_length=40,
        blank=True,
        help_text=_("自由入力（例: 1g、3粒）"),
    )
    health_evaluation = models.PositiveSmallIntegerField(
        _("状態評価"),
        choices=HealthEvaluation.choices,
        null=True,
        blank=True,
        help_text=_("1〜5 の 5 段階評価"),
    )
    created_at = models.DateTimeField(_("作成日時"), auto_now_add=True)
    updated_at = models.DateTimeField(_("更新日時"), auto_now=True)

    class Meta:
        verbose_name = _("作業ログ")
        verbose_name_plural = _("作業ログ")
        ordering = ("-performed_at",)
        indexes = [
            models.Index(fields=["bonsai", "-performed_at"]),
            models.Index(fields=["task_type"]),
        ]

    def __str__(self) -> str:
        return f"{self.bonsai.name} - {self.get_task_type_display()} ({self.performed_at})"
