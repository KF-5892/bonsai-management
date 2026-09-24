"""UI 評価で修正した挙動のテスト（ToDo 折りたたみ / 品種ラベル / クイック記録導線）。"""

from __future__ import annotations

from datetime import date

from django.urls import reverse

from apps.bonsai.models import BonsaiPlant, BonsaiSpecies, SpeciesCategory
from apps.schedules.models import CareSchedule, RepeatType


def test_home_collapses_long_todo_list(client, user, bonsai_species):
    plant = BonsaiPlant.objects.create(user=user, species=bonsai_species, name="黒松 太郎")
    today = date.today()
    for i in range(8):
        CareSchedule.objects.create(
            user=user,
            bonsai=plant,
            task_type="watering",
            title=f"作業 {i}",
            repeat_type=RepeatType.NONE,
            start_date=today,
            next_run_at=today,
        )
    client.force_login(user)

    res = client.get(reverse("bonsai:home"))
    assert len(res.context["todos"]) == 5
    assert res.context["hidden_todo_count"] == 3
    assert res.context["todo_total"] == 8
    assert "残り 3 件を表示" in res.content.decode()

    res = client.get(reverse("bonsai:home"), {"todos": "all"})
    assert len(res.context["todos"]) == 8
    assert res.context["hidden_todo_count"] == 0


def test_species_detail_shows_task_labels(client):
    species = BonsaiSpecies.objects.create(
        slug="shinpaku",
        name="真柏",
        category=SpeciesCategory.CONIFER,
        monthly_tasks=[
            {"month": 5, "period": "中旬", "task_type": "bud_pinching", "description": "芽摘み"},
            {"month": 6, "task_type": "custom_work", "description": "独自作業"},
        ],
    )
    res = client.get(reverse("bonsai:species_detail", kwargs={"slug": species.slug}))
    html = res.content.decode()
    assert "芽摘み" in html
    assert "bud_pinching" not in html
    # TaskType に無い値はそのまま表示してデータ不備に気づけるようにする
    assert "custom_work" in html


def test_detail_has_quick_log_buttons_and_full_list_link(client, user, bonsai_species):
    plant = BonsaiPlant.objects.create(user=user, species=bonsai_species, name="黒松 太郎")
    client.force_login(user)
    res = client.get(reverse("bonsai:detail", kwargs={"pk": plant.pk}), {"tab": "logs"})
    html = res.content.decode()
    assert reverse("logs:quick_create") in html
    assert "潅水を記録" in html
    assert [value for value, _label, _icon in res.context["quick_tasks"]] == [
        "watering",
        "leaf_misting",
        "observation",
    ]


def test_home_group_header_links_to_bulk_log(client, user, bonsai_species):
    first = BonsaiPlant.objects.create(user=user, species=bonsai_species, name="一号")
    second = BonsaiPlant.objects.create(user=user, species=bonsai_species, name="二号")
    client.force_login(user)
    res = client.get(reverse("bonsai:home"), {"view": "species"})
    html = res.content.decode()
    assert "この2鉢に一括記録" in html
    assert f"bonsai={first.pk}" in html and f"bonsai={second.pk}" in html
