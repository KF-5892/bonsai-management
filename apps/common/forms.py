"""共通フォームユーティリティ。

Tailwind CSS のクラスをまとめて適用するための ``TailwindFormMixin`` を提供する。
ModelForm に多重継承させると、初期化時に各フィールドの widget へ統一的な
CSS クラスを付与する。
"""

from __future__ import annotations

from typing import Any

from django import forms

INPUT_CLASS = (
    "w-full rounded-md border border-gray-300 px-3 py-2 text-sm "
    "focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
)
TEXTAREA_CLASS = INPUT_CLASS + " min-h-[6rem]"
SELECT_CLASS = INPUT_CLASS + " bg-white"
CHECKBOX_CLASS = "h-4 w-4 rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"


class TailwindFormMixin:
    """フォームの widget に Tailwind CSS クラスを自動付与するミックスイン。"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[misc]
        for field in self.fields.values():  # type: ignore[attr-defined]
            widget = field.widget
            existing = widget.attrs.get("class", "")
            if isinstance(widget, forms.Textarea):
                klass = TEXTAREA_CLASS
            elif isinstance(widget, forms.Select | forms.SelectMultiple):
                klass = SELECT_CLASS
            elif isinstance(widget, forms.CheckboxInput):
                klass = CHECKBOX_CLASS
            elif isinstance(widget, forms.ClearableFileInput | forms.FileInput):
                klass = "block w-full text-sm"
            else:
                klass = INPUT_CLASS
            widget.attrs["class"] = (existing + " " + klass).strip()
