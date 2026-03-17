# UI サンプル

盆栽管理アプリの画面イメージです。

## サンプル画像

| 画面 | ファイル | 説明 |
|------|----------|------|
| ダッシュボード（盆栽一覧） | [assets/ui-sample-dashboard.png](../assets/ui-sample-dashboard.png) | マイ盆栽一覧、カード形式 |
| 盆栽詳細 | [assets/ui-sample-detail.png](../assets/ui-sample-detail.png) | 個体詳細、予定・作業ログ表示 |

## HTML モックアップ

`docs/ui-mockup.html` をブラウザで開いて確認できます。

**推奨**: `file://` で開くと Tailwind CDN が読み込めない場合があります。ローカルサーバーで表示することを推奨します。

```bash
cd docs && python3 -m http.server 8000
# ブラウザで http://localhost:8000/ui-mockup.html を開く
```

- 盆栽一覧（カードグリッド）
- 今後の予定（スケジュール一覧）

## デザイン方針

- **カラースキーム**: 緑系アクセント（#2d5a3d）、白・グレー背景
- **レイアウト**: カード型、余白を活かしたシンプルな構成
- **技術**: Django テンプレート + Tailwind CSS を想定
