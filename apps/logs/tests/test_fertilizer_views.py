"""肥料マスタ CRUD のテスト。"""

from __future__ import annotations

from django.urls import reverse

from apps.logs.models import Fertilizer


def test_fertilizer_crud_flow(client, user):
    client.force_login(user)

    res = client.post(
        reverse("logs:fertilizer_create"),
        {"name": "油かす", "form_type": "solid", "n": "5", "p": "3", "k": "1", "note": ""},
    )
    assert res.status_code == 302
    fertilizer = Fertilizer.objects.get(user=user, name="油かす")

    res = client.get(reverse("logs:fertilizer_list"))
    assert res.status_code == 200
    assert "油かす" in res.content.decode()

    res = client.post(
        reverse("logs:fertilizer_edit", kwargs={"pk": fertilizer.pk}),
        {"name": "油かす（中粒）", "form_type": "solid", "note": ""},
    )
    assert res.status_code == 302
    fertilizer.refresh_from_db()
    assert fertilizer.name == "油かす（中粒）"

    res = client.post(reverse("logs:fertilizer_delete", kwargs={"pk": fertilizer.pk}))
    assert res.status_code == 302
    assert not Fertilizer.objects.filter(pk=fertilizer.pk).exists()


def test_common_fertilizer_is_listed_but_not_editable(client, user):
    """共通マスタは一覧に出るが編集はできない（Admin 管理）。"""
    common = Fertilizer.objects.create(name="共通肥料", form_type="liquid")
    client.force_login(user)

    res = client.get(reverse("logs:fertilizer_list"))
    assert "共通肥料" in res.content.decode()

    res = client.get(reverse("logs:fertilizer_edit", kwargs={"pk": common.pk}))
    assert res.status_code == 404
