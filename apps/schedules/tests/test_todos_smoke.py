"""compose_monthly_todos の最小スモーク。

3 ソース（品種マスタ由来 / ユーザー個別スケジュール / 月次共通アドバイス）が
合成結果に揃って現れることだけを確認する詳細テストは
``test_todos.py`` 側で別途行う想定。
"""

from __future__ import annotations

from datetime import date

from apps.bonsai.models import BonsaiPlant, BonsaiSpecies, SpeciesCategory
from apps.schedules.models import CareSchedule, MonthlyAdvice, RepeatType, TaskType
from apps.schedules.services.todos import compose_monthly_todos


def test_compose_monthly_todos_includes_three_sources(user):
    species = BonsaiSpecies.objects.create(
        slug="kuromatsu-smoke",
        name="黒松（スモーク）",
        category=SpeciesCategory.CONIFER,
        monthly_tasks=[
            {
                "month": 5,
                "period": "中旬",
                "task_type": TaskType.BUD_PINCHING.value,
                "description": "新芽の芽摘み",
            },
        ],
    )
    plant = BonsaiPlant.objects.create(user=user, species=species, name="一郎")

    CareSchedule.objects.create(
        bonsai=plant,
        user=user,
        task_type=TaskType.WATERING,
        title="個別スケジュール: 灌水",
        repeat_type=RepeatType.WEEKLY,
        start_date=date(2026, 5, 1),
        next_run_at=date(2026, 5, 10),
        is_active=True,
    )

    MonthlyAdvice.objects.create(
        month=5,
        title="月次アドバイス: 新芽期の管理",
        advice_text="芽摘みと葉水を励行する。",
        is_published=True,
    )

    todos = compose_monthly_todos(user, date(2026, 5, 1))

    source_types = {t.source_type for t in todos}
    assert "species_task" in source_types
    assert "schedule" in source_types
    assert "advice" in source_types
    assert len(todos) >= 3
