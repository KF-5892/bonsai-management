"""月次 ToDo 合成サービス。

「今月のやること」を 3 ソースから合成する:

1. 品種マスタ由来 (``BonsaiSpecies.monthly_tasks``)
2. ユーザー個別スケジュール (``CareSchedule``)
3. 月次共通アドバイス (``MonthlyAdvice``)

完了状態は ``CareScheduleCompletion`` に別管理されており、
``(source_type, source_ref, year_month)`` のキーで LEFT JOIN する。

設計判断: docs/技術要件書.md §10、docs/開発前検討事項.md §10.1（A 案）。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from django.db.models import Q
from django.utils import timezone

from apps.bonsai.models import BonsaiPlant

from ..models import (
    CareSchedule,
    CareScheduleCompletion,
    CompletionSourceType,
    CompletionStatus,
    MonthlyAdvice,
    TaskType,
)

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser

    from apps.logs.models import CareLog


# ---------------------------------------------------------------------------
# Todo dataclass
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class Todo:
    """月次 ToDo の表示用データクラス。

    ビュー層は ``asdict()`` 経由で template にも渡せるよう dataclass を採用。
    """

    source_type: str
    source_ref: str
    bonsai_id: str | None
    bonsai_name: str | None
    species_name: str | None
    task_type: str
    period: str | None
    title: str
    description: str
    completion: dict[str, Any] | None = field(default=None)
    # 期間フィルタ（今週 / カスタム期間）用の目安日。両端を含む。
    period_start: date | None = field(default=None)
    period_end: date | None = field(default=None)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# 内部ヘルパー
# ---------------------------------------------------------------------------
def _completion_to_dict(c: CareScheduleCompletion) -> dict[str, Any]:
    return {
        "status": c.status,
        "completed_at": c.completed_at,
        "log_id": c.log_id,
    }


def _is_done(todo: Todo) -> bool:
    return todo.completion is not None and todo.completion.get("status") == CompletionStatus.DONE


def _species_task_ref(species_id: str, month: int, index: int) -> str:
    return f"species_task:{species_id}:{month}:{index}"


def _schedule_ref(schedule_id: str) -> str:
    return f"schedule:{schedule_id}"


def _advice_ref(advice_id: str) -> str:
    return f"advice:{advice_id}"


def _month_bounds(year_month: date) -> tuple[date, date]:
    """当月の初日と末日（両端を含む）を返す。"""
    first = date(year_month.year, year_month.month, 1)
    if first.month == 12:
        next_first = date(first.year + 1, 1, 1)
    else:
        next_first = date(first.year, first.month + 1, 1)
    return first, next_first - timedelta(days=1)


def _period_range(year_month: date, period: str | None) -> tuple[date, date]:
    """「上旬 / 中旬 / 下旬」を日付範囲（両端含む）に変換する。

    未指定・不明な値は当月全体として扱う。
    """
    first, last = _month_bounds(year_month)
    if period and "上旬" in period:
        return first, first.replace(day=10)
    if period and "中旬" in period:
        return first.replace(day=11), first.replace(day=20)
    if period and "下旬" in period:
        return first.replace(day=21), last
    return first, last


# ---------------------------------------------------------------------------
# 公開 API
# ---------------------------------------------------------------------------
def compose_monthly_todos(user: AbstractBaseUser, year_month: date) -> list[Todo]:
    """指定ユーザー・指定月の ToDo を 3 ソースから合成する。

    :param user: 対象ユーザー
    :param year_month: 対象月の 1 日 (例 ``date(2026, 4, 1)``)。caller 側で必ず
        日付を 1 日に正規化して渡す前提だが、本関数内でも防御的に当月の 1 日へ
        丸める。
    :return: ``Todo`` のリスト（未完了 → 完了 の順、関連盆栽名・作業種別で副ソート）。
    """

    # 日付が 1 日でなくても当月の 1 日に揃えて以降の処理を一貫させる
    year_month = date(year_month.year, year_month.month, 1)
    month = year_month.month
    todos: list[Todo] = []

    # ------------------------------------------------------------------
    # ① 品種マスタ由来の仮想タスク
    # ------------------------------------------------------------------
    plants: list[BonsaiPlant] = list(
        BonsaiPlant.objects.filter(user=user).select_related("species")
    )
    for plant in plants:
        species = plant.species
        if species is None:
            continue
        monthly_tasks = species.monthly_tasks or []
        for index, task in enumerate(monthly_tasks):
            if not isinstance(task, dict):
                continue
            try:
                task_month = int(task.get("month"))
            except (TypeError, ValueError):
                continue
            if task_month != month:
                continue

            task_type = str(task.get("task_type", "other") or "other")
            period = task.get("period") or None
            description = str(task.get("description", "") or "")
            title = description[:40] or f"{species.name} の {task_type}"

            task_start, task_end = _period_range(year_month, period)
            todos.append(
                Todo(
                    source_type=CompletionSourceType.SPECIES_TASK,
                    source_ref=_species_task_ref(species.id, month, index),
                    bonsai_id=plant.id,
                    bonsai_name=plant.name,
                    species_name=species.name,
                    task_type=task_type,
                    period=period,
                    title=title,
                    description=description,
                    period_start=task_start,
                    period_end=task_end,
                )
            )

    # ------------------------------------------------------------------
    # ② ユーザー個別スケジュール（next_run_at が当月）
    # ------------------------------------------------------------------
    month_start = year_month  # 既に 1 日に丸められている
    if month == 12:
        next_month_start = date(year_month.year + 1, 1, 1)
    else:
        next_month_start = date(year_month.year, month + 1, 1)

    schedules = (
        CareSchedule.objects.filter(user=user, is_active=True)
        .filter(
            Q(next_run_at__gte=month_start, next_run_at__lt=next_month_start)
            | Q(
                next_run_at__isnull=True,
                start_date__gte=month_start,
                start_date__lt=next_month_start,
            )
        )
        .select_related("bonsai", "bonsai__species")
    )
    month_first, month_last = _month_bounds(year_month)
    for sched in schedules:
        plant = sched.bonsai
        species = plant.species if plant else None
        due = sched.next_run_at or sched.start_date
        todos.append(
            Todo(
                source_type=CompletionSourceType.SCHEDULE,
                source_ref=_schedule_ref(sched.id),
                bonsai_id=plant.id if plant else None,
                bonsai_name=plant.name if plant else None,
                species_name=species.name if species else None,
                task_type=sched.task_type,
                period=None,
                title=sched.title or sched.get_task_type_display(),
                description=sched.notes,
                period_start=due,
                period_end=due,
            )
        )

    # ------------------------------------------------------------------
    # ③ 月次共通アドバイス
    # ------------------------------------------------------------------
    advices = MonthlyAdvice.objects.filter(month=month, is_published=True)
    for advice in advices:
        todos.append(
            Todo(
                source_type=CompletionSourceType.ADVICE,
                source_ref=_advice_ref(advice.id),
                bonsai_id=None,
                bonsai_name=None,
                species_name=None,
                task_type=advice.category or "other",
                period=None,
                title=advice.title,
                description=advice.advice_text,
                period_start=month_first,
                period_end=month_last,
            )
        )

    # ------------------------------------------------------------------
    # 完了状態を一括取得して LEFT JOIN
    # ------------------------------------------------------------------
    refs = [(t.source_type, t.source_ref) for t in todos]
    if refs:
        ref_set = {ref for _, ref in refs}
        completions = CareScheduleCompletion.objects.filter(
            user=user,
            year_month=month_start,
            source_ref__in=ref_set,
        )
        completion_map: dict[tuple[str, str], CareScheduleCompletion] = {
            (c.source_type, c.source_ref): c for c in completions
        }
        for todo in todos:
            c = completion_map.get((todo.source_type, todo.source_ref))
            if c is not None:
                todo.completion = _completion_to_dict(c)

    # ------------------------------------------------------------------
    # ソート: 未完了 → 完了、関連盆栽名、作業種別
    # ------------------------------------------------------------------
    todos.sort(
        key=lambda t: (
            _is_done(t),
            (t.bonsai_name or ""),
            t.task_type,
            t.title,
        )
    )
    return todos


def get_todo_completion_status(
    user: AbstractBaseUser,
    source_type: str,
    source_ref: str,
    year_month: date,
) -> CareScheduleCompletion | None:
    """指定 ToDo の完了レコードを 1 件返す（無ければ ``None``）。"""

    month_start = date(year_month.year, year_month.month, 1)
    return CareScheduleCompletion.objects.filter(
        user=user,
        source_type=source_type,
        source_ref=source_ref,
        year_month=month_start,
    ).first()


def mark_todo_done(
    user: AbstractBaseUser,
    source_type: str,
    source_ref: str,
    year_month: date,
    *,
    log: CareLog | None = None,
    bonsai: BonsaiPlant | None = None,
    status: str = CompletionStatus.DONE,
) -> CareScheduleCompletion:
    """ToDo を「完了（または skipped/pending）」としてマークする。

    :param log: ケアログから完了マークを行う場合の参照ログ
    :param bonsai: 対象盆栽（species_task / schedule のときに付与すると検索が楽）
    :param status: ``done`` / ``skipped`` / ``pending``
    """

    month_start = date(year_month.year, year_month.month, 1)

    # bonsai が未指定で source_type=schedule のときは、schedule.bonsai を埋める
    if bonsai is None and source_type == CompletionSourceType.SCHEDULE:
        # source_ref は "schedule:{schedule_id}" 形式
        prefix = "schedule:"
        if source_ref.startswith(prefix):
            schedule_id = source_ref[len(prefix) :]
            sched = (
                CareSchedule.objects.filter(id=schedule_id, user=user)
                .select_related("bonsai")
                .first()
            )
            if sched is not None:
                bonsai = sched.bonsai

    defaults: dict[str, Any] = {
        "status": status,
        "completed_at": timezone.now(),
        "log": log,
        "bonsai": bonsai,
    }
    completion, _created = CareScheduleCompletion.objects.update_or_create(
        user=user,
        source_type=source_type,
        source_ref=source_ref,
        year_month=month_start,
        defaults=defaults,
    )
    return completion


# ---------------------------------------------------------------------------
# 月次サマリー / 年間ビュー
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class MonthlySummary:
    """1 か月分の ToDo 集計（年間スケジュール・月末レビューで共用）。"""

    year_month: date
    total: int
    done: int
    task_type_counts: dict[str, int]
    todos: list[Todo]

    @property
    def pending(self) -> int:
        return self.total - self.done

    @property
    def task_type_breakdown(self) -> list[tuple[str, int]]:
        """(作業種別ラベル, 件数) を件数の多い順に返す。

        月次アドバイスの ``category`` など ``TaskType`` に無い値は
        そのまま値を表示する。
        """
        merged: dict[str, int] = {}
        for task_type, count in self.task_type_counts.items():
            try:
                label = str(TaskType(task_type).label)
            except ValueError:
                label = task_type
            # 生値が違っても同じラベルになるもの（例: "repotting" と "植え替え"）は合算する
            merged[label] = merged.get(label, 0) + count
        breakdown = list(merged.items())
        breakdown.sort(key=lambda item: (-item[1], item[0]))
        return breakdown

    @property
    def completion_rate(self) -> int:
        """完了率（0〜100 の整数）。ToDo が 0 件なら 0 を返す。"""
        if self.total == 0:
            return 0
        return round(self.done * 100 / self.total)


def summarize_monthly_todos(
    user: AbstractBaseUser,
    year_month: date,
    *,
    todos: list[Todo] | None = None,
) -> MonthlySummary:
    """指定月の ToDo を集計する。

    :param todos: 既に合成済みの ToDo。省略時は ``compose_monthly_todos`` を呼ぶ。
    """
    year_month = date(year_month.year, year_month.month, 1)
    if todos is None:
        todos = compose_monthly_todos(user, year_month)

    task_type_counts: dict[str, int] = {}
    done = 0
    for todo in todos:
        task_type_counts[todo.task_type] = task_type_counts.get(todo.task_type, 0) + 1
        if _is_done(todo):
            done += 1

    return MonthlySummary(
        year_month=year_month,
        total=len(todos),
        done=done,
        task_type_counts=task_type_counts,
        todos=todos,
    )


def compose_yearly_summaries(user: AbstractBaseUser, year: int) -> list[MonthlySummary]:
    """1〜12 月の月次サマリーを返す（年間スケジュール用）。

    実装は月次合成を 12 回呼ぶ素朴なもの。MVP の規模（1 ユーザー数十鉢）では
    十分だが、鉢数が増えた場合はキャッシュや一括クエリ化を検討する。
    """
    return [summarize_monthly_todos(user, date(year, month, 1)) for month in range(1, 13)]


# ---------------------------------------------------------------------------
# 期間指定（今週 / カスタム期間）
# ---------------------------------------------------------------------------
def compose_todos_for_range(
    user: AbstractBaseUser,
    start: date,
    end: date,
) -> list[Todo]:
    """``start``〜``end``（両端含む）に重なる ToDo を返す。

    ToDo の合成単位は月なので、期間がまたぐ各月を合成してから
    ``period_start``/``period_end`` との重なりで絞り込む。
    留守番・短期確認のユースケース（docs/サイトマップ.md §11 P3）向け。
    """
    if end < start:
        start, end = end, start

    todos: list[Todo] = []
    cursor = date(start.year, start.month, 1)
    last_month = date(end.year, end.month, 1)
    while cursor <= last_month:
        todos.extend(compose_monthly_todos(user, cursor))
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)

    def overlaps(todo: Todo) -> bool:
        todo_start = todo.period_start
        todo_end = todo.period_end or todo_start
        if todo_start is None or todo_end is None:
            # 期間が判定できないものは落とさず残す
            return True
        return todo_start <= end and todo_end >= start

    filtered = [todo for todo in todos if overlaps(todo)]
    filtered.sort(
        key=lambda t: (
            _is_done(t),
            t.period_start or date.max,
            (t.bonsai_name or ""),
            t.task_type,
        )
    )
    return filtered


def current_week_range(today: date) -> tuple[date, date]:
    """``today`` を含む週（月曜〜日曜）の範囲を返す。"""
    monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=6)
