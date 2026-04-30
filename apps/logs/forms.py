"""logs アプリのフォーム定義。"""

from __future__ import annotations

from typing import Any

from django import forms

from apps.bonsai.models import BonsaiPlant
from apps.common.forms import TailwindFormMixin

from .models import CareLog, Fertilizer


class CareLogForm(TailwindFormMixin, forms.ModelForm):
    """作業ログ作成・編集フォーム。

    - ``bonsai`` は自分の盆栽だけに絞る
    - ``fertilizer`` は共通マスタ＋自分の登録のみ
    """

    class Meta:
        model = CareLog
        fields = [
            "bonsai",
            "task_type",
            "task_type_other",
            "performed_at",
            "weather",
            "temperature_c",
            "fertilizer",
            "fertilizer_amount",
            "health_evaluation",
            "notes",
            "photo",
        ]
        widgets = {
            "performed_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args: Any, user: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["bonsai"].queryset = BonsaiPlant.objects.filter(user=user)
            self.fields["fertilizer"].queryset = Fertilizer.objects.visible_to(user)
        # 任意項目を表現するため empty_label を上書き
        self.fields["fertilizer"].required = False
