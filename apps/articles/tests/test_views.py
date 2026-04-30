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
