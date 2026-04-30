"""アプリ横断で使う共通ユーティリティ。

MVP の主キーは UUIDv7（`uuid_extensions.uuid7`）を採用している
（決定: docs/開発前検討事項.md §3.1, docs/技術要件書.md）。
URL 列挙攻撃の防御 + 時系列ソート可能性の両立が目的。
"""

from __future__ import annotations

import uuid_extensions


def uuid7_str() -> str:
    """新しい UUIDv7 を文字列で返す。

    Django の `CharField(primary_key=True, default=...)` から呼べるよう
    引数なしで callable として使える形にしている。
    """
    return str(uuid_extensions.uuid7())
