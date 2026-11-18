"""「見ごろ」の仕様テスト。

- 見ごろは ToDo に含めない（品種マスタの ``observation`` も除く）
- ``viewing_seasons`` は旬単位の範囲（関東〜九州の平野部基準）で、月をまたげる
- ユーザーの地域（気候区分）と微調整に合わせて旬単位でずらす
- 既定は保有品種のみ、``owned_only=False`` で未保有の品種も返す
- ホームは ``?viewing=owned|all`` で切り替える
"""

from __future__ import annotations

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.bonsai.models import BonsaiPlant, BonsaiSpecies
from apps.common.regions import ClimateAdjust, ClimateZone, Region, viewing_offset, zone_for_region
from apps.schedules.models import CareSchedule, TaskType
from apps.schedules.services import (
    compose_monthly_todos,
    compose_viewing_seasons,
    format_jun_range,
    shifted_viewing_range,
)

User = get_user_model()

APRIL = date(2026, 4, 1)


def season(kind, start_month, start_period, end_month, end_period, **extra):
    return {
        "kind": kind,
        "start_month": start_month,
        "start_period": start_period,
        "end_month": end_month,
        "end_period": end_period,
        "description": "説明",
        **extra,
    }


@pytest.fixture
def owner(db):
    return User.objects.create_user(email="viewer@example.com", password="pw12345!")


@pytest.fixture
def sakura(db):
    return BonsaiSpecies.objects.create(
        slug="sakura-test",
        name="桜",
        monthly_tasks=[
            {"month": 4, "period": "上旬", "task_type": "observation", "description": "開花期。"},
            {"month": 4, "period": "下旬", "task_type": "pruning", "description": "花後の剪定。"},
        ],
        viewing_seasons=[season("flower", 3, "下旬", 4, "上旬")],
    )


@pytest.fixture
def ume(db):
    return BonsaiSpecies.objects.create(
        slug="ume-test",
        name="梅",
        viewing_seasons=[season("flower", 1, "下旬", 3, "上旬", shift="winter")],
    )


@pytest.fixture
def kaede(db):
    return BonsaiSpecies.objects.create(
        slug="kaede-test",
        name="楓",
        viewing_seasons=[season("foliage", 11, "下旬", 12, "上旬")],
    )


@pytest.fixture
def sakura_plant(db, owner, sakura):
    return BonsaiPlant.objects.create(user=owner, species=sakura, name="桜 一号")


def names(user, year_month, **kwargs):
    return [s.species_name for s in compose_viewing_seasons(user, year_month, **kwargs)]


# ---------------------------------------------------------------------------
# ToDo との分離
# ---------------------------------------------------------------------------
def test_viewing_task_is_not_a_todo(owner, sakura_plant):
    todos = compose_monthly_todos(owner, APRIL)
    assert [t.task_type for t in todos] == ["pruning"]


def test_user_observation_schedule_stays_a_todo(owner, sakura_plant):
    """自分で登録した「観察」スケジュールは作業なので ToDo に残る。"""
    CareSchedule.objects.create(
        bonsai=sakura_plant,
        user=owner,
        task_type=TaskType.OBSERVATION,
        title="毎週の観察",
        start_date=date(2026, 4, 1),
        next_run_at=date(2026, 4, 12),
        is_active=True,
    )
    assert "毎週の観察" in [t.title for t in compose_monthly_todos(owner, APRIL)]


# ---------------------------------------------------------------------------
# 旬の範囲
# ---------------------------------------------------------------------------
def test_jun_range_labels():
    assert format_jun_range(2, 6) == "1月下旬〜3月上旬"
    assert format_jun_range(10, 10) == "4月中旬"
    # 年をまたぐ範囲（12月上旬〜2月下旬）
    assert format_jun_range(33, 5) == "12月上旬〜2月下旬"


def test_shifted_range_rejects_broken_entries():
    assert shifted_viewing_range("x") is None
    assert shifted_viewing_range(season("flower", 13, "上旬", 1, "上旬")) is None
    assert shifted_viewing_range(season("flower", 3, "初旬", 4, "上旬")) is None


