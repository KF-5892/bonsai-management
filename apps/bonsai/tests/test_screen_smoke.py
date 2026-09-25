"""全画面の GET スモークテスト。

テンプレートの構文エラーや URL 名の綴り間違いを 1 本で検出するため、
アプリ横断で主要画面に GET してステータス 200 を確認する。
個々の画面の振る舞いは各アプリのテストで検証する。
"""

from datetime import date

import pytest
from django.urls import reverse

from apps.bonsai.models import BonsaiPlant, Tag
from apps.logs.models import CareLog, Fertilizer
from apps.schedules.models import CareSchedule, RepeatType


@pytest.mark.django_db
def test_all_get_screens(client, user, bonsai_species):
    plant = BonsaiPlant.objects.create(user=user, species=bonsai_species, name="黒松 太郎")
    tag = Tag.objects.create(user=user, name="ベランダ")
    plant.tags.add(tag)
    fert = Fertilizer.objects.create(user=user, name="油かす")
    CareLog.objects.create(user=user, bonsai=plant, task_type="watering", notes="水やり")
    CareSchedule.objects.create(
        user=user,
        bonsai=plant,
        task_type="watering",
        title="水やり",
        repeat_type=RepeatType.NONE,
        start_date=date.today(),
        next_run_at=date.today(),
    )
    client.force_login(user)

    urls = [
        reverse("bonsai:home"),
        reverse("bonsai:home") + "?view=species",
        reverse("bonsai:home") + "?view=tag&range=week",
        reverse("bonsai:home") + "?range=custom&from=2026-04-01&to=2026-04-30",
        reverse("bonsai:create"),
        reverse("bonsai:detail", kwargs={"pk": plant.pk}),
        reverse("bonsai:edit", kwargs={"pk": plant.pk}),
        reverse("bonsai:delete", kwargs={"pk": plant.pk}),
        reverse("bonsai:media_gallery", kwargs={"pk": plant.pk}),
        reverse("bonsai:media_upload", kwargs={"pk": plant.pk}),
        reverse("bonsai:species_detail", kwargs={"slug": bonsai_species.slug}),
        reverse("bonsai:tag_list"),
        reverse("bonsai:tag_create"),
        reverse("bonsai:tag_edit", kwargs={"pk": tag.pk}),
        reverse("bonsai:tag_delete", kwargs={"pk": tag.pk}),
        reverse("schedules:list"),
        reverse("schedules:year"),
        reverse("schedules:review"),
        reverse("schedules:export"),
        reverse("schedules:create"),
        reverse("logs:list"),
        reverse("logs:create"),
        reverse("logs:bulk_create"),
        reverse("logs:fertilizer_list"),
        reverse("logs:fertilizer_create"),
        reverse("logs:fertilizer_edit", kwargs={"pk": fert.pk}),
        reverse("logs:fertilizer_delete", kwargs={"pk": fert.pk}),
        reverse("articles:list"),
        reverse("search") + "?q=黒松",
        reverse("accounts:settings"),
        reverse("accounts:profile"),
        reverse("accounts:notifications"),
        reverse("accounts:library"),
    ]
    failures = []
    for url in urls:
        res = client.get(url)
        if res.status_code != 200:
            failures.append((url, res.status_code))
    assert not failures, failures

    for tab in ["overview", "logs", "schedules", "media", "repotting", "compare"]:
        res = client.get(reverse("bonsai:detail", kwargs={"pk": plant.pk}), {"tab": tab})
        assert res.status_code == 200, tab
