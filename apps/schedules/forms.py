"""schedules アプリのフォーム定義。"""

from __future__ import annotations

from typing import Any

from django import forms

from apps.bonsai.models import BonsaiPlant
from apps.common.forms import TailwindFormMixin

from .models import CareSchedule


class CareScheduleForm(TailwindFormMixin, forms.ModelForm):
    """個別スケジュール作成・編集フォーム。"""

    class Meta:
        model = CareSchedule
        fields = [
            "bonsai",
            "task_type",
            "title",
            "notes",
            "repeat_type",
            "start_date",
            "next_run_at",
            "is_active",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "next_run_at": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args: Any, user: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["bonsai"].queryset = BonsaiPlant.objects.filter(user=user)
