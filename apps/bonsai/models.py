"""盆栽・品種・タグ・画像のドメインモデル。

設計（docs/開発前検討事項.md・docs/技術要件書.md）:
- 主キーは UUIDv7（時系列ソート可・URL 列挙耐性）
- BonsaiSpecies は slug を URL 識別子として併用
- task_type / category / health_status は TextChoices 固定（その他フォールバックあり）
- 画像は同期で 3 段（元 / 中 1080px / サムネ 320px）に変換
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

# 共通ヘルパーから再エクスポートする（既存マイグレーションが
# `apps.bonsai.models.uuid7_str` を import 参照しているため、名前ごと
# このモジュールに残しておく必要がある）。
from apps.common.utils import uuid7_str


# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------
class SpeciesCategory(models.TextChoices):
    """品種カテゴリ（針葉樹 / 広葉樹 / 花物 / 実物）。"""

    CONIFER = "conifer", _("針葉樹")
    BROADLEAF = "broadleaf", _("広葉樹")
    FLOWERING = "flowering", _("花物")
    FRUITING = "fruiting", _("実物")
    OTHER = "other", _("その他")


class HealthStatus(models.TextChoices):
    """個体の健康ステータス。"""

    GOOD = "good", _("良好")
    WATCH = "watch", _("要注意")
    POOR = "poor", _("不調")


class TaskType(models.TextChoices):
    """月次作業や記録の作業種別。

    UI からは label（日本語）で扱い、DB には value を保持する。
    候補: 潅水・施肥・剪定・植え替え・観察・芽摘み・葉刈り・葉水・
          針金かけ・針金外し・消毒・ジン/シャリ作り・取り木・挿し木・その他
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


# ---------------------------------------------------------------------------
# Master: 品種
# ---------------------------------------------------------------------------
class BonsaiSpecies(models.Model):
    """盆栽の品種マスタ。

    `monthly_tasks` は次の構造を想定する:
        [
            {"month": 5, "period": "上旬", "task_type": "bud_pinching",
             "description": "新芽の先端を 2 枚残してつまむ"},
            ...
        ]
    """

    id = models.CharField(
        primary_key=True,
        max_length=36,
        default=uuid7_str,
        editable=False,
    )
    slug = models.SlugField(
        _("URL スラッグ"),
        max_length=64,
        unique=True,
        help_text=_("URL に利用する一意な識別子（例: kuromatsu）"),
    )
    name = models.CharField(
        _("品種名"),
        max_length=80,
        help_text=_("和名（例: 黒松）"),
    )
    scientific_name = models.CharField(
        _("学名"),
        max_length=120,
        blank=True,
    )
    category = models.CharField(
        _("カテゴリ"),
        max_length=16,
        choices=SpeciesCategory.choices,
        default=SpeciesCategory.OTHER,
    )
    description = models.TextField(
        _("解説"),
        blank=True,
        help_text=_("品種の特徴や育成のコツ"),
    )
    monthly_tasks = models.JSONField(
        _("月別作業カレンダー"),
        default=list,
        blank=True,
        help_text=_(
            "月別の標準作業を JSON 配列で保持する。"
            "例: [{month: 5, period: '上旬', task_type: 'bud_pinching', description: '...'}]"
        ),
    )
    cover_image = models.ImageField(
        _("代表画像"),
        upload_to="species/cover/%Y/%m/",
        blank=True,
    )
    created_at = models.DateTimeField(_("作成日時"), auto_now_add=True)
    updated_at = models.DateTimeField(_("更新日時"), auto_now=True)

    class Meta:
        verbose_name = _("品種")
        verbose_name_plural = _("品種")
        ordering = ["name"]
        indexes = [
            models.Index(fields=["category"]),
            models.Index(fields=["slug"]),
        ]

    def __str__(self) -> str:
        return self.name


# ---------------------------------------------------------------------------
# 盆栽（個体）
# ---------------------------------------------------------------------------
class BonsaiPlant(models.Model):
    """ユーザーが所有する盆栽（個体）。"""

    id = models.CharField(
        primary_key=True,
        max_length=36,
        default=uuid7_str,
        editable=False,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bonsai_plants",
        verbose_name=_("所有者"),
    )
    species = models.ForeignKey(
        BonsaiSpecies,
        on_delete=models.PROTECT,
        related_name="plants",
        null=True,
        blank=True,
        verbose_name=_("品種"),
        help_text=_("マスタにない品種は空欄でも登録可能"),
    )
    name = models.CharField(
        _("個体名"),
        max_length=80,
        help_text=_("ユーザーが付ける名前（例: 太郎）"),
    )
    acquired_at = models.DateField(
        _("入手日"),
        null=True,
        blank=True,
    )
    health_status = models.CharField(
        _("健康状態"),
        max_length=16,
        choices=HealthStatus.choices,
        default=HealthStatus.GOOD,
    )
    notes = models.TextField(_("メモ"), blank=True)
    cover_media = models.ForeignKey(
        "BonsaiMedia",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cover_for",
        verbose_name=_("代表画像"),
        help_text=_("一覧などで表示する代表画像"),
    )
    created_at = models.DateTimeField(_("作成日時"), auto_now_add=True)
    updated_at = models.DateTimeField(_("更新日時"), auto_now=True)

    tags = models.ManyToManyField(
        "Tag",
        through="BonsaiTag",
        related_name="bonsai_plants",
        blank=True,
        verbose_name=_("タグ"),
    )

    class Meta:
        verbose_name = _("盆栽")
        verbose_name_plural = _("盆栽")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["health_status"]),
        ]

    def __str__(self) -> str:
        return self.name


