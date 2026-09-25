"""年間スケジュール / 月末レビュー / 月別フィルタのテスト。"""

from __future__ import annotations

from datetime import date

from django.urls import reverse

from apps.bonsai.models import BonsaiPlant, BonsaiSpecies, SpeciesCategory, Tag
from apps.schedules.models import CareSchedule, CompletionSourceType, RepeatType
from apps.schedules.services import mark_todo_done, summarize_monthly_todos


def _schedule(user, plant, *, title: str, run_at: date, task_type: str = "watering"):
    return CareSchedule.objects.create(
        user=user,
        bonsai=plant,
        task_type=task_type,
        title=title,
        repeat_type=RepeatType.NONE,
        start_date=run_at,
        next_run_at=run_at,
    )


def test_yearly_view_lists_twelve_months(client, user, bonsai_species):
    plant = BonsaiPlant.objects.create(user=user, species=bonsai_species, name="黒松 太郎")
    _schedule(user, plant, title="4月の水やり", run_at=date(2026, 4, 10))
    client.force_login(user)

    res = client.get(reverse("schedules:year"), {"year": "2026"})
    assert res.status_code == 200
    summaries = res.context["summaries"]
    assert len(summaries) == 12
    april = summaries[3]
    assert april.year_month == date(2026, 4, 1)
    assert april.total >= 1


def test_review_defaults_to_previous_month(client, user):
    client.force_login(user)
    res = client.get(reverse("schedules:review"))
    assert res.status_code == 200
    today = date.today()
    expected = (
        date(today.year - 1, 12, 1) if today.month == 1 else date(today.year, today.month - 1, 1)
    )
    assert res.context["year_month"] == expected


def test_review_shows_completion_rate(client, user, bonsai_species):
    plant = BonsaiPlant.objects.create(user=user, species=bonsai_species, name="黒松 太郎")
    ym = date(2026, 4, 1)
    done_schedule = _schedule(user, plant, title="済んだ作業", run_at=date(2026, 4, 5))
    _schedule(user, plant, title="残った作業", run_at=date(2026, 4, 20))
    mark_todo_done(
        user,
        CompletionSourceType.SCHEDULE,
        f"schedule:{done_schedule.id}",
        ym,
        bonsai=plant,
    )
    client.force_login(user)

    res = client.get(reverse("schedules:review"), {"year": "2026", "month": "4"})
    summary = res.context["summary"]
    assert summary.total == 2
    assert summary.done == 1
    assert summary.completion_rate == 50
    assert len(res.context["pending_todos"]) == 1


def test_monthly_filters(client, user):
    conifer = BonsaiSpecies.objects.create(
        slug="kuromatsu", name="黒松", category=SpeciesCategory.CONIFER
    )
    broadleaf = BonsaiSpecies.objects.create(
        slug="kaede", name="楓", category=SpeciesCategory.BROADLEAF
    )
    pine = BonsaiPlant.objects.create(user=user, species=conifer, name="黒松 太郎")
    maple = BonsaiPlant.objects.create(user=user, species=broadleaf, name="楓 花子")
    tag = Tag.objects.create(user=user, name="ベランダ")
    pine.tags.add(tag)

    _schedule(user, pine, title="松の水やり", run_at=date(2026, 4, 5))
    _schedule(user, maple, title="楓の施肥", run_at=date(2026, 4, 6), task_type="fertilizing")
    client.force_login(user)

    base = {"year": "2026", "month": "4"}

    res = client.get(reverse("schedules:list"), base)
    assert len(res.context["todos"]) == 2

    res = client.get(reverse("schedules:list"), {**base, "task_type": "fertilizing"})
    assert [t.title for t in res.context["todos"]] == ["楓の施肥"]

    res = client.get(reverse("schedules:list"), {**base, "bonsai": pine.pk})
    assert [t.title for t in res.context["todos"]] == ["松の水やり"]

    res = client.get(reverse("schedules:list"), {**base, "species": broadleaf.pk})
    assert [t.title for t in res.context["todos"]] == ["楓の施肥"]

    res = client.get(reverse("schedules:list"), {**base, "tag": tag.pk})
    assert [t.title for t in res.context["todos"]] == ["松の水やり"]


def test_summary_breakdown_uses_task_type_labels(user, bonsai_species):
    plant = BonsaiPlant.objects.create(user=user, species=bonsai_species, name="黒松 太郎")
    _schedule(user, plant, title="水やり", run_at=date(2026, 4, 5))
    summary = summarize_monthly_todos(user, date(2026, 4, 1))
    assert ("潅水", 1) in summary.task_type_breakdown


def test_todo_export_returns_csv(client, user, bonsai_species):
    plant = BonsaiPlant.objects.create(user=user, species=bonsai_species, name="黒松 太郎")
    _schedule(user, plant, title="4月の水やり", run_at=date(2026, 4, 10))
    client.force_login(user)

    res = client.get(reverse("schedules:export"), {"year": "2026", "month": "4"})
    assert res.status_code == 200
    assert res["Content-Type"].startswith("text/csv")
    assert "todos_202604.csv" in res["Content-Disposition"]
    body = res.content.decode("utf-8-sig")
    assert "対象の盆栽" in body
    assert "4月の水やり" in body


def test_todo_export_supports_custom_range(client, user, bonsai_species):
    plant = BonsaiPlant.objects.create(user=user, species=bonsai_species, name="黒松 太郎")
    _schedule(user, plant, title="4/15 の作業", run_at=date(2026, 4, 15))
    client.force_login(user)

    res = client.get(reverse("schedules:export"), {"from": "2026-04-14", "to": "2026-04-16"})
    body = res.content.decode("utf-8-sig")
    assert "4/15 の作業" in body

    res = client.get(reverse("schedules:export"), {"from": "2026-04-01", "to": "2026-04-05"})
    body = res.content.decode("utf-8-sig")
    assert "4/15 の作業" not in body


def test_breakdown_merges_same_label_sources(user, bonsai_species):
    """生値が異なっても同じ作業種別ラベルになる ToDo は 1 チップに合算される。"""
    from apps.schedules.models import MonthlyAdvice

    plant = BonsaiPlant.objects.create(user=user, species=bonsai_species, name="黒松 太郎")
    _schedule(user, plant, title="植え替え", run_at=date(2026, 4, 5), task_type="repotting")
    # アドバイスの category には日本語ラベルが入ることがある
    MonthlyAdvice.objects.create(
        month=4, title="春の植え替え", advice_text="適期です。", category="repotting"
    )

    summary = summarize_monthly_todos(user, date(2026, 4, 1))
    labels = [label for label, _count in summary.task_type_breakdown]
    assert labels.count("植え替え") == 1
    assert dict(summary.task_type_breakdown)["植え替え"] == 2
