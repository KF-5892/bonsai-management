"""accounts アプリのフォーム定義。"""

from __future__ import annotations

from django import forms

from apps.common.forms import TailwindFormMixin
from apps.common.regions import ClimateAdjust

from .models import User


class ProfileForm(TailwindFormMixin, forms.ModelForm):
    """プロフィール編集フォーム（表示名・言語・地域）。

    ``time_zone`` は MVP では Asia/Tokyo 固定のため編集対象に含めない
    （docs/開発前検討事項.md §3.1）。
    """

    class Meta:
        model = User
        fields = ["display_name", "language", "region", "climate_adjust"]

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        # 微調整は任意。未送信なら「補正しない」として扱う
        self.fields["climate_adjust"].required = False

    def clean_climate_adjust(self) -> int:
        value = self.cleaned_data.get("climate_adjust")
        return int(value) if value not in (None, "") else int(ClimateAdjust.NONE)


class NotificationSettingForm(TailwindFormMixin, forms.ModelForm):
    """通知設定フォーム。

    通知の配信自体は Phase 3 で実装するが、設定値の保持は MVP から可能にする。
    """

    class Meta:
        model = User
        fields = ["notification_enabled", "notify_start_time", "notify_end_time"]
        widgets = {
            "notify_start_time": forms.TimeInput(attrs={"type": "time"}),
            "notify_end_time": forms.TimeInput(attrs={"type": "time"}),
        }
