"""ケアスケジュール・月次アドバイス・完了状態のドメインモデル。

設計方針（docs/技術要件書.md §10、docs/開発前検討事項.md §10.1 「A 案」）:
- 「今月のやること」は 3 ソース（品種マスタ由来 / ユーザー個別 / 月次共通アドバイス）を
  オンデマンドに合成する。スケジュール本体は ``CareSchedule`` のみ DB に持ち、
  品種マスタ由来の仮想タスクと月次アドバイスは ``BonsaiSpecies.monthly_tasks`` と
  ``MonthlyAdvice`` から都度展開する。
- 完了状態だけは別テーブル ``CareScheduleCompletion`` に保存する。
  これにより仮想タスク（品種マスタ由来）にもユニークな ``source_ref`` で完了印を
  付けられる。
- 主キーは UUIDv7（``apps.common.utils.uuid7_str``）。
- ``CareScheduleCompletion.log`` は別チームが並行実装中の ``logs.CareLog`` への FK。
  循環 import を避けるため文字列参照（``"logs.CareLog"``）を使う。
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.utils import uuid7_str


# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------
class TaskType(models.TextChoices):
    """作業種別。

    ``apps.bonsai.models.TaskType`` と同じ列挙値を持つが、循環 import を避けるため
    schedules 内に独立して定義している（MVP の判断、docs/開発前検討事項.md §10.1）。
    両者の値（DB に保持される文字列）が一致するよう、変更時は両方の同期を必ず行う。
    """

    WATERING = "watering", _("潅水")
    FERTILIZING = "fertilizing", _("施肥")
    PRUNING = "pruning", _("剪定")
    REPOTTING = "repotting", _("植え替え")
    OBSERVATION = "observation", _("観察")
    BUD_PINCHING = "bud_pinching", _("芽摘み")
    DEFOLIATION = "defoliation", _("葉刈り")
    LEAF_MISTING = "leaf_misting", _("葉水")
    WIRING = "wiring", _("針金かけ")
    UNWIRING = "unwiring", _("針金外し")
    PEST_CONTROL = "pest_control", _("消毒")
    JIN_SHARI = "jin_shari", _("ジン・シャリ作り")
    AIR_LAYERING = "air_layering", _("取り木")
    CUTTING = "cutting", _("挿し木")
    OTHER = "other", _("その他")


class RepeatType(models.TextChoices):
    """繰り返し種別。"""

    NONE = "none", _("繰り返しなし")
    DAILY = "daily", _("毎日")
    WEEKLY = "weekly", _("毎週")
    MONTHLY = "monthly", _("毎月")
    YEARLY = "yearly", _("毎年")
    CUSTOM = "custom", _("カスタム")


class CompletionSourceType(models.TextChoices):
    """完了状態の参照元種別。"""

    SPECIES_TASK = "species_task", _("品種マスタ由来")
    SCHEDULE = "schedule", _("ユーザー個別スケジュール")
    ADVICE = "advice", _("月次共通アドバイス")


class CompletionStatus(models.TextChoices):
    """完了状態。"""

    DONE = "done", _("完了")
    SKIPPED = "skipped", _("スキップ")
    PENDING = "pending", _("保留")


# ---------------------------------------------------------------------------
# 個別ケアスケジュール
# ---------------------------------------------------------------------------
class CareSchedule(models.Model):
    """ユーザーが個別に登録するケアスケジュール。

    `repeat_rule` は iCal RFC5545 風の JSON。例::

        {"interval": 7, "byweekday": ["MO"]}
        {"interval": 1, "bymonthday": 15}
    """

    id = models.CharField(
        primary_key=True,
        max_length=36,
        default=uuid7_str,
        editable=False,
    )
    bonsai = models.ForeignKey(
        "bonsai.BonsaiPlant",
        on_delete=models.CASCADE,
        related_name="schedules",
        verbose_name=_("対象盆栽"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="schedules",
        verbose_name=_("所有者"),
        help_text=_("権限チェック簡略化のため非正規化して保持する"),
    )
    task_type = models.CharField(
        _("作業種別"),
        max_length=32,
        choices=TaskType.choices,
        default=TaskType.OTHER,
    )
    title = models.CharField(
        _("タスク名"),
        max_length=120,
        blank=True,
        help_text=_("例: 黒松の水やり"),
    )
    notes = models.TextField(_("メモ"), blank=True)
    repeat_type = models.CharField(
        _("繰り返し種別"),
        max_length=16,
        choices=RepeatType.choices,
        default=RepeatType.NONE,
    )
    repeat_rule = models.JSONField(
        _("繰り返しルール"),
        default=dict,
        blank=True,
        help_text=_('iCal RFC5545 風の JSON。例: {"interval": 7, "byweekday": ["MO"]}'),
    )
    start_date = models.DateField(_("開始日"))
    next_run_at = models.DateField(
        _("次回予定日"),
        null=True,
        blank=True,
        help_text=_("一覧クエリ高速化のため都度キャッシュする"),
    )
    is_active = models.BooleanField(_("有効"), default=True)
    created_at = models.DateTimeField(_("作成日時"), auto_now_add=True)
    updated_at = models.DateTimeField(_("更新日時"), auto_now=True)

    class Meta:
        verbose_name = _("ケアスケジュール")
        verbose_name_plural = _("ケアスケジュール")
        ordering = ["next_run_at", "-created_at"]
        indexes = [
            models.Index(fields=["user", "next_run_at"]),
            models.Index(fields=["bonsai", "is_active"]),
        ]

    def __str__(self) -> str:
        return self.title or f"{self.get_task_type_display()} / {self.bonsai_id}"


# ---------------------------------------------------------------------------
# 月次共通アドバイス
# ---------------------------------------------------------------------------
class MonthlyAdvice(models.Model):
    """月ごとの共通アドバイス（全ユーザー共通）。"""

    id = models.CharField(
        primary_key=True,
        max_length=36,
        default=uuid7_str,
        editable=False,
    )
    month = models.PositiveSmallIntegerField(
        _("対象月"),
        validators=[MinValueValidator(1), MaxValueValidator(12)],
    )
    title = models.CharField(_("タイトル"), max_length=120)
    advice_text = models.TextField(_("アドバイス本文"))
    category = models.CharField(
        _("カテゴリ"),
        max_length=32,
        blank=True,
        help_text=_("例: 灌水、全般、病害虫など任意のラベル"),
    )
    is_published = models.BooleanField(_("公開"), default=True)
    created_at = models.DateTimeField(_("作成日時"), auto_now_add=True)
    updated_at = models.DateTimeField(_("更新日時"), auto_now=True)

    class Meta:
        verbose_name = _("月次アドバイス")
        verbose_name_plural = _("月次アドバイス")
        ordering = ("month", "title")
        indexes = [
            models.Index(fields=["month"]),
        ]

    def __str__(self) -> str:
        return f"{self.month}月: {self.title}"


# ---------------------------------------------------------------------------
# 完了状態
# ---------------------------------------------------------------------------
class CareScheduleCompletion(models.Model):
    """月次 ToDo の完了状態。

    `source_type` / `source_ref` の組で「どの ToDo の完了か」を一意に特定する。
    `source_ref` の規約:

    - ``species_task:{species_id}:{month}:{task_index}``
    - ``schedule:{schedule_id}``
    - ``advice:{advice_id}``
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
        related_name="completions",
        verbose_name=_("ユーザー"),
    )
    source_type = models.CharField(
        _("参照元種別"),
        max_length=16,
        choices=CompletionSourceType.choices,
    )
    source_ref = models.CharField(
        _("参照キー"),
        max_length=200,
        help_text=_(
            "例: species_task:{species_id}:{month}:{task_index} / "
            "schedule:{schedule_id} / advice:{advice_id}"
        ),
    )
    bonsai = models.ForeignKey(
        "bonsai.BonsaiPlant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="completions",
        verbose_name=_("対象盆栽"),
    )
    year_month = models.DateField(
        _("対象年月"),
        help_text=_("対象月の 1 日固定（年月単位の完了状態）"),
    )
    status = models.CharField(
        _("状態"),
        max_length=16,
        choices=CompletionStatus.choices,
        default=CompletionStatus.DONE,
    )
    completed_at = models.DateTimeField(_("完了日時"), default=timezone.now)
    log = models.ForeignKey(
        "logs.CareLog",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="completions",
        verbose_name=_("関連ケアログ"),
        help_text=_("プリフィル経由で作成したログへの参照"),
    )

    class Meta:
        verbose_name = _("ToDo 完了状態")
        verbose_name_plural = _("ToDo 完了状態")
        ordering = ("-completed_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["user", "source_type", "source_ref", "year_month"],
                name="unique_completion_per_month",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "year_month"]),
            models.Index(fields=["bonsai", "year_month"]),
        ]

    def __str__(self) -> str:
        return f"{self.source_type}:{self.source_ref}@{self.year_month:%Y-%m}"
