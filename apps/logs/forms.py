"""logs アプリのフォーム定義。"""

from __future__ import annotations

from typing import Any

from django import forms
from django.utils import timezone

from apps.bonsai.models import BonsaiPlant, TaskType
from apps.common.forms import DateTimeLocalInput, TailwindFormMixin

from .models import CareLog, Fertilizer, HealthEvaluation, Weather


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
            "performed_at": DateTimeLocalInput(),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args: Any, user: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["bonsai"].queryset = BonsaiPlant.objects.filter(user=user)
            self.fields["fertilizer"].queryset = Fertilizer.objects.visible_to(user)
        # 任意項目は「未設定」を明示し、必須の選択肢は "---------" ではなく促す文言にする
        self.fields["bonsai"].empty_label = "選択してください"
        self.fields["fertilizer"].required = False
        self.fields["fertilizer"].empty_label = "未設定"
        self.fields["weather"].choices = [("", "未設定"), *Weather.choices]
        self.fields["health_evaluation"].choices = [("", "未設定"), *HealthEvaluation.choices]
        if not self.instance.pk and not self.is_bound:
            self.initial.setdefault(
                "performed_at", timezone.localtime().replace(second=0, microsecond=0)
            )


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
    task_type = forms.ChoiceField(label="作業種別", choices=TaskType.choices)
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
    health_evaluation = forms.ChoiceField(
        label="状態評価", choices=[("", "未設定"), *HealthEvaluation.choices], required=False
    )
    notes = forms.CharField(label="メモ", widget=forms.Textarea(attrs={"rows": 3}), required=False)

    def __init__(self, *args: Any, user: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["bonsai"].queryset = BonsaiPlant.objects.filter(user=user)
            self.fields["fertilizer"].queryset = Fertilizer.objects.visible_to(user)
        self.fields["performed_at"].initial = timezone.localtime().replace(second=0, microsecond=0)

    def create_logs(self, user: Any) -> list[CareLog]:
        """選択された盆栽ごとに ``CareLog`` を作成して返す。"""
        data = self.cleaned_data
        logs = [
            CareLog(
                user=user,
                bonsai=plant,
                task_type=data["task_type"],
                performed_at=data["performed_at"],
                weather=data.get("weather") or "",
                temperature_c=data.get("temperature_c"),
                fertilizer=data.get("fertilizer"),
                fertilizer_amount=data.get("fertilizer_amount") or "",
                health_evaluation=data.get("health_evaluation") or None,
                notes=data.get("notes") or "",
            )
            for plant in data["bonsai"]
        ]
        return CareLog.objects.bulk_create(logs)
