"""articles アプリのビュー最小スモークテスト。"""

from __future__ import annotations

from django.urls import reverse
from django.utils import timezone

from apps.articles.models import ArticleStatus, HelpArticle


def test_article_list_is_public(client):
    res = client.get(reverse("articles:list"))
    assert res.status_code == 200


def test_article_detail_renders_markdown(client, user):
    article = HelpArticle.objects.create(
        title="盆栽の水やり",
        slug="watering-basics",
        body="# 見出し\n\n本文です。",
        status=ArticleStatus.PUBLISHED,
        author=user,
        published_at=timezone.now(),
    )
    res = client.get(reverse("articles:detail", kwargs={"slug": article.slug}))
    assert res.status_code == 200
    body_html = res.context["body_html"]
    assert "<h1>" in body_html


# ---------------------------------------------------------------------------
# カテゴリ / 特集 / 関連（サブカテゴリ統合後）
# ---------------------------------------------------------------------------
def test_list_filters_by_category(client, user):
    from django.utils import timezone

    from apps.articles.models import ArticleCategory, ArticleStatus, HelpArticle

    now = timezone.now()
    HelpArticle.objects.create(
        title="剪定のコツ",
        slug="pruning",
        body="本文",
        author=user,
        category=ArticleCategory.TIPS,
        status=ArticleStatus.PUBLISHED,
        published_at=now,
    )
    HelpArticle.objects.create(
        title="アブラムシ対策",
        slug="aphid",
        body="本文",
        author=user,
        category=ArticleCategory.PEST,
        status=ArticleStatus.PUBLISHED,
        published_at=now,
    )

    res = client.get(reverse("articles:list"))
    assert len(res.context["articles"]) == 2

    res = client.get(reverse("articles:list"), {"category": "pest"})
    assert [a.title for a in res.context["articles"]] == ["アブラムシ対策"]

    # 未知のカテゴリは無視して全件表示にフォールバックする
    res = client.get(reverse("articles:list"), {"category": "unknown"})
    assert len(res.context["articles"]) == 2


def test_detail_shows_my_related_plants(client, user, bonsai_species):
    from django.utils import timezone

    from apps.articles.models import ArticleStatus, HelpArticle
    from apps.bonsai.models import BonsaiPlant

    article = HelpArticle.objects.create(
        title="黒松の管理",
        slug="kuromatsu-care",
        body="本文",
        author=user,
        status=ArticleStatus.PUBLISHED,
        published_at=timezone.now(),
    )
    article.related_species.add(bonsai_species)
    plant = BonsaiPlant.objects.create(user=user, species=bonsai_species, name="黒松 太郎")

    client.force_login(user)
    res = client.get(reverse("articles:detail", kwargs={"slug": article.slug}))
    assert list(res.context["my_related_plants"]) == [plant]
