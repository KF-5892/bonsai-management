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

import django

django.setup()

from django.core.management import call_command  # noqa: E402
from django.test import Client  # noqa: E402
from django.utils import timezone  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = BASE_DIR / "docs" / "preview"

# 盆栽詳細のタブ（apps.bonsai.views.DETAIL_TABS と同じ順）
DETAIL_TAB_KEYS_ORDERED = [
    "overview",
    "logs",
    "schedules",
    "media",
    "repotting",
    "compare",
]


def reset_db() -> None:
    db = BASE_DIR / "db.sqlite3"
    if db.exists():
        db.unlink()
    call_command("migrate", "--noinput", verbosity=0)
    call_command("collectstatic", "--noinput", "--clear", verbosity=0)
    call_command("loaddata", "bonsai_species_seed", verbosity=0)
    call_command("loaddata", "monthly_advices_seed", verbosity=0)


def _dummy_photo(rgb: tuple[int, int, int]):
    """プレビュー用のダミー写真（単色 + 樹形のような図形）を生成する。"""
    from io import BytesIO

    from django.core.files.base import ContentFile
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (960, 960), rgb)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 780, 960, 960), fill=(196, 180, 160))  # 鉢
    draw.rectangle((440, 420, 520, 800), fill=(92, 68, 48))  # 幹
    for cx, cy, r in [(480, 360, 210), (330, 470, 130), (640, 470, 140)]:
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(58, 110, 62))
    buf = BytesIO()
    image.save(buf, format="JPEG", quality=85)
    return ContentFile(buf.getvalue(), name="demo.jpg")


