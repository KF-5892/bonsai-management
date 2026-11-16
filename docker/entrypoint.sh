#!/usr/bin/env bash
# コンテナ起動時に DB マイグレーションを適用してから gunicorn を起動する。
# 単一インスタンス運用（Render Starter など）を前提にしている。複数インスタンスで
# 同時起動する構成にしたら、マイグレーションはデプロイ前フック側へ移すこと。
set -euo pipefail

python manage.py migrate --noinput

# PORT は Render 等の PaaS が注入する。WEB_CONCURRENCY でワーカー数を調整できる
exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --threads 4 \
  --timeout 60 \
  --access-logfile - \
  --error-logfile -
