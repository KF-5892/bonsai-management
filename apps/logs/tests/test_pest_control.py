"""消毒の記録（目的・薬剤・希釈倍率など）と薬剤マスタのテスト。"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.bonsai.models import BonsaiPlant
from apps.logs.models import CareLog, Pesticide


@pytest.fixture
def plant(user, bonsai_species):
    return BonsaiPlant.objects.create(user=user, species=bonsai_species, name="一郎")


@pytest.fixture
def pesticides(user):
    return [
        Pesticide.objects.create(user=user, name="殺虫剤A", category="insecticide"),
        Pesticide.objects.create(user=user, name="殺菌剤B", category="fungicide"),
    ]


def _pest_control_data(plant, pesticides, **overrides):
    data = {
        "bonsai": str(plant.pk),
        "task_type": ["pest_control"],
        "performed_at": "2026-05-15T09:00",
        "pest_control_purposes": ["insecticide", "fungicide"],
        "pesticides": [p.pk for p in pesticides],
        "pesticide_dilution": "1000倍",
        "spreader_used": "on",
        "pest_target": "アブラムシ",
    }
    data.update(overrides)
    return data


def test_pest_control_details_are_saved_and_shown(client, user, plant, pesticides):
    client.force_login(user)
    res = client.post(reverse("logs:create"), _pest_control_data(plant, pesticides))
    assert res.status_code == 302, getattr(res, "context", None)

    log = CareLog.objects.get(user=user)
    assert log.pest_control_purposes == ["insecticide", "fungicide"]
    assert log.pest_control_purpose_label == "殺虫・殺菌"
    assert log.pesticide_names == "殺菌剤B、殺虫剤A"
    assert log.pesticide_dilution == "1000倍"
    assert log.spreader_used is True

    html = client.get(reverse("logs:detail", kwargs={"pk": log.pk})).content.decode()
    for text in ("殺虫・殺菌", "殺菌剤B、殺虫剤A", "1000倍", "展着剤", "アブラムシ"):
        assert text in html

    body = client.get(reverse("logs:export")).content.decode("utf-8-sig")
    assert "消毒の目的" in body
    assert "殺菌剤B、殺虫剤A" in body


def test_pest_control_details_are_dropped_without_pest_control(client, user, plant, pesticides):
    """消毒を選んでいなければ、付帯項目が送られてきても保存しない。"""
    client.force_login(user)
    res = client.post(
        reverse("logs:create"), _pest_control_data(plant, pesticides, task_type=["watering"])
    )
    assert res.status_code == 302, getattr(res, "context", None)
    log = CareLog.objects.get(user=user)
    assert not log.has_pest_control_details
    assert log.pesticides.count() == 0


def test_edit_keeps_and_clears_pest_control_details(client, user, plant, pesticides):
    client.force_login(user)
    client.post(reverse("logs:create"), _pest_control_data(plant, pesticides))
    log = CareLog.objects.get(user=user)
    edit_url = reverse("logs:edit", kwargs={"pk": log.pk})

    form = client.get(edit_url).context["form"]
    assert form["pest_control_purposes"].value() == ["insecticide", "fungicide"]
    assert {str(v) for v in form["pesticides"].value()} == {p.pk for p in pesticides}

    res = client.post(edit_url, _pest_control_data(plant, pesticides, task_type=["pruning"]))
    assert res.status_code == 302, getattr(res, "context", None)
    log.refresh_from_db()
    assert not log.has_pest_control_details


def test_other_users_pesticide_cannot_be_selected(client, user, plant):
    other = get_user_model().objects.create_user(email="other@example.com", password="x")
    theirs = Pesticide.objects.create(user=other, name="他人の薬剤")
    common = Pesticide.objects.create(name="共通の薬剤")
    client.force_login(user)

    res = client.post(reverse("logs:create"), _pest_control_data(plant, [theirs]))
    assert res.status_code == 200
    assert not CareLog.objects.exists()

    res = client.post(reverse("logs:create"), _pest_control_data(plant, [common]))
    assert res.status_code == 302


def test_bulk_create_records_pest_control_details(client, user, bonsai_species, pesticides):
    plants = [
        BonsaiPlant.objects.create(user=user, species=bonsai_species, name=name)
        for name in ("一郎", "二郎")
    ]
    client.force_login(user)
    data = _pest_control_data(plants[0], pesticides, pest_control_purposes=["dormant"])
    data["bonsai"] = [p.pk for p in plants]
    res = client.post(reverse("logs:bulk_create"), data)
    assert res.status_code == 302, getattr(res, "context", None)

    logs = list(CareLog.objects.filter(user=user))
    assert len(logs) == 2
    for log in logs:
        assert log.pest_control_purpose_label == "冬季消毒"
        assert log.pesticide_names == "殺菌剤B、殺虫剤A"
        assert log.spreader_used is True


def test_pesticide_crud_flow(client, user):
    client.force_login(user)
    res = client.post(
        reverse("logs:pesticide_create"),
        {
            "name": "石灰硫黄合剤",
            "category": "dormant",
            "formulation": "liquid",
            "default_dilution": "20倍",
            "note": "",
        },
    )
    assert res.status_code == 302
    pesticide = Pesticide.objects.get(user=user, name="石灰硫黄合剤")

    html = client.get(reverse("logs:pesticide_list")).content.decode()
    assert "石灰硫黄合剤" in html
    assert "20倍" in html

    res = client.post(
        reverse("logs:pesticide_edit", kwargs={"pk": pesticide.pk}),
        {"name": "石灰硫黄合剤（冬用）", "category": "dormant", "formulation": "", "note": ""},
    )
    assert res.status_code == 302
    pesticide.refresh_from_db()
    assert pesticide.name == "石灰硫黄合剤（冬用）"

    res = client.post(reverse("logs:pesticide_delete", kwargs={"pk": pesticide.pk}))
    assert res.status_code == 302
    assert not Pesticide.objects.filter(pk=pesticide.pk).exists()


def test_common_pesticide_is_listed_but_not_editable(client, user):
    common = Pesticide.objects.create(name="共通薬剤")
    client.force_login(user)
    assert "共通薬剤" in client.get(reverse("logs:pesticide_list")).content.decode()
    res = client.get(reverse("logs:pesticide_edit", kwargs={"pk": common.pk}))
    assert res.status_code == 404