def seed_demo_data():
    from django.contrib.auth import get_user_model

    from apps.articles.models import (
        ArticleCategory,
        ArticleSpeciesRelation,
        ArticleStatus,
        HelpArticle,
    )
    from apps.bonsai.models import (
        BonsaiMedia,
        BonsaiPlant,
        BonsaiSpecies,
        HealthStatus,
        Tag,
    )
    from apps.logs.models import CareLog, Fertilizer, FertilizerForm, HealthEvaluation, Weather
    from apps.schedules.models import (
        CareSchedule,
        CompletionSourceType,
        RepeatType,
        TaskType,
    )
    from apps.schedules.services import mark_todo_done

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
        (
            "黒松 太郎",
            kuro or (others[0] if others else None),
            HealthStatus.GOOD,
            date(2021, 5, 10),
            "実生3年。芽摘みで樹勢を調整中。",
        ),
        (
            "もみじ 花子",
            momiji or (others[1] if len(others) > 1 else None),
            HealthStatus.WATCH,
            date(2022, 3, 20),
            "葉やけ気味。半日陰に移動して様子見。",
        ),
        (
            "五葉松 次郎",
            species.get("goyomatsu") or (others[2] if len(others) > 2 else None),
            HealthStatus.GOOD,
            date(2020, 11, 1),
            "棚の主役。針金で枝順を整えた。",
        ),
    ]
    for name, sp, health, acquired, notes in plant_specs:
        plants.append(
            BonsaiPlant.objects.create(
                user=user,
                species=sp,
                name=name,
                health_status=health,
                acquired_at=acquired,
                notes=notes,
            )
        )

    # タグ（ライブラリ / 表示切替の確認用）
    tags = {
        name: Tag.objects.create(user=user, name=name, color=color)
        for name, color in [("ベランダ", "#4CAF50"), ("棚上", "#8D6E63")]
    }
    plants[0].tags.add(tags["ベランダ"])
    plants[1].tags.add(tags["ベランダ"])
    plants[2].tags.add(tags["棚上"])

    # 肥料マスタ（共通 + 個別）
    Fertilizer.objects.create(
        name="標準固形肥料（共通）",
        form_type=FertilizerForm.SOLID,
        n=5,
        p=5,
        k=5,
        note="共通マスタの例。",
    )
    fertilizer = Fertilizer.objects.create(
        user=user,
        name="自家製油かす",
        form_type=FertilizerForm.SOLID,
        n=6,
        p=3,
        k=1,
        is_organic=True,
        note="春と秋に置き肥。",
    )

    # 写真（成長比較・ギャラリー確認用にダミー画像を生成）
    for offset_days, caption, rgb in [
        (540, "入手直後", (120, 150, 110)),
        (240, "半年後の姿", (90, 140, 95)),
        (20, "芽摘み後", (60, 120, 80)),
    ]:
        media = BonsaiMedia.objects.create(
            bonsai=plants[0],
            image_original=_dummy_photo(rgb),
            taken_at=today - timedelta(days=offset_days),
            caption=caption,
        )
    plants[0].cover_media = media
    plants[0].save(update_fields=["cover_media"])

    # スケジュール（当月に次回予定が来るもの）
    watering_schedule = CareSchedule.objects.create(
        bonsai=plants[0],
        user=user,
        task_type=TaskType.WATERING,
        title="黒松の水やり",
        repeat_type=RepeatType.DAILY,
        repeat_rule={"interval": 1},
        start_date=today - timedelta(days=30),
        next_run_at=today,
        is_active=True,
        notes="朝夕の2回。",
    )
    CareSchedule.objects.create(
        bonsai=plants[1],
        user=user,
        task_type=TaskType.FERTILIZING,
        title="もみじの置き肥",
        repeat_type=RepeatType.MONTHLY,
        repeat_rule={"interval": 1, "bymonthday": 1},
        start_date=today - timedelta(days=60),
        next_run_at=today + timedelta(days=3),
        is_active=True,
    )

    # 作業ログ
    log_specs = [
        (
            plants[0],
            TaskType.WATERING,
            Weather.SUNNY,
            22.5,
            "たっぷり灌水。",
            HealthEvaluation.GOOD,
            1,
        ),
        (
            plants[0],
            TaskType.BUD_PINCHING,
            Weather.CLOUDY,
            20.0,
            "強い芽を元から摘んだ。",
            HealthEvaluation.VERY_GOOD,
            5,
        ),
        (
            plants[1],
            TaskType.OBSERVATION,
            Weather.SUNNY,
            24.0,
            "葉先が少し茶色い。風通しを改善。",
            HealthEvaluation.NORMAL,
            8,
        ),
        (
            plants[2],
            TaskType.WIRING,
            Weather.CLOUDY,
            18.0,
            "下枝にアルミ線をかけた。",
            HealthEvaluation.GOOD,
            12,
        ),
    ]
    first_log = None
    for bonsai, tt, weather, temp, note, ev, days_ago in log_specs:
        log = CareLog.objects.create(
            bonsai=bonsai,
            user=user,
            task_type=tt,
            weather=weather,
            temperature_c=temp,
            notes=note,
            health_evaluation=ev,
            performed_at=timezone.now() - timedelta(days=days_ago),
        )
        first_log = first_log or log

    # 施肥ログ（肥料参照あり）
    CareLog.objects.create(
        bonsai=plants[1],
        user=user,
        task_type=TaskType.FERTILIZING,
        weather=Weather.CLOUDY,
        temperature_c=21.0,
        fertilizer=fertilizer,
        fertilizer_amount="3粒",
        notes="置き肥を交換。",
        health_evaluation=HealthEvaluation.GOOD,
        performed_at=timezone.now() - timedelta(days=3),
    )

    # ToDo の完了実績（月末レビューの達成率を 0% にしないため）
    month_start = date(today.year, today.month, 1)
    mark_todo_done(
        user,
        CompletionSourceType.SCHEDULE,
        f"schedule:{watering_schedule.id}",
        month_start,
        bonsai=plants[0],
        log=first_log,
    )

    # お役立ち記事（公開）
    article_specs = [
        (
            "bonsai-watering-basics",
            "盆栽の水やり入門",
            "盆栽管理で最も大切な日課が水やりです。",
            "## 基本\n\n- 土の表面が乾いたらたっぷりと\n- 朝夕の2回が目安\n\n### 季節の注意\n\n夏場は乾きやすいので回数を増やします。",
            kuro,
        ),
        (
            "repotting-guide",
            "植え替えの基本とタイミング",
            "2〜3年に一度の植え替えで根詰まりを防ぎます。",
            "## 適期\n\n芽が動き出す直前の春が基本です。\n\n```\n古い土を1/3落とす\n```\n",
            None,
        ),
        (
            "pest-control",
            "病害虫の予防と対策",
            "早期発見・早期対処が肝心です。",
            "## よくある害虫\n\n| 害虫 | 対策 |\n|---|---|\n| アブラムシ | 薬剤散布 |\n| ハダニ | 葉水 |\n",
            momiji,
        ),
    ]
    # (カテゴリ, 特集フラグ) を記事ごとに割り当てる
    article_meta = {
        "bonsai-watering-basics": (ArticleCategory.TIPS, True),
        "repotting-guide": (ArticleCategory.TIPS, False),
        "pest-control": (ArticleCategory.PEST, False),
    }
    for slug, title, summary, body, rel_sp in article_specs:
        category, featured = article_meta.get(slug, (ArticleCategory.OTHER, False))
        art = HelpArticle.objects.create(
            title=title,
            slug=slug,
            summary=summary,
            body=body,
            category=category,
            is_featured=featured,
            status=ArticleStatus.PUBLISHED,
            author=user,
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
        "/?view=species": "home_species.html",
        "/?view=tag": "home_tag.html",
        "/?range=week": "home_week.html",
        "/schedules/": "schedules.html",
        "/schedules/year/": "schedules_year.html",
        "/schedules/review/": "schedules_review.html",
        "/logs/": "logs.html",
        "/logs/bulk/": "log_bulk_form.html",
        "/logs/fertilizers/": "fertilizers.html",
        "/logs/fertilizers/new/": "fertilizer_form.html",
        "/articles/": "articles.html",
        "/articles/?category=tips": "articles_tips.html",
        "/bonsai/new/": "bonsai_form.html",
        "/schedules/new/": "schedule_form.html",
        "/logs/new/": "log_form.html",
        "/search/?q=松": "search.html",
        "/settings/": "settings.html",
        "/settings/profile/": "settings_profile.html",
        "/settings/notifications/": "settings_notifications.html",
        "/settings/library/": "library.html",
        "/tags/": "tags.html",
        "/tags/new/": "tag_form.html",
    }
    # 詳細ページのファイル名は連番にする（UUID は毎回変わり差分が荒れるため）。
    for i, p in enumerate(plants, start=1):
        pages[f"/bonsai/{p.pk}/"] = f"bonsai_{i}.html"
        # 6 タブそれぞれを個別ファイルに（?tab= は静的化時にファイル名へ書き換える）
        for tab in DETAIL_TAB_KEYS_ORDERED[1:]:
            pages[f"/bonsai/{p.pk}/?tab={tab}"] = f"bonsai_{i}_{tab}.html"
        pages[f"/bonsai/{p.pk}/media/"] = f"bonsai_{i}_gallery.html"
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

    # 相対クエリリンク（?tab=logs 等）-> 静的ファイル名
    def rewrite_relative_queries(html: str, fname: str) -> str:
        stem = fname.removesuffix(".html")
        # 盆栽詳細のタブ（?tab=xxx）
        base_stem = (
            stem.split("_")[0] + "_" + stem.split("_")[1] if stem.startswith("bonsai_") else stem
        )
        for tab in DETAIL_TAB_KEYS_ORDERED:
            target = f"{base_stem}.html" if tab == "overview" else f"{base_stem}_{tab}.html"
            html = html.replace(f'href="?tab={tab}"', f'href="{target}"')
        # ホームの表示切替・期間切替
        for query, target in [
            ("?view=card", "home.html"),
            ("?view=species", "home_species.html"),
            ("?view=tag", "home_tag.html"),
            ("?range=month", "home.html"),
            ("?range=week", "home_week.html"),
            ("?category=tips", "articles_tips.html"),
            ("?", "articles.html" if stem.startswith("articles") else f"{stem}.html"),
        ]:
            html = html.replace(f'href="{query}"', f'href="{target}"')
        # 残りの相対クエリリンク（フィルタ結果など）は無効化する
        html = re.sub(r'href="\?[^"]*"', 'href="#"', html)
        return html

    # リンク書き換え
    def rewrite(html: str) -> str:
        # 静的 CSS（ハッシュ付き含む）-> app.css
        html = re.sub(r"/static/css/app(\.[0-9a-f]+)?\.css", "app.css", html)
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
        (OUT_DIR / fname).write_text(
            rewrite_relative_queries(rewrite(html), fname), encoding="utf-8"
        )

    write_gallery(rendered, plants, all_species)
    print(f"OK: {len(rendered)} pages -> {OUT_DIR}")


