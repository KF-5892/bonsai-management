"""お役立ち記事（HelpArticle）モデル。

決定事項（docs/開発前検討事項.md, docs/技術要件書.md）:
- お役立ち記事は MVP 必須機能。運営（P7）が編集、一般ユーザー（P1～P6）は閲覧のみ。
- 主キーは UUIDv7（`apps.common.utils.uuid7_str`）。
- 本文は Markdown（レンダリングはビュー側で `markdown` パッケージを使う想定）。
- 公開ステータスは draft / published。
- 記事と品種は多対多。中間表 `ArticleSpeciesRelation` に関連度スコアを持たせ、
  品種詳細ページなどで関連記事を並び替え可能にする。

NOTE: `bonsai.BonsaiSpecies` は別チームが実装中。FK は文字列参照で解決する。
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.utils import uuid7_str


class ArticleStatus(models.TextChoices):
    """お役立ち記事の公開ステータス。"""

    DRAFT = "draft", _("下書き")
    PUBLISHED = "published", _("公開")


class HelpArticle(models.Model):
    """お役立ち記事本体。"""

    id = models.CharField(
        primary_key=True,
        max_length=36,
        default=uuid7_str,
        editable=False,
    )
    title = models.CharField(_("タイトル"), max_length=200)
    slug = models.SlugField(_("スラッグ"), max_length=200, unique=True)
    body = models.TextField(_("本文（Markdown）"))
    summary = models.CharField(_("概要"), max_length=300, blank=True)
    cover_image = models.ImageField(
        _("カバー画像"),
        upload_to="articles/cover/%Y/%m/",
        blank=True,
    )
    status = models.CharField(
        _("公開ステータス"),
        max_length=16,
        choices=ArticleStatus.choices,
        default=ArticleStatus.DRAFT,
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="articles",
        verbose_name=_("執筆者"),
    )
    related_species = models.ManyToManyField(
        "bonsai.BonsaiSpecies",
        through="ArticleSpeciesRelation",
        related_name="articles",
        blank=True,
        verbose_name=_("関連品種"),
    )
    published_at = models.DateTimeField(_("公開日時"), null=True, blank=True)
    created_at = models.DateTimeField(_("作成日時"), auto_now_add=True)
    updated_at = models.DateTimeField(_("更新日時"), auto_now=True)

    class Meta:
        verbose_name = _("お役立ち記事")
        verbose_name_plural = _("お役立ち記事")
        ordering = ("-published_at", "-created_at")
        indexes = (
            models.Index(fields=("status",), name="article_status_idx"),
            models.Index(fields=("slug",), name="article_slug_idx"),
        )

    def __str__(self) -> str:
        return self.title

    @property
    def is_published(self) -> bool:
        """公開ステータスかつ公開日時が現在以前の場合に True。"""
        if self.status != ArticleStatus.PUBLISHED:
            return False
        if self.published_at is None:
            return False
        return self.published_at <= timezone.now()


class ArticleSpeciesRelation(models.Model):
    """記事と品種を結ぶ中間表。

    `relevance` は関連度スコア（任意）。同一品種に紐づく記事一覧を
    並び替えるときに利用する想定。
    """

    id = models.CharField(
        primary_key=True,
        max_length=36,
        default=uuid7_str,
        editable=False,
    )
    article = models.ForeignKey(
        HelpArticle,
        on_delete=models.CASCADE,
        related_name="species_relations",
        verbose_name=_("お役立ち記事"),
    )
    species = models.ForeignKey(
        "bonsai.BonsaiSpecies",
        on_delete=models.CASCADE,
        related_name="article_relations",
        verbose_name=_("品種"),
    )
    relevance = models.PositiveSmallIntegerField(_("関連度スコア"), default=0)
    created_at = models.DateTimeField(_("作成日時"), auto_now_add=True)

    class Meta:
        verbose_name = _("記事-品種関連")
        verbose_name_plural = _("記事-品種関連")
        unique_together = (("article", "species"),)
        ordering = ("-relevance", "-created_at")

    def __str__(self) -> str:
        return f"{self.article_id} <-> {self.species_id} (rel={self.relevance})"
