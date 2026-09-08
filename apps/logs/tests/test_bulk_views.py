"""一括ログ記録のテスト。"""

from __future__ import annotations

from django.urls import reverse

from apps.bonsai.models import BonsaiPlant
from apps.logs.models import CareLog


def test_bulk_create_makes_one_log_per_plant(client, user, bonsai_species):
    plants = [
        BonsaiPlant.objects.create(user=user, species=bonsai_species, name=f"松 {i}")
        for i in range(3)
    ]
    client.force_login(user)

    res = client.post(
        reverse("logs:bulk_create"),
        {
            "bonsai": [p.pk for p in plants[:2]],
            "task_type": "watering",
            "performed_at": "2026-04-10T09:00",
            "weather": "",
            "health_evaluation": "",
            "notes": "まとめて潅水",
        },
    )
    assert res.status_code == 302
    logs = CareLog.objects.filter(user=user)
    assert logs.count() == 2
    assert set(logs.values_list("bonsai_id", flat=True)) == {plants[0].pk, plants[1].pk}
    assert all(log.notes == "まとめて潅水" for log in logs)


def test_bulk_create_rejects_other_users_plant(client, user, other_user, bonsai_species):
    mine = BonsaiPlant.objects.create(user=user, species=bonsai_species, name="自分の")
    theirs = BonsaiPlant.objects.create(user=other_user, species=bonsai_species, name="他人の")
    client.force_login(user)

    res = client.post(
        reverse("logs:bulk_create"),
        {
            "bonsai": [mine.pk, theirs.pk],
            "task_type": "watering",
            "performed_at": "2026-04-10T09:00",
        },
    )
    # 選択肢に無い盆栽が含まれるためフォームエラーで再描画される
    assert res.status_code == 200
    assert CareLog.objects.count() == 0
