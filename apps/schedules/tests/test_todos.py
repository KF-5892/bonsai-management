"""compose_monthly_todos / mark_todo_done のスモークテスト。

最低限のカバー範囲:
- 3 ソース（品種マスタ由来 / ユーザー個別スケジュール / 月次共通アドバイス）
  からの合成
- 完了状態の LEFT JOIN（マッチした Todo にのみ ``completion`` が付くこと）
- ``mark_todo_done`` が schedule の場合に bonsai を自動付与すること
- 別ユーザーのデータに侵食しない（ユーザー絞り込み）
- ``year_month`` が 1 日でなくても安全に丸められること
- ``species`` が None の盆栽はスキップされること
"""

from __future__ import annotations

from datetime import date

import pytest
from django.contrib.auth import get_user_model

from apps.bonsai.models import BonsaiPlant, BonsaiSpecies
from apps.schedules.models import (
    CareSchedule,
    CareScheduleCompletion,
    CompletionSourceType,
    CompletionStatus,
    MonthlyAdvice,
    TaskType,
)
from apps.schedules.services import (
    Todo,
    compose_monthly_todos,
    mark_todo_done,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def user(db):
    return User.objects.create_user(email="alice@example.com", password="pw12345!")


@pytest.fixture
def other_user(db):
    return User.objects.create_user(email="bob@example.com", password="pw12345!")


@pytest.fixture
def species(db):
    return BonsaiSpecies.objects.create(
        slug="kuromatsu",
        name="黒松",
        monthly_tasks=[
            {
                "month": 4,
                "period": "上旬",
                "task_type": "bud_pinching",
                "description": "新芽を 2 枚残してつまむ",
            },
            {
                "month": 5,
                "period": "中旬",
                "task_type": "fertilizing",
                "description": "5 月の施肥",
            },
            # 不正データ: month が無いものは無視される想定
            {"task_type": "watering", "description": "壊れたデータ"},
        ],
    )


@pytest.fixture
def plant(db, user, species):
    return BonsaiPlant.objects.create(user=user, species=species, name="太郎")


@pytest.fixture
def plant_no_species(db, user):
    return BonsaiPlant.objects.create(user=user, species=None, name="名無し")


@pytest.fixture
def schedule_in_month(db, user, plant):
    return CareSchedule.objects.create(
        bonsai=plant,
        user=user,
        task_type=TaskType.WATERING,
        title="毎週の水やり",
        repeat_type="weekly",
        start_date=date(2026, 4, 1),
        next_run_at=date(2026, 4, 15),
        is_active=True,
    )


@pytest.fixture
def schedule_other_month(db, user, plant):
    return CareSchedule.objects.create(
        bonsai=plant,
        user=user,
        task_type=TaskType.PRUNING,
        title="5 月の剪定",
        start_date=date(2026, 5, 1),
        next_run_at=date(2026, 5, 10),
        is_active=True,
    )


@pytest.fixture
def schedule_inactive(db, user, plant):
    return CareSchedule.objects.create(
        bonsai=plant,
        user=user,
        task_type=TaskType.OBSERVATION,
        title="無効化済み",
        start_date=date(2026, 4, 1),
        next_run_at=date(2026, 4, 20),
        is_active=False,
    )


@pytest.fixture
def advice_apr_published(db):
    return MonthlyAdvice.objects.create(
        month=4, title="4 月の灌水", advice_text="まだ朝晩は寒いので注意", is_published=True
    )


@pytest.fixture
def advice_apr_draft(db):
    return MonthlyAdvice.objects.create(
        month=4, title="4 月の下書き", advice_text="非公開", is_published=False
    )


@pytest.fixture
def advice_may(db):
    return MonthlyAdvice.objects.create(
        month=5, title="5 月の施肥", advice_text="そろそろ施肥開始", is_published=True
    )


# ---------------------------------------------------------------------------
# compose_monthly_todos
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_compose_merges_three_sources(
    user,
    plant,
    plant_no_species,
    schedule_in_month,
    schedule_other_month,
    schedule_inactive,
    advice_apr_published,
    advice_apr_draft,
    advice_may,
):
    """3 ソースが正しく合成され、絞り込み条件が効くこと。"""
    todos = compose_monthly_todos(user, date(2026, 4, 1))

    by_source: dict[str, list[Todo]] = {}
    for t in todos:
        by_source.setdefault(t.source_type, []).append(t)

    # ① 品種マスタ由来: 4 月分の 1 件のみ（5 月分・壊れデータは除外、
    #    species=None の盆栽もスキップ）
    species_todos = by_source.get(CompletionSourceType.SPECIES_TASK, [])
    assert len(species_todos) == 1
    assert species_todos[0].task_type == "bud_pinching"
    assert species_todos[0].bonsai_name == "太郎"
    assert species_todos[0].source_ref.startswith("species_task:")
    assert species_todos[0].source_ref.endswith(":4:0")  # month=4, index=0

    # ② スケジュール: is_active=True かつ next_run_at が当月の 1 件のみ
    sched_todos = by_source.get(CompletionSourceType.SCHEDULE, [])
    assert len(sched_todos) == 1
    assert sched_todos[0].title == "毎週の水やり"
    assert sched_todos[0].source_ref == f"schedule:{schedule_in_month.id}"

    # ③ 月次共通アドバイス: is_published=True かつ month=4 の 1 件のみ
    advice_todos = by_source.get(CompletionSourceType.ADVICE, [])
    assert len(advice_todos) == 1
    assert advice_todos[0].title == "4 月の灌水"
    assert advice_todos[0].source_ref == f"advice:{advice_apr_published.id}"


@pytest.mark.django_db
def test_compose_left_joins_completion(
    user,
    plant,
    schedule_in_month,
    advice_apr_published,
):
    """完了レコードがある Todo にのみ completion が付与されること。"""
    # schedule_in_month を完了マーク
    mark_todo_done(
        user=user,
        source_type=CompletionSourceType.SCHEDULE,
        source_ref=f"schedule:{schedule_in_month.id}",
        year_month=date(2026, 4, 1),
    )

    todos = compose_monthly_todos(user, date(2026, 4, 1))
    sched = next(t for t in todos if t.source_type == CompletionSourceType.SCHEDULE)
    advice = next(t for t in todos if t.source_type == CompletionSourceType.ADVICE)

    assert sched.completion is not None
    assert sched.completion["status"] == CompletionStatus.DONE
    assert advice.completion is None

    # ソートは「未完了 → 完了」なので、未完了の advice が先に来る
    done_indices = [i for i, t in enumerate(todos) if t.completion is not None]
    pending_indices = [i for i, t in enumerate(todos) if t.completion is None]
    assert max(pending_indices) < min(done_indices)


@pytest.mark.django_db
def test_compose_isolates_users(user, other_user, schedule_in_month, advice_apr_published):
    """別ユーザーのスケジュールは混ざらない（advice は全ユーザー共通で出る）。"""
    todos = compose_monthly_todos(other_user, date(2026, 4, 1))
    # other_user は盆栽もスケジュールも持たないが、共通 advice は出る
    assert all(t.source_type != CompletionSourceType.SCHEDULE for t in todos)
    assert all(t.source_type != CompletionSourceType.SPECIES_TASK for t in todos)
    assert any(t.source_type == CompletionSourceType.ADVICE for t in todos)


@pytest.mark.django_db
def test_compose_normalizes_year_month(user, schedule_in_month):
    """year_month.day が 1 でなくても当月扱いされること。"""
    todos = compose_monthly_todos(user, date(2026, 4, 17))
    assert any(
        t.source_type == CompletionSourceType.SCHEDULE
        and t.source_ref == f"schedule:{schedule_in_month.id}"
        for t in todos
    )


# ---------------------------------------------------------------------------
# mark_todo_done
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_mark_todo_done_autosets_bonsai_for_schedule(user, schedule_in_month):
    """source_type=schedule のとき bonsai を未指定でも自動セットされること。"""
    completion = mark_todo_done(
        user=user,
        source_type=CompletionSourceType.SCHEDULE,
        source_ref=f"schedule:{schedule_in_month.id}",
        year_month=date(2026, 4, 1),
    )
    assert completion.bonsai_id == schedule_in_month.bonsai_id
    assert completion.year_month == date(2026, 4, 1)
    assert completion.status == CompletionStatus.DONE


@pytest.mark.django_db
def test_mark_todo_done_is_idempotent(user, schedule_in_month):
    """同一 (user, source_type, source_ref, year_month) は upsert で 1 行に収まる。"""
    ref = f"schedule:{schedule_in_month.id}"
    mark_todo_done(
        user=user,
        source_type=CompletionSourceType.SCHEDULE,
        source_ref=ref,
        year_month=date(2026, 4, 1),
    )
    mark_todo_done(
        user=user,
        source_type=CompletionSourceType.SCHEDULE,
        source_ref=ref,
        year_month=date(2026, 4, 1),
        status=CompletionStatus.SKIPPED,
    )
    qs = CareScheduleCompletion.objects.filter(
        user=user, source_type=CompletionSourceType.SCHEDULE, source_ref=ref
    )
    assert qs.count() == 1
    assert qs.get().status == CompletionStatus.SKIPPED
