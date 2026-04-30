"""schedules ドメインのサービス層。

ToDo 合成（オンデマンド計算 + 完了状態 LEFT JOIN）はここに集約する。
ビュー層は本パッケージの公開関数のみを呼び出すこと。
"""

from __future__ import annotations

from .todos import (
    Todo,
    compose_monthly_todos,
    get_todo_completion_status,
    mark_todo_done,
)

__all__ = [
    "Todo",
    "compose_monthly_todos",
    "get_todo_completion_status",
    "mark_todo_done",
]
