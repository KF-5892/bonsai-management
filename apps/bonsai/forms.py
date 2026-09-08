"""bonsai アプリのフォーム定義。"""

from __future__ import annotations

from typing import Any

from django import forms

from apps.common.forms import TailwindFormMixin

from .models import BonsaiPlant, Tag


class BonsaiPlantForm(TailwindFormMixin, forms.ModelForm):
    """盆栽の新規登録・編集フォーム（MVP 最小項目 + タグ）。"""

    class Meta:
        model = BonsaiPlant
        fields = [
            "name",
            "species",
            "acquired_at",
            "health_status",
            "tags",
            "notes",
        ]
        widgets = {
            "acquired_at": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
            "tags": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args: Any, user: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if user is not None:
            # タグは自分が作成したものだけを選択肢にする
            self.fields["tags"].queryset = Tag.objects.filter(user=user)
        self.fields["tags"].required = False


class TagForm(TailwindFormMixin, forms.ModelForm):
    """タグの作成・編集フォーム。"""

    class Meta:
        model = Tag
        fields = ["name", "color"]
        widgets = {
            "color": forms.TextInput(attrs={"placeholder": "#4CAF50"}),
        }

    def __init__(self, *args: Any, user: Any = None, **kwargs: Any) -> None:
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_name(self) -> str:
        """同一ユーザー内でのタグ名重複を DB 制約より前に検出する。"""
        name = self.cleaned_data["name"]
        if self.user is None:
            return name
        qs = Tag.objects.filter(user=self.user, name=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("同じ名前のタグが既に存在します。")
        return name