# ---------------------------------------------------------------------------
# タグ
# ---------------------------------------------------------------------------
class Tag(models.Model):
    """ユーザーごとに自由に作れるタグ。"""

    id = models.CharField(
        primary_key=True,
        max_length=36,
        default=uuid7_str,
        editable=False,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bonsai_tags",
        verbose_name=_("所有者"),
    )
    name = models.CharField(_("タグ名"), max_length=32)
    color = models.CharField(
        _("カラー"),
        max_length=16,
        blank=True,
        help_text=_("Hex カラー（例: #4CAF50）"),
    )
    created_at = models.DateTimeField(_("作成日時"), auto_now_add=True)

    class Meta:
        verbose_name = _("タグ")
        verbose_name_plural = _("タグ")
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["user", "name"], name="uniq_tag_user_name"),
        ]

    def __str__(self) -> str:
        return self.name


class BonsaiTag(models.Model):
    """盆栽 ↔ タグ の中間表（明示）。"""

    id = models.CharField(
        primary_key=True,
        max_length=36,
        default=uuid7_str,
        editable=False,
    )
    bonsai = models.ForeignKey(
        BonsaiPlant,
        on_delete=models.CASCADE,
        related_name="tag_links",
        verbose_name=_("盆栽"),
    )
    tag = models.ForeignKey(
        Tag,
        on_delete=models.CASCADE,
        related_name="bonsai_links",
        verbose_name=_("タグ"),
    )
    created_at = models.DateTimeField(_("作成日時"), auto_now_add=True)

    class Meta:
        verbose_name = _("盆栽タグ")
        verbose_name_plural = _("盆栽タグ")
        constraints = [
            models.UniqueConstraint(fields=["bonsai", "tag"], name="uniq_bonsaitag_pair"),
        ]

    def __str__(self) -> str:
        return f"{self.bonsai_id}:{self.tag_id}"


# ---------------------------------------------------------------------------
# 画像
# ---------------------------------------------------------------------------
class BonsaiMedia(models.Model):
    """盆栽の写真（元 / 中 / サムネ の 3 段）。"""

    id = models.CharField(
        primary_key=True,
        max_length=36,
        default=uuid7_str,
        editable=False,
    )
    bonsai = models.ForeignKey(
        BonsaiPlant,
        on_delete=models.CASCADE,
        related_name="media",
        verbose_name=_("盆栽"),
    )
    image_original = models.ImageField(
        _("元画像"),
        upload_to="bonsai/original/%Y/%m/",
        help_text=_("長辺 2048px を超える場合はサーバ側でリサイズして保存"),
    )
    image_medium = models.ImageField(
        _("中サイズ画像"),
        upload_to="bonsai/medium/%Y/%m/",
        blank=True,
    )
    image_thumbnail = models.ImageField(
        _("サムネイル画像"),
        upload_to="bonsai/thumb/%Y/%m/",
        blank=True,
    )
    taken_at = models.DateField(_("撮影日"), null=True, blank=True)
    caption = models.CharField(_("キャプション"), max_length=200, blank=True)
    created_at = models.DateTimeField(_("作成日時"), auto_now_add=True)

    class Meta:
        verbose_name = _("盆栽画像")
        verbose_name_plural = _("盆栽画像")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["bonsai", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.bonsai_id} / {self.created_at:%Y-%m-%d}" if self.created_at else str(self.id)

    # ------------------------------------------------------------------
    # 保存時に派生画像を生成する
    # ------------------------------------------------------------------
    def save(self, *args: object, **kwargs: object) -> None:
        """新規アップロード時に中サイズ・サムネイルを同期生成する。

        - 元画像が長辺 2048px を超える場合は元ファイルもリサイズして差し替える
        - フォーマットは JPEG に統一（透明背景は白で合成）
        - EXIF の向き情報を考慮（`Image.exif_transpose`）
        """
        from .services.images import generate_variants  # 循環回避のため遅延 import

        is_new = self._state.adding
        if is_new and self.image_original:
            medium_file, thumb_file = generate_variants(self.image_original)
            if medium_file is not None:
                self.image_medium.save(medium_file.name, medium_file, save=False)
            if thumb_file is not None:
                self.image_thumbnail.save(thumb_file.name, thumb_file, save=False)

        super().save(*args, **kwargs)
