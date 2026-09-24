"""作業ログの絞り込み / CSV エクスポート / クイック記録のテスト。"""

from __future__ import annotations

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from apps.bonsai.models import BonsaiPlant
from apps.logs.models import CareLog


def _plants(user, species):
    pine = BonsaiPlant.objects.create(user=user, species=species, name="黒松 太郎")
    maple = BonsaiPlant.objects.create(user=user, species=species, name="楓 花子")
    return pine, maple


def test_list_filters_by_bonsai_task_type_and_period(client, user, bonsai_species):
    pine, maple = _plants(user, bonsai_species)
    now = timezone.now()
    CareLog.objects.create(user=user, bonsai=pine, task_type="watering", performed_at=now)
    CareLog.objects.create(
        user=user, bonsai=maple, task_type="fertilizing", performed_at=now - timedelta(days=10)
    )
    client.force_login(user)

    res = client.get(reverse("logs:list"), {"bonsai": pine.pk})
    assert [log.bonsai_id for log in res.context["logs"]] == [pine.pk]
    assert res.context["selected_plant"] == pine

    res = client.get(reverse("logs:list"), {"task_type": "fertilizing"})
    assert [log.task_type for log in res.context["logs"]] == ["fertilizing"]

    today = timezone.localdate()
    res = client.get(
        reverse("logs:list"),
        {"from": (today - timedelta(days=1)).isoformat(), "to": today.isoformat()},
    )
    assert [log.task_type for log in res.context["logs"]] == ["watering"]
    assert res.context["is_filtered"] is True


def test_export_csv_respects_filters(client, user, bonsai_species):
    pine, maple = _plants(user, bonsai_species)
    CareLog.objects.create(user=user, bonsai=pine, task_type="watering", notes="朝の潅水")
    CareLog.objects.create(user=user, bonsai=maple, task_type="pruning", notes="剪定")
    client.force_login(user)

    res = client.get(reverse("logs:export"), {"bonsai": pine.pk})
    assert res.status_code == 200
    assert res["Content-Type"].startswith("text/csv")
    body = res.content.decode("utf-8-sig")
    assert "実施日時" in body
    assert "朝の潅水" in body
    assert "剪定" not in body


def test_quick_log_creates_entry_and_redirects_back(client, user, bonsai_species):
    pine, _maple = _plants(user, bonsai_species)
    client.force_login(user)
    detail_url = reverse("bonsai:detail", kwargs={"pk": pine.pk}) + "?tab=logs"

    res = client.post(
        reverse("logs:quick_create"),
        {"bonsai": pine.pk, "task_type": "watering", "next": detail_url},
    )
    assert res.status_code == 302
    assert res["Location"] == detail_url
    log = CareLog.objects.get(user=user, bonsai=pine)
    assert log.task_type == "watering"
    assert timezone.now() - log.performed_at < timedelta(minutes=1)


def test_quick_log_rejects_unsupported_task_and_foreign_plant(
    client, user, other_user, bonsai_species
):
    pine, _maple = _plants(user, bonsai_species)
    theirs = BonsaiPlant.objects.create(user=other_user, species=bonsai_species, name="他人の")
    client.force_login(user)

    res = client.post(reverse("logs:quick_create"), {"bonsai": pine.pk, "task_type": "repotting"})
    assert res.status_code == 400

    res = client.post(reverse("logs:quick_create"), {"bonsai": theirs.pk, "task_type": "watering"})
    assert res.status_code == 404
    assert CareLog.objects.count() == 0


def test_quick_log_ignores_external_next(client, user, bonsai_species):
    pine, _maple = _plants(user, bonsai_species)
    client.force_login(user)
    res = client.post(
        reverse("logs:quick_create"),
        {"bonsai": pine.pk, "task_type": "observation", "next": "https://evil.example/"},
    )
    assert res.status_code == 302
    assert res["Location"] == reverse("bonsai:detail", kwargs={"pk": pine.pk})


def test_bulk_form_groups_plants_by_species_and_preselects(client, user, bonsai_species):
    pine, _maple = _plants(user, bonsai_species)
    client.force_login(user)
    res = client.get(reverse("logs:bulk_create"), {"bonsai": [pine.pk]})
    assert res.status_code == 200
    groups = dict(res.context["plant_groups"])
    assert set(groups) == {bonsai_species.name}
    assert res.context["selected_ids"] == {str(pine.pk)}
    assert res.context["plant_count"] == 2
    html = res.content.decode()
    assert "すべて選択" in html
    assert f'value="{pine.pk}" id="bonsai_{pine.pk}"' in html
