"""実装済み Django 画面をデモデータ付きで静的 HTML へ書き出す。

GitHub Pages で「実装の見た目」をログイン不要・サーバー不要で確認するための
プレビュー生成スクリプト。Django テストクライアントで各画面を GET し、
レスポンス HTML を ``docs/preview/`` 配下へ保存したうえで、ページ間リンクを
静的ファイル名へ書き換える。

注意:
- これは静的スナップショットであり、フォーム送信・HTMX・検索などの
  動的機能は動作しない（閲覧専用）。
- Tailwind / HTMX / Alpine / Material Symbols は CDN 参照のまま残すため、
  閲覧者のブラウザ側でスタイルが適用される。

実行: ``uv run python tools/export_static_preview.py``
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# --- Django 設定（SQLite・DEBUG）-------------------------------------------
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
os.environ.setdefault("USE_SQLITE_FOR_TESTS", "True")
os.environ.setdefault("DJANGO_DEBUG", "True")
os.environ.setdefault("DJANGO_SECRET_KEY", "preview-only-key")

import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402
from django.test import Client  # noqa: E402
from django.utils import timezone  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = BASE_DIR / "docs" / "preview"


def reset_db() -> None:
    db = BASE_DIR / "db.sqlite3"
    if db.exists():
        db.unlink()
    call_command("migrate", "--noinput", verbosity=0)
    call_command("collectstatic", "--noinput", "--clear", verbosity=0)
    call_command("loaddata", "bonsai_species_seed", verbosity=0)
    call_command("loaddata", "monthly_advices_seed", verbosity=0)


def seed_demo_data():
    from django.contrib.auth import get_user_model

    from apps.articles.models import (
        ArticleSpeciesRelation,
        ArticleStatus,
        HelpArticle,
    )
    from apps.bonsai.models import BonsaiPlant, BonsaiSpecies, HealthStatus
    from apps.logs.models import CareLog, HealthEvaluation, Weather
    from apps.schedules.models import CareSchedule, RepeatType, TaskType

    User = get_user_model()
    user = User.objects.create_user(
        email="demo@example.com",
        password="demo-preview-pass",  # noqa: S106
        display_name="デモ太郎",
    )

    species = {s.slug: s for s in BonsaiSpecies.objects.all()}
    kuro = species.get("kuromatsu")
    momiji = species.get("momiji") or species.get("yamamomiji")
    # フォールバック: 任意の品種を割り当てる
    others = list(species.values())

    today = timezone.localdate()

    plants = []
    plant_specs = [
        ("黒松 太郎", kuro or (others[0] if others else None), HealthStatus.GOOD,
         date(2021, 5, 10), "実生3年。芽摘みで樹勢を調整中。"),
        ("もみじ 花子", momiji or (others[1] if len(others) > 1 else None), HealthStatus.WATCH,
         date(2022, 3, 20), "葉やけ気味。半日陰に移動して様子見。"),
        ("五葉松 次郎", species.get("goyomatsu") or (others[2] if len(others) > 2 else None),
         HealthStatus.GOOD, date(2020, 11, 1), "棚の主役。針金で枝順を整えた。"),
    ]
    for name, sp, health, acquired, notes in plant_specs:
        plants.append(
            BonsaiPlant.objects.create(
                user=user, species=sp, name=name,
                health_status=health, acquired_at=acquired, notes=notes,
            )
        )

    # スケジュール（当月に次回予定が来るもの）
    CareSchedule.objects.create(
        bonsai=plants[0], user=user, task_type=TaskType.WATERING,
        title="黒松の水やり", repeat_type=RepeatType.DAILY,
        repeat_rule={"interval": 1}, start_date=today - timedelta(days=30),
        next_run_at=today, is_active=True, notes="朝夕の2回。",
    )
    CareSchedule.objects.create(
        bonsai=plants[1], user=user, task_type=TaskType.FERTILIZING,
        title="もみじの置き肥", repeat_type=RepeatType.MONTHLY,
        repeat_rule={"interval": 1, "bymonthday": 1},
        start_date=today - timedelta(days=60),
        next_run_at=today + timedelta(days=3), is_active=True,
    )

    # 作業ログ
    log_specs = [
        (plants[0], TaskType.WATERING, Weather.SUNNY, 22.5, "たっぷり灌水。", HealthEvaluation.GOOD, 1),
        (plants[0], TaskType.BUD_PINCHING, Weather.CLOUDY, 20.0,
         "強い芽を元から摘んだ。", HealthEvaluation.VERY_GOOD, 5),
        (plants[1], TaskType.OBSERVATION, Weather.SUNNY, 24.0,
         "葉先が少し茶色い。風通しを改善。", HealthEvaluation.NORMAL, 8),
        (plants[2], TaskType.WIRING, Weather.CLOUDY, 18.0,
         "下枝にアルミ線をかけた。", HealthEvaluation.GOOD, 12),
    ]
    first_log = None
    for bonsai, tt, weather, temp, note, ev, days_ago in log_specs:
        log = CareLog.objects.create(
            bonsai=bonsai, user=user, task_type=tt, weather=weather,
            temperature_c=temp, notes=note, health_evaluation=ev,
            performed_at=timezone.now() - timedelta(days=days_ago),
        )
        first_log = first_log or log

    # お役立ち記事（公開）
    article_specs = [
        ("bonsai-watering-basics", "盆栽の水やり入門",
         "盆栽管理で最も大切な日課が水やりです。",
         "## 基本\n\n- 土の表面が乾いたらたっぷりと\n- 朝夕の2回が目安\n\n### 季節の注意\n\n夏場は乾きやすいので回数を増やします。",
         kuro),
        ("repotting-guide", "植え替えの基本とタイミング",
         "2〜3年に一度の植え替えで根詰まりを防ぎます。",
         "## 適期\n\n芽が動き出す直前の春が基本です。\n\n```\n古い土を1/3落とす\n```\n",
         None),
        ("pest-control", "病害虫の予防と対策",
         "早期発見・早期対処が肝心です。",
         "## よくある害虫\n\n| 害虫 | 対策 |\n|---|---|\n| アブラムシ | 薬剤散布 |\n| ハダニ | 葉水 |\n",
         momiji),
    ]
    for slug, title, summary, body, rel_sp in article_specs:
        art = HelpArticle.objects.create(
            title=title, slug=slug, summary=summary, body=body,
            status=ArticleStatus.PUBLISHED, author=user,
            published_at=timezone.now() - timedelta(days=5),
        )
        if rel_sp:
            ArticleSpeciesRelation.objects.create(article=art, species=rel_sp, relevance=10)

    return user, plants, list(species.values())


def main() -> None:
    reset_db()
    user, plants, all_species = seed_demo_data()

    from apps.articles.models import HelpArticle

    client = Client(raise_request_exception=False)
    client.force_login(user)

    # path -> 出力ファイル名 のマップ
    pages: dict[str, str] = {
        "/": "home.html",
        "/schedules/": "schedules.html",
        "/logs/": "logs.html",
        "/articles/": "articles.html",
        "/bonsai/new/": "bonsai_form.html",
        "/schedules/new/": "schedule_form.html",
        "/logs/new/": "log_form.html",
    }
    # 詳細ページのファイル名は連番にする（UUID は毎回変わり差分が荒れるため）。
    for i, p in enumerate(plants, start=1):
        pages[f"/bonsai/{p.pk}/"] = f"bonsai_{i}.html"
    for s in all_species:
        pages[f"/species/{s.slug}/"] = f"species_{s.slug}.html"
    for a in HelpArticle.objects.all():
        pages[f"/articles/{a.slug}/"] = f"article_{a.slug}.html"
    from apps.logs.models import CareLog

    for i, log in enumerate(CareLog.objects.order_by("performed_at"), start=1):
        pages[f"/logs/{log.pk}/"] = f"log_{i}.html"

    # ログアウト状態のページ
    public_pages = {
        "/accounts/login/": "login.html",
        "/accounts/signup/": "signup.html",
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rendered: dict[str, str] = {}  # filename -> html
    for path, fname in pages.items():
        resp = client.get(path)
        if resp.status_code != 200:
            print(f"  SKIP {path} -> {resp.status_code}")
            continue
        rendered[fname] = resp.content.decode("utf-8")

    anon = Client(raise_request_exception=False)
    for path, fname in public_pages.items():
        resp = anon.get(path)
        if resp.status_code != 200:
            print(f"  SKIP {path} -> {resp.status_code}")
            continue
        rendered[fname] = resp.content.decode("utf-8")

    full_map = {**pages, **public_pages, "/accounts/logout/": "#"}

    # CSS をコピー
    shutil.copyfile(BASE_DIR / "static" / "css" / "app.css", OUT_DIR / "app.css")

    # リンク書き換え
    def rewrite(html: str) -> str:
        # 静的 CSS（ハッシュ付き含む）-> app.css
        html = re.sub(r'/static/css/app(\.[0-9a-f]+)?\.css', "app.css", html)
        # 既知パス -> 静的ファイル名（長いパス優先）
        for path in sorted(full_map, key=len, reverse=True):
            fname = full_map[path]
            html = html.replace(f'"{path}"', f'"{fname}"')
            html = re.sub(rf'"{re.escape(path)}\?[^"]*"', f'"{fname}"', html)
            html = re.sub(rf'"{re.escape(path)}#[^"]*"', f'"{fname}"', html)
        # ルート "/" を home.html へ
        html = re.sub(r'(href|action)="/"', r'\1="home.html"', html)
        # 残った同一オリジンの絶対リンク（edit/delete/complete 等）は無効化
        html = re.sub(r'(href|action)="/[^"]*"', r'\1="#"', html)
        return html

    for fname, html in rendered.items():
        (OUT_DIR / fname).write_text(rewrite(html), encoding="utf-8")

    write_gallery(rendered, plants, all_species)
    print(f"OK: {len(rendered)} pages -> {OUT_DIR}")


def write_gallery(rendered, plants, all_species) -> None:
    """プレビューのトップ（ギャラリー）を生成する。"""

    def link(fname: str, label: str) -> str:
        exists = fname in rendered
        if not exists:
            return f'<li><span style="color:#9ca3af">{label}（生成スキップ）</span></li>'
        return f'<li><a href="{fname}">{label}</a></li>'

    plant_links = "\n".join(
        link(f"bonsai_{i}.html", f"盆栽詳細 — {p.name}") for i, p in enumerate(plants, start=1)
    )
    species_links = "\n".join(
        link(f"species_{s.slug}.html", f"品種詳細 — {s.name}") for s in all_species[:8]
    )
    article_files = sorted(f for f in rendered if f.startswith("article_"))
    article_links = "\n".join(link(f, f.replace("article_", "").replace(".html", "")) for f in article_files)
    log_files = sorted(f for f in rendered if f.startswith("log_"))
    log_links = "\n".join(link(f, "作業ログ詳細") for f in log_files)

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>盆栽管理アプリ — 実装UIプレビュー</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ font-family: system-ui, "Hiragino Sans", "Noto Sans JP", sans-serif;
         margin: 0; background: #ecfdf5; color: #111827; line-height: 1.6; }}
  header {{ background: #047857; color: #fff; padding: 24px 20px; }}
  header h1 {{ margin: 0 0 4px; font-size: 1.4rem; }}
  header p {{ margin: 0; opacity: .9; font-size: .9rem; }}
  main {{ max-width: 880px; margin: 0 auto; padding: 24px 20px 64px; }}
  .note {{ background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px;
          padding: 12px 16px; font-size: .85rem; color: #78350f; margin-bottom: 24px; }}
  section {{ background: #fff; border: 1px solid #d1fae5; border-radius: 12px;
           padding: 16px 20px; margin-bottom: 20px; }}
  section h2 {{ font-size: 1.05rem; margin: 0 0 10px; color: #065f46; }}
  ul {{ margin: 0; padding-left: 18px; columns: 2; }}
  @media (max-width: 600px) {{ ul {{ columns: 1; }} }}
  li {{ margin: 4px 0; }}
  a {{ color: #047857; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
<header>
  <h1>🌳 盆栽管理アプリ — 実装UIプレビュー</h1>
  <p>Phase 1（MVP）の Django 実装画面を、デモデータ付きで静的書き出ししたものです。</p>
</header>
<main>
  <div class="note">
    ⚠️ これは閲覧専用の静的スナップショットです。フォーム送信・検索・HTMX などの
    動的操作は動作しません（リンクの一部は無効化しています）。スタイル（Tailwind 等）は
    CDN 経由で読み込むため、オンライン環境のブラウザで正しく表示されます。
  </div>

  <section>
    <h2>主要画面（ボトムナビ4タブ）</h2>
    <ul>
      {link("home.html", "ホーム（今月のやること＋マイ盆栽）")}
      {link("schedules.html", "月別スケジュール")}
      {link("logs.html", "作業ログ一覧")}
      {link("articles.html", "お役立ち記事一覧")}
    </ul>
  </section>

  <section>
    <h2>盆栽詳細</h2>
    <ul>
      {plant_links}
    </ul>
  </section>

  <section>
    <h2>入力フォーム</h2>
    <ul>
      {link("bonsai_form.html", "盆栽の新規登録")}
      {link("schedule_form.html", "スケジュールの新規作成")}
      {link("log_form.html", "作業ログの記録")}
    </ul>
  </section>

  <section>
    <h2>お役立ち記事</h2>
    <ul>
      {article_links}
    </ul>
  </section>

  <section>
    <h2>作業ログ詳細</h2>
    <ul>
      {log_links}
    </ul>
  </section>

  <section>
    <h2>品種マスタ詳細</h2>
    <ul>
      {species_links}
    </ul>
  </section>

  <section>
    <h2>認証画面</h2>
    <ul>
      {link("login.html", "ログイン")}
      {link("signup.html", "新規登録")}
    </ul>
  </section>
</main>
</body>
</html>
"""
    (OUT_DIR / "index.html").write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
