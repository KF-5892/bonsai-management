"""logs アプリのビュー最小スモークテスト。"""

from __future__ import annotations

import re
from datetime import date

from django.urls import reverse

from apps.bonsai.models import BonsaiPlant
from apps.logs.models import CareLog
from apps.schedules.models import CareScheduleCompletion


def test_logs_list_requires_login(client):
    res = client.get(reverse("logs:list"))
    assert res.status_code == 302


def test_logs_list_renders(client, user):
    client.force_login(user)
    res = client.get(reverse("logs:list"))
    assert res.status_code == 200


def test_log_create_marks_todo_done(client, user, bonsai_species):
    """プリフィル経由でログ作成すると CareScheduleCompletion が作られる。"""
    plant = BonsaiPlant.objects.create(user=user, species=bonsai_species, name="一郎")
    client.force_login(user)
    qs = (
        f"?bonsai={plant.pk}"
        f"&task_type=bud_pinching"
        f"&source_type=species_task"
        f"&source_ref=species_task:{bonsai_species.id}:5:0"
        f"&year_month=2026-05"
    )
    res = client.post(
        reverse("logs:create") + qs,
        data={
            "bonsai": str(plant.pk),
            "task_type": "bud_pinching",
            "task_type_other": "",
            "performed_at": "2026-05-15T09:00",
            "weather": "",
            "temperature_c": "",
            "fertilizer": "",
            "fertilizer_amount": "",
            "health_evaluation": "",
            "notes": "芽摘みした",
        },
    )
    assert res.status_code == 302, getattr(res, "context", None)
    assert CareLog.objects.filter(user=user).count() == 1
    completion = CareScheduleCompletion.objects.filter(user=user).first()
    assert completion is not None
    assert completion.source_type == "species_task"
    assert completion.year_month == date(2026, 5, 1)


def _post_log(client, plant, task_types, **extra):
    return client.post(
        reverse("logs:create"),
        data={
            "bonsai": str(plant.pk),
            "task_type": task_types,
            "performed_at": "2026-05-15T09:00",
            **extra,
        },
    )


def test_log_create_accepts_multiple_task_types(client, user, bonsai_species):
    """同時に行った作業を 1 件の記録に複数付けられる。"""
    plant = BonsaiPlant.objects.create(user=user, species=bonsai_species, name="一郎")
    client.force_login(user)
    res = _post_log(client, plant, ["fertilizing", "pruning", "watering"])
    assert res.status_code == 302, getattr(res, "context", None)

    log = CareLog.objects.get(user=user)
    # 並びは選んだ順ではなく TaskType の定義順
    assert log.task_type_values == ["watering", "fertilizing", "pruning"]
    assert log.task_label == "潅水・施肥・剪定"

    html = client.get(reverse("logs:detail", kwargs={"pk": log.pk})).content.decode()
    assert "潅水・施肥・剪定" in html
    html = client.get(reverse("logs:list")).content.decode()
    assert "潅水・施肥・剪定" in html


def test_log_create_requires_a_task_type(client, user, bonsai_species):
    plant = BonsaiPlant.objects.create(user=user, species=bonsai_species, name="一郎")
    client.force_login(user)
    res = _post_log(client, plant, [])
    assert res.status_code == 200
    assert "作業種別を 1 つ以上選んでください。" in res.content.decode()
    assert not CareLog.objects.exists()


def test_log_list_filter_matches_any_task_type(client, user, bonsai_species):
    """絞り込みと植え替え履歴は、2 つ目以降の作業種別でも拾う。"""
    plant = BonsaiPlant.objects.create(user=user, species=bonsai_species, name="一郎")
    client.force_login(user)
    _post_log(client, plant, ["pruning", "repotting"])
    _post_log(client, plant, ["watering"])

    for task_type in ("pruning", "repotting"):
        res = client.get(reverse("logs:list"), {"task_type": task_type})
        assert [log.task_label for log in res.context["logs"]] == ["剪定・植え替え"]
    res = client.get(reverse("logs:list"), {"task_type": "fertilizing"})
    assert list(res.context["logs"]) == []

    res = client.get(reverse("bonsai:detail", kwargs={"pk": plant.pk}), {"tab": "repotting"})
    assert len(res.context["repot_logs"]) == 1


def test_log_edit_replaces_task_types(client, user, bonsai_species):
    plant = BonsaiPlant.objects.create(user=user, species=bonsai_species, name="一郎")
    client.force_login(user)
    _post_log(client, plant, ["watering", "pruning", "other"], task_type_other="苔の手入れ")
    log = CareLog.objects.get(user=user)
    assert log.task_label == "潅水・剪定・苔の手入れ"

    edit_url = reverse("logs:edit", kwargs={"pk": log.pk})
    html = client.get(edit_url).content.decode()
    assert len(re.findall(r'name="task_type"[^>]*\schecked', html)) == 3

    res = client.post(
        edit_url,
        data={
            "bonsai": str(plant.pk),
            "task_type": ["pruning", "wiring"],
            "task_type_other": "苔の手入れ",
            "performed_at": "2026-05-15T09:00",
        },
    )
    assert res.status_code == 302, getattr(res, "context", None)
    log.refresh_from_db()
    assert log.task_type_values == ["pruning", "wiring"]
    # 「その他」を外したら自由入力も残さない
    assert log.task_type_other == ""


def test_log_create_prefill_checks_single_task_type(client, user, bonsai_species):
    plant = BonsaiPlant.objects.create(user=user, species=bonsai_species, name="一郎")
    client.force_login(user)
    res = client.get(reverse("logs:create"), {"bonsai": plant.pk, "task_type": "repotting"})
    assert res.context["form"]["task_type"].value() == ["repotting"]


def test_csv_export_joins_task_types(client, user, bonsai_species):
    plant = BonsaiPlant.objects.create(user=user, species=bonsai_species, name="一郎")
    client.force_login(user)
    _post_log(client, plant, ["watering", "fertilizing"])
    body = client.get(reverse("logs:export")).content.decode("utf-8-sig")
    assert "潅水・施肥" in body
