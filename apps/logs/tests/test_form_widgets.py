"""フォーム描画の回帰テスト（datetime-local の初期値、選択肢群の見た目）。"""

from __future__ import annotations

import re

from django.urls import reverse

from apps.bonsai.forms import BonsaiPlantForm
from apps.bonsai.models import BonsaiPlant, Tag
from apps.logs.forms import BulkCareLogForm, CareLogForm


def test_datetime_local_initial_uses_iso_format(user):
    """ブラウザが受け付ける ``YYYY-MM-DDTHH:MM`` で初期値を描画する。"""
    for form in (CareLogForm(user=user), BulkCareLogForm(user=user)):
        html = str(form["performed_at"])
        match = re.search(r'value="([^"]+)"', html)
        assert match, html
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", match.group(1)), match.group(1)


def test_care_log_form_accepts_datetime_local_value(user, bonsai_species):
    plant = BonsaiPlant.objects.create(user=user, species=bonsai_species, name="黒松 太郎")
    form = CareLogForm(
        data={"bonsai": plant.pk, "task_type": "watering", "performed_at": "2026-04-10T09:30"},
        user=user,
    )
    assert form.is_valid(), form.errors


def test_tag_checkboxes_render_as_option_cards(client, user, bonsai_species):
    """チェックボックス群のラッパーに入力欄用の枠クラスが付かない。"""
    Tag.objects.create(user=user, name="ベランダ")
    form = BonsaiPlantForm(user=user)
    assert "border-outline-variant" in str(form["tags"].subwidgets[0].tag())

    client.force_login(user)
    html = client.get(reverse("bonsai:create")).content.decode()
    assert 'role="group"' in html
    assert 'id="id_tags" class="w-full' not in html
