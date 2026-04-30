"""logs アプリのビュー最小スモークテスト。"""

from __future__ import annotations

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
