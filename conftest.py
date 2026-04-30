"""pytest 共通設定。

- pytest-django を利用し、`DJANGO_SETTINGS_MODULE` は pyproject.toml で
  指定済み。
- 全テストでデフォルトで DB を使えるよう ``django_db`` マーカーを自動付与する
  （MVP 段階では DB を触らないユニットテストはほぼ無いため利便性を優先）。
"""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config, items):
    """全テストにデフォルトで `django_db` マーカーを付与する。"""
    del config  # 未使用
    for item in items:
        if "django_db" not in item.keywords:
            item.add_marker(pytest.mark.django_db)


@pytest.fixture
def user(django_user_model):
    """汎用 User fixture。テストごとにユニークな email を生成する。"""
    return django_user_model.objects.create_user(
        email="user@example.com",
        password="testpass1234",
        display_name="テストユーザー",
    )


@pytest.fixture
def other_user(django_user_model):
    """別ユーザー（認可テスト用）。"""
    return django_user_model.objects.create_user(
        email="other@example.com",
        password="testpass1234",
        display_name="別ユーザー",
    )


@pytest.fixture
def bonsai_species(db):
    """簡易な BonsaiSpecies fixture。月別タスクを 1 件含む。"""
    from apps.bonsai.models import BonsaiSpecies, SpeciesCategory

    return BonsaiSpecies.objects.create(
        slug="test-kuromatsu",
        name="テスト黒松",
        scientific_name="Pinus thunbergii",
        category=SpeciesCategory.CONIFER,
        description="テスト用の黒松。",
        monthly_tasks=[
            {
                "month": 5,
                "period": "中旬",
                "task_type": "bud_pinching",
                "description": "新芽の先端を摘む。",
            },
        ],
    )
