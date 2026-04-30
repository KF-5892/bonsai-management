"""bonsai アプリのフォーム定義。"""

from __future__ import annotations

from django import forms

from apps.common.forms import TailwindFormMixin

from .models import BonsaiPlant


class BonsaiPlantForm(TailwindFormMixin, forms.ModelForm):
    """盆栽の新規登録・編集フォーム（MVP 最小項目）。"""

    class Meta:
        model = BonsaiPlant
        fields = [
            "name",
            "species",
            "acquired_at",
            "health_status",
            "notes",
        ]
        widgets = {
            "acquired_at": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }
