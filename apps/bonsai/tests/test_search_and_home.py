"""グローバル検索とホーム改修（期間切替 / 表示切替 / 最近の活動）のテスト。"""

from __future__ import annotations

from datetime import date, timedelta

from django.urls import reverse
from django.utils import timezone

from apps.articles.models import ArticleStatus, HelpArticle
from apps.bonsai.models import BonsaiPlant, BonsaiSpecies, SpeciesCategory, Tag
from apps.logs.models import CareLog
from apps.schedules.models import CareSchedule, RepeatType


def test_search_requires_login(client):
    res = client.get(reverse("search"))
    assert res.status_code == 302


def test_search_finds_plants_logs_and_articles(client, user, bonsai_species):
    plant = BonsaiPlant.objects.create(user=user, species=bonsai_species, name="黒松 太郎")
    CareLog.objects.create(user=user, bonsai=plant, task_type="watering", notes="黒松に水やり")
    HelpArticle.objects.create(
        title="黒松の育て方",
        slug="kuromatsu",
        body="本文",
        status=ArticleStatus.PUBLISHED,
        author=user,
    )
    client.force_login(user)

    res = client.get(reverse("search"), {"q": "黒松"})
    assert res.status_code == 200
    assert [p.name for p in res.context["plants"]] == ["黒松 太郎"]
    assert len(res.context["logs"]) == 1
    assert len(res.context["articles"]) == 1
    # 品種マスタ「テスト黒松」も横断検索の対象になる
    assert [s.name for s in res.context["species_list"]] == ["テスト黒松"]
    assert res.context["total_count"] == 4


def test_search_excludes_other_users_data(client, user, other_user, bonsai_species):
    BonsaiPlant.objects.create(user=other_user, species=bonsai_species, name="他人の黒松")
    client.force_login(user)
    res = client.get(reverse("search"), {"q": "黒松"})
    assert res.context["plants"] == []


def test_home_week_range_filters_todos(client, user, bonsai_species):
    """今週切替では、期間に重なるスケジュールだけが残る。"""
    plant = BonsaiPlant.objects.create(user=user, species=bonsai_species, name="黒松 太郎")
    today = timezone.localdate()
    monday = today - timedelta(days=today.weekday())
    in_week = monday + timedelta(days=1)
    # 同月内で今週から外れる日を選ぶ
    out_of_week = date(today.year, today.month, 28 if monday.day < 15 else 1)

    CareSchedule.objects.create(
        user=user,
        bonsai=plant,
        task_type="watering",
        title="今週の作業",
        repeat_type=RepeatType.NONE,
        start_date=in_week,
        next_run_at=in_week,
    )
    CareSchedule.objects.create(
        user=user,
        bonsai=plant,
        task_type="watering",
        title="週外の作業",
        repeat_type=RepeatType.NONE,
        start_date=out_of_week,
        next_run_at=out_of_week,
    )
    client.force_login(user)

    res = client.get(reverse("bonsai:home"), {"range": "week"})
    titles = [t.title for t in res.context["todos"]]
    assert "今週の作業" in titles
    assert "週外の作業" not in titles
    assert res.context["range_mode"] == "week"


def test_home_custom_range(client, user, bonsai_species):
    plant = BonsaiPlant.objects.create(user=user, species=bonsai_species, name="黒松 太郎")
    CareSchedule.objects.create(
        user=user,
        bonsai=plant,
        task_type="watering",
        title="4/15 の作業",
        repeat_type=RepeatType.NONE,
        start_date=date(2026, 4, 15),
        next_run_at=date(2026, 4, 15),
    )
    client.force_login(user)

    res = client.get(
        reverse("bonsai:home"), {"range": "custom", "from": "2026-04-14", "to": "2026-04-16"}
    )
    assert [t.title for t in res.context["todos"]] == ["4/15 の作業"]

    res = client.get(
        reverse("bonsai:home"), {"range": "custom", "from": "2026-04-01", "to": "2026-04-05"}
    )
    assert res.context["todos"] == []


def test_home_group_by_species_and_tag(client, user):
    conifer = BonsaiSpecies.objects.create(
        slug="kuromatsu", name="黒松", category=SpeciesCategory.CONIFER
    )
    broadleaf = BonsaiSpecies.objects.create(
        slug="kaede", name="楓", category=SpeciesCategory.BROADLEAF
    )
    pine = BonsaiPlant.objects.create(user=user, species=conifer, name="黒松 太郎")
    BonsaiPlant.objects.create(user=user, species=broadleaf, name="楓 花子")
    tag = Tag.objects.create(user=user, name="ベランダ")
    pine.tags.add(tag)
    client.force_login(user)

    res = client.get(reverse("bonsai:home"), {"view": "species"})
    groups = {name: [p.name for p in plants] for name, plants in res.context["plant_groups"]}
    assert groups == {"黒松": ["黒松 太郎"], "楓": ["楓 花子"]}

    res = client.get(reverse("bonsai:home"), {"view": "tag"})
    groups = {name: [p.name for p in plants] for name, plants in res.context["plant_groups"]}
    assert groups == {"ベランダ": ["黒松 太郎"], "タグなし": ["楓 花子"]}

    # 既定はカード表示（単一グループ）
    res = client.get(reverse("bonsai:home"))
    assert res.context["view_mode"] == "card"
    assert len(res.context["plant_groups"]) == 1


def test_home_shows_recent_activities(client, user, bonsai_species):
    plant = BonsaiPlant.objects.create(user=user, species=bonsai_species, name="黒松 太郎")
    CareLog.objects.create(user=user, bonsai=plant, task_type="watering", notes="水やり")
    client.force_login(user)
    res = client.get(reverse("bonsai:home"))
    assert len(res.context["recent_activities"]) == 1
    assert "最近の活動" in res.content.decode()
