"""メディア（ギャラリー / アップロード / カバー / 削除）と詳細タブのテスト。"""

from __future__ import annotations

from datetime import date, timedelta
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.bonsai.models import BonsaiMedia, BonsaiPlant
from apps.logs.models import CareLog


def _image_file(name: str = "test.jpg") -> SimpleUploadedFile:
    """テスト用の小さな JPEG を生成する。"""
    buf = BytesIO()
    Image.new("RGB", (64, 48), (16, 128, 32)).save(buf, format="JPEG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")


def _plant(user, species=None) -> BonsaiPlant:
    return BonsaiPlant.objects.create(user=user, species=species, name="黒松 太郎")


def test_upload_sets_cover_for_first_media(client, user):
    plant = _plant(user)
    client.force_login(user)
    res = client.post(
        reverse("bonsai:media_upload", kwargs={"pk": plant.pk}),
        {"image_original": _image_file(), "caption": "入手直後"},
    )
    assert res.status_code == 302
    media = BonsaiMedia.objects.get(bonsai=plant)
    plant.refresh_from_db()
    assert plant.cover_media_id == media.pk
    # 派生画像も生成されている
    assert media.image_thumbnail
    assert media.image_medium


def test_gallery_groups_by_year_and_month(client, user):
    plant = _plant(user)
    BonsaiMedia.objects.create(
        bonsai=plant, image_original=_image_file("a.jpg"), taken_at=date(2025, 4, 3)
    )
    BonsaiMedia.objects.create(
        bonsai=plant, image_original=_image_file("b.jpg"), taken_at=date(2026, 5, 9)
    )
    client.force_login(user)

    res = client.get(reverse("bonsai:media_gallery", kwargs={"pk": plant.pk}))
    assert res.status_code == 200
    # 既定は最新年
    assert res.context["selected_year"] == 2026
    assert [m for m, _ in res.context["media_by_month"]] == [5]

    res = client.get(reverse("bonsai:media_gallery", kwargs={"pk": plant.pk}), {"year": "2025"})
    assert res.context["selected_year"] == 2025
    assert [m for m, _ in res.context["media_by_month"]] == [4]


def test_set_cover_and_delete(client, user):
    plant = _plant(user)
    first = BonsaiMedia.objects.create(bonsai=plant, image_original=_image_file("a.jpg"))
    second = BonsaiMedia.objects.create(bonsai=plant, image_original=_image_file("b.jpg"))
    plant.cover_media = first
    plant.save(update_fields=["cover_media"])
    client.force_login(user)

    res = client.post(
        reverse("bonsai:media_set_cover", kwargs={"pk": plant.pk, "media_pk": second.pk})
    )
    assert res.status_code == 302
    plant.refresh_from_db()
    assert plant.cover_media_id == second.pk

    # カバーを削除すると残りの写真へ自動的に付け替わる
    res = client.post(
        reverse("bonsai:media_delete", kwargs={"pk": plant.pk, "media_pk": second.pk})
    )
    assert res.status_code == 302
    plant.refresh_from_db()
    assert plant.cover_media_id == first.pk
    assert BonsaiMedia.objects.filter(bonsai=plant).count() == 1


def test_other_user_cannot_upload(client, user, other_user):
    plant = _plant(user)
    client.force_login(other_user)
    res = client.post(
        reverse("bonsai:media_upload", kwargs={"pk": plant.pk}),
        {"image_original": _image_file()},
    )
    assert res.status_code == 404


def test_detail_tabs_render(client, user, bonsai_species):
    plant = _plant(user, bonsai_species)
    client.force_login(user)
    for tab, _label in [
        ("overview", ""),
        ("logs", ""),
        ("schedules", ""),
        ("media", ""),
        ("repotting", ""),
        ("compare", ""),
    ]:
        res = client.get(reverse("bonsai:detail", kwargs={"pk": plant.pk}), {"tab": tab})
        assert res.status_code == 200
        assert res.context["tab"] == tab

    # 未知のタブは概要にフォールバックする
    res = client.get(reverse("bonsai:detail", kwargs={"pk": plant.pk}), {"tab": "unknown"})
    assert res.context["tab"] == "overview"


def test_repotting_tab_shows_last_and_next_estimate(client, user, bonsai_species):
    """針葉樹は最終植え替えの 3 年後を次回目安として表示する。"""
    plant = _plant(user, bonsai_species)  # bonsai_species は conifer
    performed = timezone.now() - timedelta(days=30)
    CareLog.objects.create(user=user, bonsai=plant, task_type="repotting", performed_at=performed)
    client.force_login(user)
    res = client.get(reverse("bonsai:detail", kwargs={"pk": plant.pk}), {"tab": "repotting"})
    assert res.status_code == 200
    assert res.context["last_repot"] is not None
    expected_year = timezone.localtime(performed).date().year + 3
    assert res.context["next_repot_estimate"].year == expected_year


def test_compare_tab_defaults_to_oldest_and_newest(client, user):
    plant = _plant(user)
    oldest = BonsaiMedia.objects.create(bonsai=plant, image_original=_image_file("a.jpg"))
    BonsaiMedia.objects.create(bonsai=plant, image_original=_image_file("b.jpg"))
    newest = BonsaiMedia.objects.create(bonsai=plant, image_original=_image_file("c.jpg"))
    client.force_login(user)

    res = client.get(reverse("bonsai:detail", kwargs={"pk": plant.pk}), {"tab": "compare"})
    assert res.context["compare_before"].pk == oldest.pk
    assert res.context["compare_after"].pk == newest.pk
