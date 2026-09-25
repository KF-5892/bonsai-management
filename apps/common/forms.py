"""共通フォームユーティリティ。

Tailwind CSS のクラスをまとめて適用するための ``TailwindFormMixin`` を提供する。
ModelForm に多重継承させると、初期化時に各フィールドの widget へ統一的な
CSS クラスを付与する。色は base.html の Material Design 3 トークンに揃える。
"""

from __future__ import annotations

from typing import Any

from django import forms

INPUT_CLASS = (
    "w-full rounded-lg border border-outline-variant bg-surface-container-lowest "
    "px-3 py-2.5 text-sm text-on-surface placeholder-on-surface-variant/60 "
    "focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/40"
)
TEXTAREA_CLASS = INPUT_CLASS + " min-h-[6rem]"
SELECT_CLASS = INPUT_CLASS
CHECKBOX_CLASS = "h-5 w-5 rounded-sm border-outline-variant text-primary focus:ring-primary"
FILE_CLASS = (
    "block w-full text-sm text-on-surface-variant "
    "file:mr-3 file:rounded-full file:border-0 file:bg-secondary-container "
    "file:px-4 file:py-2 file:text-sm file:font-bold file:text-on-secondary-container"
)

# ブラウザの <input type="datetime-local"> が受け付ける唯一の書式。
# Django 既定の "%Y-%m-%d %H:%M:%S" を渡すと初期値が無視され空欄になる。
DATETIME_LOCAL_FORMAT = "%Y-%m-%dT%H:%M"


class DateTimeLocalInput(forms.DateTimeInput):
    """``datetime-local`` 入力。初期値を ISO 8601（T 区切り）で描画する。"""

    input_type = "datetime-local"

    def __init__(self, attrs: dict[str, Any] | None = None) -> None:
        super().__init__(attrs=attrs, format=DATETIME_LOCAL_FORMAT)


class TailwindFormMixin:
    """フォームの widget に Tailwind CSS クラスを自動付与するミックスイン。"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[misc]
        for field in self.fields.values():  # type: ignore[attr-defined]
            widget = field.widget
            existing = widget.attrs.get("class", "")
            if isinstance(widget, forms.Textarea):
                klass = TEXTAREA_CLASS
            elif isinstance(widget, forms.CheckboxSelectMultiple | forms.RadioSelect):
                # 選択肢群は _partials/form_fields.html 側で 1 つずつ描画する。
                # ここで付けたクラスは各 <input> に渡る（ラッパー div には使わない）。
                klass = CHECKBOX_CLASS
            elif isinstance(widget, forms.Select | forms.SelectMultiple):
                klass = SELECT_CLASS
            elif isinstance(widget, forms.CheckboxInput):
                klass = CHECKBOX_CLASS
            elif isinstance(widget, forms.ClearableFileInput | forms.FileInput):
                klass = FILE_CLASS
            else:
                klass = INPUT_CLASS
            widget.attrs["class"] = (existing + " " + klass).strip()
