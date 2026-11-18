"""作業ログ・肥料マスタのドメインモデル。

設計（docs/技術要件書.md §1, §4 / docs/開発前検討事項.md §4.3）:
- 主キーは UUIDv7（URL 列挙耐性 + 時系列ソート可）
- 作業種別 `task_type` は `apps.bonsai.models.TaskType` を再利用し、
  「その他」フォールバック時は `task_type_other` に自由入力を保持する
- 1 回の記録に複数の作業種別を付けられる。`task_type` は主となる種別
  （選んだうち `TaskType` の定義順で最初のもの）で、2 つ目以降は
  `CareLogExtraTask` に持つ。既存データや 1 種別だけの記録は従来のまま
- 肥料マスタはハイブリッド方式（共通マスタ + ユーザー個別）を
  `Fertilizer.user` の null/非null で表現する（MVP）
- 薬剤マスタも肥料と同じハイブリッド方式。消毒の記録は「目的」「薬剤（複数）」
  「希釈倍率」「展着剤の有無」「対象の病害虫」を `CareLog` に持つ
- 状態評価は 1〜5 の 5 段階（5_1〜5_5 に対応）
"""

from __future__ import annotations

from collections.abc import Iterable

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


class PestControlPurpose(models.TextChoices):
    """消毒の目的。殺虫と殺菌を混ぜて一度に散布することが多いので複数選べる。"""

    INSECTICIDE = "insecticide", _("殺虫")
    MITICIDE = "miticide", _("殺ダニ")
    FUNGICIDE = "fungicide", _("殺菌")
    DORMANT = "dormant", _("冬季消毒")


class PesticideCategory(models.TextChoices):
    """薬剤の区分。"""

    INSECTICIDE = "insecticide", _("殺虫剤")
    MITICIDE = "miticide", _("殺ダニ剤")
    FUNGICIDE = "fungicide", _("殺菌剤")
    INSECTICIDE_FUNGICIDE = "insecticide_fungicide", _("殺虫殺菌剤")
    DORMANT = "dormant", _("冬季消毒用（石灰硫黄合剤・マシン油など）")
    OTHER = "other", _("その他")


class PesticideFormulation(models.TextChoices):
    """薬剤の剤型。"""

    EMULSION = "emulsion", _("乳剤")
    WETTABLE_POWDER = "wettable_powder", _("水和剤")
    FLOWABLE = "flowable", _("フロアブル")
    LIQUID = "liquid", _("液剤")
    GRANULE = "granule", _("粒剤")
    SPRAY = "spray", _("スプレー（そのまま使う）")
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
# 薬剤マスタ
# ---------------------------------------------------------------------------
class PesticideQuerySet(models.QuerySet):
    """共通マスタ / ユーザー個別を区別するための QuerySet ヘルパー。"""

    def personal(self, user) -> PesticideQuerySet:
        """指定ユーザーの個別登録のみを返す。"""
        return self.filter(user=user)

    def visible_to(self, user) -> PesticideQuerySet:
        """指定ユーザーが選択可能な薬剤（共通マスタ + 自分の個別）を返す。"""
        return self.filter(models.Q(user__isnull=True) | models.Q(user=user))


