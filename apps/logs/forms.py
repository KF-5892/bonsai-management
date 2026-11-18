"""logs アプリのフォーム定義。"""

from __future__ import annotations

from typing import Any

from django import forms
from django.utils import timezone

from apps.bonsai.models import BonsaiPlant, TaskType
from apps.common.forms import DateTimeLocalInput, TailwindFormMixin

from .models import (
    CareLog,
    CareLogExtraTask,
    Fertilizer,
    HealthEvaluation,
    PestControlPurpose,
    Pesticide,
    Weather,
    split_task_types,
)

PEST_CONTROL_FIELDS = (
    "pest_control_purposes",
    "pesticides",
    "pesticide_dilution",
    "spreader_used",
    "pest_target",
)


class CareLogForm(TailwindFormMixin, forms.ModelForm):
    """作業ログ作成・編集フォーム。

    - ``bonsai`` は自分の盆栽だけに絞る
    - ``fertilizer`` は共通マスタ＋自分の登録のみ
    - ``task_type`` は複数選択。モデルの ``task_type``（主となる種別）と
      ``CareLogExtraTask``（2 つ目以降）に分けて保存する
    """

    task_type = forms.MultipleChoiceField(
        label="作業種別",
        choices=TaskType.choices,
        widget=forms.CheckboxSelectMultiple,
        help_text="同時に行った作業は複数選べます。",
        error_messages={"required": "作業種別を 1 つ以上選んでください。"},
    )

    pest_control_purposes = forms.MultipleChoiceField(
        label="消毒の目的",
        choices=PestControlPurpose.choices,
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )

    field_order = [
        "bonsai",
        "task_type",
        "task_type_other",
        "performed_at",
        "weather",
        "temperature_c",
        "fertilizer",
        "fertilizer_amount",
        *PEST_CONTROL_FIELDS,
    ]

    class Meta:
        model = CareLog
        # task_type は複数選択の独自フィールドで扱うため、ここには含めない
        fields = [
            "bonsai",
            "task_type_other",
            "performed_at",
            "weather",
            "temperature_c",
            "fertilizer",
            "fertilizer_amount",
            "pesticides",
            "pesticide_dilution",
            "spreader_used",
            "pest_target",
            "health_evaluation",
            "notes",
            "photo",
        ]
        widgets = {
            "pesticides": forms.CheckboxSelectMultiple,
            "performed_at": DateTimeLocalInput(),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args: Any, user: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["bonsai"].queryset = BonsaiPlant.objects.filter(user=user)
            self.fields["fertilizer"].queryset = Fertilizer.objects.visible_to(user)
            self.fields["pesticides"].queryset = Pesticide.objects.visible_to(user)
        # 任意項目は「未設定」を明示し、必須の選択肢は "---------" ではなく促す文言にする
        self.fields["bonsai"].empty_label = "選択してください"
        self.fields["fertilizer"].required = False
        self.fields["fertilizer"].empty_label = "未設定"
        self.fields["weather"].choices = [("", "未設定"), *Weather.choices]
        self.fields["health_evaluation"].choices = [("", "未設定"), *HealthEvaluation.choices]
        # 主キーは UUID の既定値で保存前から入るため、新規かどうかは _state で判定する
        if not self.instance._state.adding:
            self.initial.setdefault("task_type", self.instance.task_type_values)
            self.initial.setdefault(
                "pest_control_purposes", self.instance.pest_control_purposes or []
            )
        elif isinstance(self.initial.get("task_type"), str):
            # ``?task_type=`` のプリフィルは 1 つだけ渡ってくる
            self.initial["task_type"] = [self.initial["task_type"]]
        if not self.instance.pk and not self.is_bound:
            self.initial.setdefault(
                "performed_at", timezone.localtime().replace(second=0, microsecond=0)
            )

    def clean(self) -> dict[str, Any]:
        data = super().clean() or {}
        selected = data.get("task_type") or []
        # 選んでいない種別に紐づく項目は残さない
        if TaskType.OTHER not in selected:
            data["task_type_other"] = ""
        if TaskType.FERTILIZING not in selected:
            data["fertilizer"] = None
            data["fertilizer_amount"] = ""
        if TaskType.PEST_CONTROL not in selected:
            data["pest_control_purposes"] = []
            data["pesticides"] = Pesticide.objects.none()
            data["pesticide_dilution"] = ""
            data["spreader_used"] = False
            data["pest_target"] = ""
        return data

    def save(self, commit: bool = True) -> CareLog:
        primary, _extras = split_task_types(self.cleaned_data["task_type"])
        self.instance.task_type = primary
        self.instance.pest_control_purposes = list(self.cleaned_data["pest_control_purposes"])
        return super().save(commit=commit)

    def _save_m2m(self) -> None:
        super()._save_m2m()  # type: ignore[misc]
        self.instance.set_task_types(self.cleaned_data["task_type"])


class FertilizerMasterForm(TailwindFormMixin, forms.ModelForm):
    """肥料マスタ（ユーザー個別）の登録・編集フォーム。

    共通マスタ（``user`` が NULL）は Django Admin で管理し、本フォームでは
    常にログインユーザー所有のレコードだけを作成・編集する。
    """

    class Meta:
        model = Fertilizer
        fields = ["name", "form_type", "n", "p", "k", "is_organic", "note"]
        widgets = {
            "note": forms.Textarea(attrs={"rows": 3}),
        }


class PesticideMasterForm(TailwindFormMixin, forms.ModelForm):
    """薬剤マスタ（ユーザー個別）の登録・編集フォーム。

    共通マスタ（``user`` が NULL）は Django Admin で管理する。
    """

    class Meta:
        model = Pesticide
        fields = ["name", "category", "formulation", "default_dilution", "note"]
        widgets = {
            "note": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["formulation"].choices = [
            ("", "未設定"),
            *[c for c in self.fields["formulation"].choices if c[0]],
        ]


class BulkCareLogForm(TailwindFormMixin, forms.Form):
    """複数の盆栽に同一作業をまとめて記録するフォーム（多鉢運用向け）。

    ``CareLog`` の共通項目だけを持ち、選択された盆栽の数だけログを作成する
    （docs/サイトマップ.md §11-3）。
    """

    bonsai = forms.ModelMultipleChoiceField(
        label="対象の盆栽",
        queryset=BonsaiPlant.objects.none(),
        widget=forms.CheckboxSelectMultiple,
    )
    task_type = forms.MultipleChoiceField(
        label="作業種別",
        choices=TaskType.choices,
        widget=forms.CheckboxSelectMultiple,
        help_text="同時に行った作業は複数選べます。",
        error_messages={"required": "作業種別を 1 つ以上選んでください。"},
    )
    performed_at = forms.DateTimeField(label="実施日時", widget=DateTimeLocalInput())
    # 任意項目は空の選択肢を先頭に置く（無いと先頭の値が常に送信されてしまう）
    weather = forms.ChoiceField(
        label="天候", choices=[("", "未設定"), *Weather.choices], required=False
    )
    temperature_c = forms.DecimalField(
        label="気温 (℃)", max_digits=4, decimal_places=1, required=False
    )
    fertilizer = forms.ModelChoiceField(
        label="使用した肥料", queryset=Fertilizer.objects.none(), required=False
    )
    fertilizer_amount = forms.CharField(label="肥料の量", max_length=40, required=False)
    pest_control_purposes = forms.MultipleChoiceField(
        label="消毒の目的",
        choices=PestControlPurpose.choices,
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
    pesticides = forms.ModelMultipleChoiceField(
        label="使用した薬剤",
        queryset=Pesticide.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
    pesticide_dilution = forms.CharField(
        label="希釈倍率", max_length=40, required=False, help_text="自由入力（例: 1000倍、原液）"
    )
    spreader_used = forms.BooleanField(label="展着剤を使用", required=False)
    pest_target = forms.CharField(
        label="対象の病害虫",
        max_length=80,
        required=False,
        help_text="自由入力（例: アブラムシ、うどんこ病）",
    )
    health_evaluation = forms.ChoiceField(
        label="状態評価", choices=[("", "未設定"), *HealthEvaluation.choices], required=False
    )
    notes = forms.CharField(label="メモ", widget=forms.Textarea(attrs={"rows": 3}), required=False)

    def __init__(self, *args: Any, user: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["bonsai"].queryset = BonsaiPlant.objects.filter(user=user)
            self.fields["fertilizer"].queryset = Fertilizer.objects.visible_to(user)
            self.fields["pesticides"].queryset = Pesticide.objects.visible_to(user)
        self.fields["performed_at"].initial = timezone.localtime().replace(second=0, microsecond=0)

    def create_logs(self, user: Any) -> list[CareLog]:
        """選択された盆栽ごとに ``CareLog`` を作成して返す。"""
        data = self.cleaned_data
        primary, extras = split_task_types(data["task_type"])
        selected = {primary, *extras}
        fertilizing = TaskType.FERTILIZING in selected
        # 消毒を選んでいないときは、消毒の付帯項目を保存しない
        pest_control = TaskType.PEST_CONTROL in selected
        pesticides = list(data.get("pesticides") or []) if pest_control else []
        logs = [
            CareLog(
                user=user,
                bonsai=plant,
                task_type=primary,
                performed_at=data["performed_at"],
                weather=data.get("weather") or "",
                temperature_c=data.get("temperature_c"),
                fertilizer=data.get("fertilizer") if fertilizing else None,
                fertilizer_amount=(data.get("fertilizer_amount") or "") if fertilizing else "",
                pest_control_purposes=(
                    list(data.get("pest_control_purposes") or []) if pest_control else []
                ),
                pesticide_dilution=(data.get("pesticide_dilution") or "") if pest_control else "",
                spreader_used=bool(data.get("spreader_used")) if pest_control else False,
                pest_target=(data.get("pest_target") or "") if pest_control else "",
                health_evaluation=data.get("health_evaluation") or None,
                notes=data.get("notes") or "",
            )
            for plant in data["bonsai"]
        ]
        created = CareLog.objects.bulk_create(logs)
        CareLogExtraTask.objects.bulk_create(
            CareLogExtraTask(log=log, task_type=value) for log in created for value in extras
        )
        through = CareLog.pesticides.through
        through.objects.bulk_create(
            through(carelog_id=log.pk, pesticide_id=pesticide.pk)
            for log in created
            for pesticide in pesticides
        )
        return created
