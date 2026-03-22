# UI サンプル

盆栽管理アプリの画面イメージです。

## サンプル画像

| 画面 | ファイル | 説明 |
|------|----------|------|
| ダッシュボード（盆栽一覧） | [assets/ui-sample-dashboard.png](../assets/ui-sample-dashboard.png) | マイ盆栽一覧、カード形式 |
| 盆栽詳細 | [assets/ui-sample-detail.png](../assets/ui-sample-detail.png) | 個体詳細、予定・作業ログ表示 |

## HTML モックアップ

[`docs/ui-mockup.html`](ui-mockup.html) をブラウザで開いて確認できます。

**推奨**: `file://` で開くと Tailwind CDN が読み込めない場合があります。ローカルサーバーで表示することを推奨します。

```bash
cd docs && python3 -m http.server 8000
# ブラウザで http://localhost:8000/ui-mockup.html を開く
```

ページ内アンカー一覧（レビュー反映を含む）:

| アンカー | 内容 |
|----------|------|
| `#bonsai-detail` | 盆栽詳細・パンくず・作業ログ入力モック |
| `#schedule-mobile` | 狭幅向けスケジュール（月＋縦リスト） |
| `#empty-state` | 盆栽0本の空状態・オンボーディング |
| `#hub-table` / `#hub-cards` | 一覧（表）・カード |
| `#schedule-section` | 年間スケジュール（表／ガント） |
| `#review-notes` | レビュー対応の要点（詳細は下記 Markdown） |

**レビュー対応の全文**: [レビュー対応案.md](レビュー対応案.md) · 指摘原文 [レビュー改善提案.md](レビュー改善提案.md)

## デザイン方針

- **カラースキーム**: 緑系アクセント（#2d5a3d）、白・グレー背景
- **レイアウト**: カード型、余白を活かしたシンプルな構成
- **技術**: Django テンプレート + Tailwind CSS（本番は CLI ビルド）+ HTMX / Alpine.js を想定（[技術要件書.md](技術要件書.md)）
