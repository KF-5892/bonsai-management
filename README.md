# bonsai-management

盆栽の年間作業（品種ごとの月別推奨作業）と、鉢ごとの記録・写真をまとめて管理する Web アプリ。
Django 5 + PostgreSQL、モバイル優先の UI（Tailwind CSS / Alpine.js / htmx）。

- 画面構成: [docs/サイトマップ.md](docs/サイトマップ.md)
- 技術要件: [docs/技術要件書.md](docs/技術要件書.md)
- 本番デプロイ: [docs/デプロイ手順.md](docs/デプロイ手順.md)（Render + Supabase）
- 画面プレビュー（静的）: `docs/preview/index.html`

## ローカル開発

```bash
uv sync                       # Python 依存
npm install && npm run build  # Tailwind CSS のビルドと Alpine / htmx のコピー
cp .env.example .env          # DATABASE_URL などを設定
docker compose up -d          # PostgreSQL 16
uv run python manage.py migrate
uv run python manage.py loaddata bonsai_species_seed monthly_advices_seed
uv run python manage.py runserver
```

テンプレートや `apps/**/*.py` のクラス名を変えたら `npm run build`（開発中は `npm run watch:css`）で
`static/css/tailwind.css` を更新してコミットする。CI が差分をチェックする。

デモデータ入りで全画面を確認したいときは `uv run python tools/export_static_preview.py`
（SQLite に投入して `docs/preview/` を再生成。ログイン: `demo@example.com` / `demo-preview-pass`）。

## テスト・Lint

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
```