def write_gallery(rendered, plants, all_species) -> None:
    """プレビューのトップ（ギャラリー）を生成する。"""

    def link(fname: str, label: str) -> str:
        exists = fname in rendered
        if not exists:
            return f'<li><span style="color:#9ca3af">{label}（生成スキップ）</span></li>'
        return f'<li><a href="{fname}">{label}</a></li>'

    tab_labels = {
        "overview": "概要",
        "logs": "作業履歴",
        "schedules": "スケジュール",
        "media": "メディア",
        "repotting": "植え替え履歴",
        "compare": "成長比較",
    }
    plant_links = "\n".join(
        link(f"bonsai_{i}.html", f"盆栽詳細 — {p.name}") for i, p in enumerate(plants, start=1)
    )
    # 1 本目の盆栽で 6 タブすべてを確認できるようにする
    tab_links = "\n".join(
        link(
            "bonsai_1.html" if tab == "overview" else f"bonsai_1_{tab}.html",
            f"タブ — {tab_labels[tab]}",
        )
        for tab in DETAIL_TAB_KEYS_ORDERED
    )
    tab_links += "\n" + link("bonsai_1_gallery.html", "メディア年別ギャラリー")
    species_links = "\n".join(
        link(f"species_{s.slug}.html", f"品種詳細 — {s.name}") for s in all_species[:8]
    )
    article_files = sorted(f for f in rendered if f.startswith("article_"))
    article_links = "\n".join(
        link(f, f.replace("article_", "").replace(".html", "")) for f in article_files
    )
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
    <h2>ホーム（表示・期間の切替）</h2>
    <ul>
      {link("home.html", "ホーム（カード表示・今月）")}
      {link("home_species.html", "マイ盆栽 — 品種別グルーピング")}
      {link("home_tag.html", "マイ盆栽 — タグ別グルーピング")}
      {link("home_week.html", "やること — 今週の期間切替")}
    </ul>
  </section>

  <section>
    <h2>盆栽詳細</h2>
    <ul>
      {plant_links}
    </ul>
  </section>

  <section>
    <h2>盆栽詳細の 6 タブ（黒松 太郎）</h2>
    <ul>
      {tab_links}
    </ul>
  </section>

  <section>
    <h2>スケジュール</h2>
    <ul>
      {link("schedules.html", "月別スケジュール（絞り込み付き）")}
      {link("schedules_year.html", "年間スケジュール")}
      {link("schedules_review.html", "月末レビュー")}
    </ul>
  </section>

  <section>
    <h2>横断・設定・ライブラリ</h2>
    <ul>
      {link("search.html", "グローバル検索（「松」の結果）")}
      {link("settings.html", "設定トップ")}
      {link("settings_profile.html", "プロフィール編集")}
      {link("settings_notifications.html", "通知設定")}
      {link("library.html", "ライブラリ")}
      {link("tags.html", "タグ管理")}
      {link("tag_form.html", "タグ作成")}
      {link("fertilizers.html", "肥料マスタ")}
      {link("fertilizer_form.html", "肥料登録")}
    </ul>
  </section>

  <section>
    <h2>入力フォーム</h2>
    <ul>
      {link("bonsai_form.html", "盆栽の新規登録")}
      {link("schedule_form.html", "スケジュールの新規作成")}
      {link("log_form.html", "作業ログの記録")}
      {link("log_bulk_form.html", "一括ログ記録")}
    </ul>
  </section>

  <section>
    <h2>お役立ち記事</h2>
    <ul>
      {link("articles.html", "お役立ちトップ（特集＋カテゴリ）")}
      {link("articles_tips.html", "カテゴリ絞り込み — 作業TIPS")}
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