def test_season_spans_months(owner, sakura_plant, ume):
    """月をまたぐ見ごろは、重なるすべての月に出る。"""
    BonsaiPlant.objects.create(user=owner, species=ume, name="梅 一号")
    assert names(owner, date(2026, 1, 1)) == ["梅"]
    assert names(owner, date(2026, 2, 1)) == ["梅"]
    assert names(owner, date(2026, 3, 1)) == ["梅", "桜"]  # 梅は上旬まで、桜は下旬から
    assert names(owner, APRIL) == ["桜"]
    assert names(owner, date(2026, 5, 1)) == []
    seasons = compose_viewing_seasons(owner, date(2026, 3, 1))
    assert [(s.kind_label, s.period_label) for s in seasons] == [
        ("花", "1月下旬〜3月上旬"),
        ("花", "3月下旬〜4月上旬"),
    ]


def test_year_wrapping_season(owner):
    roubai = BonsaiSpecies.objects.create(
        slug="roubai-test",
        name="蝋梅",
        viewing_seasons=[season("flower", 12, "上旬", 2, "下旬", shift="none")],
    )
    BonsaiPlant.objects.create(user=owner, species=roubai, name="蝋梅 一号")
    assert names(owner, date(2026, 12, 1)) == ["蝋梅"]
    assert names(owner, date(2026, 1, 1)) == ["蝋梅"]
    assert names(owner, date(2026, 3, 1)) == []
    assert names(owner, date(2026, 11, 1)) == []


# ---------------------------------------------------------------------------
# 地域（気候区分）による補正
# ---------------------------------------------------------------------------
def test_region_zone_mapping():
    assert zone_for_region("") == ClimateZone.STANDARD
    assert zone_for_region("unknown") == ClimateZone.STANDARD
    assert zone_for_region(Region.TOKYO) == ClimateZone.STANDARD
    assert zone_for_region(Region.AOMORI) == ClimateZone.TOHOKU_NORTH
    assert zone_for_region(Region.HOKKAIDO_NE) == ClimateZone.HOKKAIDO_NE
    # すべての地域がいずれかの区分に対応する
    assert all(zone_for_region(value) in ClimateZone for value in Region.values)


def test_offsets_move_spring_later_and_autumn_earlier():
    assert viewing_offset(ClimateZone.STANDARD, "spring") == 0
    assert viewing_offset(ClimateZone.HOKKAIDO_SW, "spring") == 4
    assert viewing_offset(ClimateZone.HOKKAIDO_SW, "autumn") == -3
    assert viewing_offset(ClimateZone.HOKKAIDO_SW, "winter") == 10
    assert viewing_offset(ClimateZone.HOKKAIDO_SW, "none") == 0
    # 寒い場所の微調整は、春を遅く・秋を早くする
    assert viewing_offset(ClimateZone.STANDARD, "spring", ClimateAdjust.COLDER) == 1
    assert viewing_offset(ClimateZone.STANDARD, "autumn", ClimateAdjust.COLDER) == -1
    assert viewing_offset(ClimateZone.STANDARD, "none", ClimateAdjust.COLDER) == 0


def test_region_shifts_sakura_later(owner, sakura_plant):
    owner.region = Region.HOKKAIDO_SW
    owner.save()
    assert names(owner, APRIL) == []
    seasons = compose_viewing_seasons(owner, date(2026, 5, 1))
    assert [s.period_label for s in seasons] == ["5月上旬〜5月中旬"]


def test_region_shifts_foliage_earlier(owner, kaede):
    BonsaiPlant.objects.create(user=owner, species=kaede, name="楓 一号")
    assert names(owner, date(2026, 10, 1)) == []
    owner.region = Region.HOKKAIDO_SW
    owner.save()
    seasons = compose_viewing_seasons(owner, date(2026, 10, 1))
    assert [s.period_label for s in seasons] == ["10月下旬〜11月上旬"]


def test_climate_adjust_is_applied(owner, sakura_plant):
    owner.climate_adjust = ClimateAdjust.COLDER
    owner.save()
    seasons = compose_viewing_seasons(owner, APRIL)
    assert [s.period_label for s in seasons] == ["4月上旬〜4月中旬"]


def test_okinawa_has_no_viewing_seasons(owner, sakura_plant):
    owner.region = Region.OKINAWA
    owner.save()
    assert compose_viewing_seasons(owner, APRIL) == []
    assert compose_viewing_seasons(owner, APRIL, owned_only=False) == []