class Pesticide(models.Model):
    """消毒に使う薬剤のマスタ（共通マスタ + ユーザー個別 のハイブリッド）。

    商品は販売終了や登録内容の変更があるため、共通マスタは最小限にとどめ、
    基本は各ユーザーが手持ちの薬剤を登録する。
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
        related_name="pesticides",
        verbose_name=_("登録ユーザー"),
        help_text=_("NULL の場合は共通マスタ（管理者編集）"),
    )
    name = models.CharField(_("薬剤名"), max_length=100)
    category = models.CharField(
        _("区分"),
        max_length=32,
        choices=PesticideCategory.choices,
        default=PesticideCategory.INSECTICIDE,
    )
    formulation = models.CharField(
        _("剤型"),
        max_length=32,
        choices=PesticideFormulation.choices,
        blank=True,
    )
    default_dilution = models.CharField(
        _("ふだんの希釈倍率"),
        max_length=40,
        blank=True,
        help_text=_("自由入力（例: 1000倍、原液）。ラベルの記載を確認して入力する"),
    )
    note = models.TextField(_("メモ"), blank=True)
    created_at = models.DateTimeField(_("作成日時"), auto_now_add=True)
    updated_at = models.DateTimeField(_("更新日時"), auto_now=True)

    objects = PesticideQuerySet.as_manager()

    class Meta:
        verbose_name = _("薬剤")
        verbose_name_plural = _("薬剤")
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
    pest_control_purposes = models.JSONField(
        _("消毒の目的"),
        default=list,
        blank=True,
        help_text=_("PestControlPurpose の値のリスト（消毒時のみ）"),
    )
    pesticides = models.ManyToManyField(
        Pesticide,
        blank=True,
        related_name="logs",
        verbose_name=_("使用した薬剤"),
        help_text=_("消毒時のみ指定する。混ぜて使った薬剤は複数選ぶ"),
    )
    pesticide_dilution = models.CharField(
        _("希釈倍率"),
        max_length=40,
        blank=True,
        help_text=_("自由入力（例: 1000倍、原液）"),
    )
    spreader_used = models.BooleanField(_("展着剤を使用"), default=False)
    pest_target = models.CharField(
        _("対象の病害虫"),
        max_length=80,
        blank=True,
        help_text=_("自由入力（例: アブラムシ、うどんこ病）"),
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
        return f"{self.bonsai.name} - {self.task_label} ({self.performed_at})"

    @property
    def task_type_values(self) -> list[str]:
        """この記録の作業種別すべて（主となる種別が先頭）。"""
        # 主キーは UUID の既定値で保存前から入るため、保存済みかどうかは _state で判定する
        saved = not self._state.adding
        extras = [extra.task_type for extra in self.extra_tasks.all()] if saved else []
        return [self.task_type, *(value for value in extras if value != self.task_type)]

    @property
    def task_label(self) -> str:
        """表示用の作業種別。複数あれば「剪定・施肥」のように並べる。"""
        labels = dict(TaskType.choices)
        parts = []
        for value in self.task_type_values:
            if value == TaskType.OTHER and self.task_type_other:
                parts.append(self.task_type_other)
            else:
                parts.append(str(labels.get(value, value)))
        return "・".join(parts)

    @property
    def pest_control_purpose_label(self) -> str:
        """表示用の消毒の目的（「殺虫・殺菌」のように並べる）。"""
        labels = dict(PestControlPurpose.choices)
        return "・".join(str(labels.get(v, v)) for v in self.pest_control_purposes or [])

    @property
    def pesticide_names(self) -> str:
        """表示用の薬剤名（「、」区切り）。"""
        if self._state.adding:
            return ""
        return "、".join(p.name for p in self.pesticides.all())

    @property
    def has_pest_control_details(self) -> bool:
        """消毒の付帯情報が 1 つでも入っているか。"""
        return bool(
            self.pest_control_purposes
            or self.pesticide_dilution
            or self.spreader_used
            or self.pest_target
            or self.pesticide_names
        )

    def set_task_types(self, values: Iterable[str]) -> None:
        """作業種別をまとめて設定して保存する（先頭を主、残りを追加の種別にする）。"""
        primary, extras = split_task_types(values)
        if self.task_type != primary:
            self.task_type = primary
            self.save(update_fields=["task_type", "updated_at"])
        self.extra_tasks.exclude(task_type__in=extras).delete()
        existing = set(self.extra_tasks.values_list("task_type", flat=True))
        CareLogExtraTask.objects.bulk_create(
            CareLogExtraTask(log=self, task_type=value) for value in extras if value not in existing
        )


def split_task_types(values: Iterable[str]) -> tuple[str, list[str]]:
    """作業種別の並びを ``TaskType`` の定義順に整え、(主, 追加) に分ける。"""
    selected = set(values)
    ordered = [value for value in TaskType.values if value in selected]
    if not ordered:
        raise ValueError("作業種別を 1 つ以上指定してください。")
    return ordered[0], ordered[1:]


def with_task_type(queryset: models.QuerySet[CareLog], task_type: str) -> models.QuerySet[CareLog]:
    """主・追加のどちらかに ``task_type`` を含むログへ絞り込む。"""
    return queryset.filter(
        models.Q(task_type=task_type) | models.Q(extra_tasks__task_type=task_type)
    ).distinct()


class CareLogExtraTask(models.Model):
    """1 つの作業ログに付く 2 つ目以降の作業種別。"""

    id = models.CharField(
        primary_key=True,
        max_length=36,
        default=uuid7_str,
        editable=False,
    )
    log = models.ForeignKey(
        CareLog,
        on_delete=models.CASCADE,
        related_name="extra_tasks",
        verbose_name=_("作業ログ"),
    )
    task_type = models.CharField(
        _("作業種別"),
        max_length=32,
        choices=TaskType.choices,
    )

    class Meta:
        verbose_name = _("追加の作業種別")
        verbose_name_plural = _("追加の作業種別")
        ordering = ("id",)
        constraints = [
            models.UniqueConstraint(fields=["log", "task_type"], name="uniq_care_log_extra_task"),
        ]
        indexes = [
            models.Index(fields=["task_type"]),
        ]

    def __str__(self) -> str:
        return f"{self.log_id} - {self.get_task_type_display()}"
