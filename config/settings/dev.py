"""Development settings."""

from .base import *  # noqa: F403
from .base import env

DEBUG = True
ALLOWED_HOSTS = ["*"]

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

INTERNAL_IPS = ["127.0.0.1"]

# 開発時はパスワードバリデーションを緩める（任意）
AUTH_PASSWORD_VALIDATORS: list[dict[str, str]] = []

# テスト時にローカル SQLite で完結したい場合のフォールバック
if env("USE_SQLITE_FOR_TESTS", default=False, cast=bool):
    from .base import BASE_DIR

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
