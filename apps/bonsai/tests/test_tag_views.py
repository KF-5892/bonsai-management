"""タグ管理 CRUD のテスト。"""

from __future__ import annotations

from django.urls import reverse

from apps.bonsai.models import BonsaiPlant, Tag


def test_tag_crud_flow(client, user):
    client.force_login(user)

    res = client.post(reverse("bonsai:tag_create"), {"name": "松", "color": "#4CAF50"})
    assert res.status_code == 302
    tag = Tag.objects.get(user=user, name="松")

    res = client.get(reverse("bonsai:tag_list"))
    assert res.status_code == 200
    assert "松" in res.content.decode()

    res = client.post(
        reverse("bonsai:tag_edit", kwargs={"pk": tag.pk}), {"name": "黒松", "color": ""}
    )
    assert res.status_code == 302
    tag.refresh_from_db()
    assert tag.name == "黒松"

    res = client.post(reverse("bonsai:tag_delete", kwargs={"pk": tag.pk}))
    assert res.status_code == 302
    assert not Tag.objects.filter(pk=tag.pk).exists()


def test_tag_name_must_be_unique_per_user(client, user):
    Tag.objects.create(user=user, name="松")
    client.force_login(user)
    res = client.post(reverse("bonsai:tag_create"), {"name": "松", "color": ""})
    assert res.status_code == 200
    assert Tag.objects.filter(user=user, name="松").count() == 1


def test_other_user_cannot_edit_tag(client, user, other_user):
    tag = Tag.objects.create(user=user, name="松")
    client.force_login(other_user)
    res = client.get(reverse("bonsai:tag_edit", kwargs={"pk": tag.pk}))
    assert res.status_code == 404


def test_bonsai_form_accepts_tags(client, user, bonsai_species):
    """盆栽フォームから自分のタグを付与できる。"""
    tag = Tag.objects.create(user=user, name="ベランダ")
    client.force_login(user)
    res = client.post(
        reverse("bonsai:create"),
        {
            "name": "黒松 太郎",
            "species": bonsai_species.pk,
            "health_status": "good",
            "tags": [tag.pk],
            "notes": "",
        },
    )
    assert res.status_code == 302
    plant = BonsaiPlant.objects.get(user=user, name="黒松 太郎")
    assert list(plant.tags.all()) == [tag]
