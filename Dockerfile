# syntax=docker/dockerfile:1.7
# 本番用イメージ。Render（Docker ランタイム）/ Fly.io / Cloud Run など、
# コンテナを動かせる PaaS ならどこでも同じイメージで動く。
#
#   ステージ 1: Tailwind CSS のビルドと Alpine / htmx のコピー（Node）
#   ステージ 2: Python 実行環境（uv で依存を固定、gunicorn で起動）

# ---------------------------------------------------------------------------
# 1. フロントエンド資産
# ---------------------------------------------------------------------------
FROM node:22-slim AS assets
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY tailwind.config.js ./
COPY tools/copy_vendor_js.mjs ./tools/
COPY static ./static
COPY templates ./templates
COPY apps ./apps
RUN npm run build

# ---------------------------------------------------------------------------
# 2. アプリケーション
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# uv は公式イメージからバイナリだけ取り込む（CI と同じ 0.8 系）
COPY --from=ghcr.io/astral-sh/uv:0.8.13 /uv /uvx /bin/

# 依存のみ先にインストールしてレイヤーキャッシュを効かせる
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# アプリ本体とビルド済み資産
COPY . .
COPY --from=assets /app/static/css/tailwind.css ./static/css/tailwind.css
COPY --from=assets /app/static/js ./static/js

# 静的ファイルを収集（WhiteNoise が配信）。ビルド時はダミーの環境変数で十分
RUN DJANGO_SETTINGS_MODULE=config.settings.prod \
    DJANGO_SECRET_KEY=build-only-not-a-secret \
    DJANGO_DEBUG=False \
    DJANGO_ALLOWED_HOSTS=localhost \
    DATABASE_URL=sqlite:////tmp/build.sqlite3 \
    USE_S3_STORAGE=False \
    python manage.py collectstatic --noinput

RUN useradd --create-home --uid 1000 app && chown -R app:app /app
USER app

EXPOSE 8000
ENTRYPOINT ["/app/docker/entrypoint.sh"]
