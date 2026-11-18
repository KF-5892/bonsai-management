"""月次 ToDo 合成サービス。

「今月のやること」を 3 ソースから合成する:

1. 品種マスタ由来 (``BonsaiSpecies.monthly_tasks``)
2. ユーザー個別スケジュール (``CareSchedule``)
3. 月次共通アドバイス (``MonthlyAdvice``)

「見ごろ」（開花・紅葉・実の色付き）は作業ではないので ToDo には含めない。
品種マスタの ``viewing_seasons``（旬単位の範囲、関東〜九州の平野部基準）を
``compose_viewing_seasons`` がユーザーの地域に合わせて補正して返す。
``monthly_tasks`` に残っている ``observation`` も同じ理由で ToDo から除く。

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

from apps.bonsai.models import BonsaiPlant, BonsaiSpecies
from apps.common.regions import (
    ClimateZone,
    ViewingShift,
    is_viewing_supported,
    viewing_offset,
    zone_for_region,
)

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


@dataclass(slots=True)
class ViewingSeason:
    """品種ごとの「見ごろ」1 件分（開花期・紅葉期など）。

    ToDo と違って完了状態を持たない。期間はユーザーの地域に合わせて補正済みの
    旬（``start_index``〜``end_index``、0 = 1 月上旬 … 35 = 12 月下旬）で、
    年をまたぐ場合は ``end_index`` が ``start_index`` より小さくなる。
    ``plants`` はその品種でユーザーが保有している盆栽で、空なら未保有の品種。
    """

    species_id: str
    species_slug: str
    species_name: str
    kind: str
    kind_label: str
    start_index: int
    end_index: int
    period_label: str
    description: str
    plants: list[BonsaiPlant] = field(default_factory=list)

    @property
    def is_owned(self) -> bool:
        return bool(self.plants)


# 品種マスタの monthly_tasks のうち「見ごろ」扱いで ToDo から除く task_type
VIEWING_TASK_TYPE = TaskType.OBSERVATION.value

# 1 年を 36 旬に分ける（各月の上旬・中旬・下旬）
JUN_PER_YEAR = 36
JUN_LABELS = ("上旬", "中旬", "下旬")
VIEWING_KIND_LABELS = {"flower": "花", "foliage": "紅葉", "fruit": "実"}
DEFAULT_VIEWING_KIND_LABEL = "見ごろ"


# ---------------------------------------------------------------------------
# 内部ヘルパー
# ---------------------------------------------------------------------------
def _is_viewing_task(task: dict[str, Any]) -> bool:
    return str(task.get("task_type") or "") == VIEWING_TASK_TYPE


def _task_month(task: Any) -> int | None:
    """monthly_tasks の 1 要素から対象月を取り出す（不正な要素は ``None``）。"""
    if not isinstance(task, dict):
        return None
    try:
        return int(str(task.get("month")))
    except ValueError:
        return None


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
            if _task_month(task) != month:
                continue
            # 見ごろは作業ではないので ToDo に含めない（compose_viewing_seasons が返す）
            if _is_viewing_task(task):
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


# ---------------------------------------------------------------------------
# 見ごろ（開花・紅葉・実の色付きなど）
# ---------------------------------------------------------------------------
def _jun_index(month: Any, period: Any) -> int | None:
    """月と旬（上旬 / 中旬 / 下旬）を 0〜35 の通し番号にする。不正な値は ``None``。"""
    try:
        month_number = int(str(month))
    except ValueError:
        return None
    if not 1 <= month_number <= 12 or period not in JUN_LABELS:
        return None
    return (month_number - 1) * 3 + JUN_LABELS.index(period)


def _jun_label(index: int) -> str:
    return f"{index // 3 + 1}月{JUN_LABELS[index % 3]}"


def format_jun_range(start_index: int, end_index: int) -> str:
    """旬の範囲を「1月下旬〜3月上旬」の形にする（1 旬だけなら「4月中旬」）。"""
    if start_index == end_index:
        return _jun_label(start_index)
    return f"{_jun_label(start_index)}〜{_jun_label(end_index)}"


def _default_shift(kind: str) -> str:
    """shift 省略時の型。花は寒い地域ほど遅く、紅葉・実は早い。"""
    return ViewingShift.SPRING if kind == "flower" else ViewingShift.AUTUMN


def shifted_viewing_range(
    entry: Any,
    zone: ClimateZone = ClimateZone.STANDARD,
    adjust: int = 0,
) -> tuple[int, int] | None:
    """``viewing_seasons`` の 1 要素を、気候区分に合わせてずらした旬の範囲にする。

    :return: ``(start_index, end_index)``。年をまたぐと end < start になる。
        要素が不正なら ``None``。
    """
    if not isinstance(entry, dict):
        return None
    start = _jun_index(entry.get("start_month"), entry.get("start_period"))
    end = _jun_index(entry.get("end_month"), entry.get("end_period"))
    if start is None or end is None:
        return None
    length = (end - start) % JUN_PER_YEAR
    kind = str(entry.get("kind") or "")
    shift = str(entry.get("shift") or _default_shift(kind))
    shifted_start = (start + viewing_offset(zone, shift, adjust)) % JUN_PER_YEAR
    return shifted_start, (shifted_start + length) % JUN_PER_YEAR


def compose_viewing_seasons(
    user: AbstractBaseUser,
    year_month: date,
    *,
    owned_only: bool = True,
) -> list[ViewingSeason]:
    """指定月に見ごろを迎える品種を返す。

    品種マスタの基準値（関東〜九州の平野部）を、ユーザーの地域
    （``User.region`` / ``User.climate_adjust``）の気候区分に合わせて旬単位で
    ずらしてから、指定月と重なるものを選ぶ。沖縄は本州基準のずらしでは
    表せないため空を返す。

    :param owned_only: ``True`` ならユーザーが保有している品種だけ、
        ``False`` なら品種マスタ全体（保有分を先頭に並べる）。
    :return: 保有 → 未保有、月内で早く始まる順、品種名の順。
    """
    zone = zone_for_region(getattr(user, "region", ""))
    if not is_viewing_supported(zone):
        return []
    adjust = int(getattr(user, "climate_adjust", 0) or 0)
    month_first = (year_month.month - 1) * 3

    plants_by_species: dict[str, list[BonsaiPlant]] = {}
    for plant in BonsaiPlant.objects.filter(user=user, species__isnull=False).order_by("name"):
        if plant.species_id is not None:
            plants_by_species.setdefault(plant.species_id, []).append(plant)

    if owned_only:
        species_qs = BonsaiSpecies.objects.filter(id__in=plants_by_species.keys())
    else:
        species_qs = BonsaiSpecies.objects.all()

    found: list[tuple[int, ViewingSeason]] = []
    for species in species_qs:
        for entry in species.viewing_seasons or []:
            shifted = shifted_viewing_range(entry, zone, adjust)
            if shifted is None:
                continue
            start, end = shifted
            length = (end - start) % JUN_PER_YEAR
            # 当月の上旬・中旬・下旬のうち、見ごろに入る最初の旬（無ければ対象外）
            in_month = [
                position
                for position in range(3)
                if (month_first + position - start) % JUN_PER_YEAR <= length
            ]
            if not in_month:
                continue
            kind = str(entry.get("kind") or "")
            found.append(
                (
                    in_month[0],
                    ViewingSeason(
                        species_id=species.id,
                        species_slug=species.slug,
                        species_name=species.name,
                        kind=kind,
                        kind_label=VIEWING_KIND_LABELS.get(kind, DEFAULT_VIEWING_KIND_LABEL),
                        start_index=start,
                        end_index=end,
                        period_label=format_jun_range(start, end),
                        description=str(entry.get("description", "") or ""),
                        plants=plants_by_species.get(species.id, []),
                    ),
                )
            )

    found.sort(key=lambda item: (not item[1].is_owned, item[0], item[1].species_name))
    return [season for _position, season in found]