# ---------------------------------------------------------------------------
# 保有品種のみ / すべての品種
# ---------------------------------------------------------------------------
def test_viewing_seasons_default_to_owned_species(owner, sakura_plant, ume):
    seasons = compose_viewing_seasons(owner, date(2026, 3, 1))
    assert [s.species_name for s in seasons] == ["桜"]
    assert seasons[0].is_owned
    assert [p.name for p in seasons[0].plants] == ["桜 一号"]


def test_viewing_seasons_all_lists_owned_first(owner, sakura_plant, ume):
    seasons = compose_viewing_seasons(owner, date(2026, 3, 1), owned_only=False)
    assert [(s.species_name, s.is_owned) for s in seasons] == [("桜", True), ("梅", False)]


def test_viewing_seasons_ignore_other_users_plants(owner, sakura):
    other = User.objects.create_user(email="other-viewer@example.com", password="pw12345!")
    BonsaiPlant.objects.create(user=other, species=sakura, name="他人の桜")
    assert compose_viewing_seasons(owner, APRIL) == []
    assert all(not s.is_owned for s in compose_viewing_seasons(owner, APRIL, owned_only=False))


# ---------------------------------------------------------------------------
# 画面
# ---------------------------------------------------------------------------
def test_home_viewing_filter(client, owner, sakura_plant, ume, monkeypatch):
    monkeypatch.setattr("apps.bonsai.views.timezone.localdate", lambda: date(2026, 3, 5))
    client.force_login(owner)

    res = client.get(reverse("bonsai:home"))
    assert res.context["viewing_scope"] == "owned"
    assert [s.species_name for s in res.context["viewing_seasons"]] == ["桜"]
    html = res.content.decode()
    assert "3月の見ごろ" in html
    assert "保有品種のみ" in html and "すべての品種" in html
    assert "3月下旬〜4月上旬" in html
    assert "関東〜九州の平野部を基準にした目安です" in html

    res = client.get(reverse("bonsai:home"), {"viewing": "all", "range": "week"})
    assert res.context["viewing_scope"] == "all"
    assert [s.species_name for s in res.context["viewing_seasons"]] == ["桜", "梅"]
    # 切替リンクはほかの絞り込み（期間）を保ち、期間リンクは見ごろの切替を保つ
    assert res.context["viewing_owned_url"].startswith("?range=week")
    assert "?range=month&amp;viewing=all" in res.content.decode()

    # 不正な値は既定（保有品種のみ）に倒す
    res = client.get(reverse("bonsai:home"), {"viewing": "bogus"})
    assert res.context["viewing_scope"] == "owned"


def test_home_shows_region_basis(client, owner, sakura_plant):
    owner.region = Region.AOMORI
    owner.save()
    client.force_login(owner)
    html = client.get(reverse("bonsai:home")).content.decode()
    assert "東北北部の目安です" in html


def test_profile_form_saves_region(client, owner):
    client.force_login(owner)
    res = client.post(
        reverse("accounts:profile"),
        {
            "display_name": "見る人",
            "language": "ja",
            "region": Region.NAGANO,
            "climate_adjust": ClimateAdjust.COLDER,
        },
    )
    assert res.status_code == 302
    owner.refresh_from_db()
    assert (owner.region, owner.climate_adjust) == (Region.NAGANO, ClimateAdjust.COLDER)


def test_species_detail_shows_base_viewing_season(client, ume):
    html = client.get(reverse("bonsai:species_detail", kwargs={"slug": ume.slug})).content.decode()
    assert "1月下旬〜3月上旬" in html


def test_seed_viewing_seasons_are_valid():
    """シードの見ごろはすべて旬の範囲として読める。"""
    import json
    from pathlib import Path

    from django.conf import settings

    seed = Path(settings.BASE_DIR) / "apps/bonsai/fixtures/bonsai_species_seed.json"
    entries = [
        (obj["fields"]["slug"], entry)
        for obj in json.loads(seed.read_text())
        for entry in obj["fields"]["viewing_seasons"]
    ]
    assert len(entries) >= 10
    for slug, entry in entries:
        assert shifted_viewing_range(entry) is not None, slug
        assert entry["kind"] in {"flower", "foliage", "fruit"}, slug
