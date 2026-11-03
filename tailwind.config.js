/** @type {import('tailwindcss').Config} */
// Stitch モックのデザインシステム（Material Design 3 トークン）。
// base.html のインライン設定から移植した単一の定義元。変更後は `npm run build` で再生成する。
module.exports = {
  content: [
    "./templates/**/*.html",
    "./apps/**/templates/**/*.html",
    // フォーム部品のクラスは Python 側（apps/common/forms.py など）に書かれている
    "./apps/**/*.py",
  ],
  theme: {
    extend: {
      colors: {
        "background": "#f6faf6",
        "on-background": "#181d1a",
        "surface": "#f6faf6",
        "surface-bright": "#f6faf6",
        "surface-dim": "#d7dbd7",
        "surface-tint": "#1b6d24",
        "surface-variant": "#dfe3e0",
        "surface-container-lowest": "#ffffff",
        "surface-container-low": "#f1f5f1",
        "surface-container": "#ebefeb",
        "surface-container-high": "#e5e9e5",
        "surface-container-highest": "#dfe3e0",
        "on-surface": "#181d1a",
        "on-surface-variant": "#40493d",
        "inverse-surface": "#2d312f",
        "inverse-on-surface": "#eef2ee",
        "primary": "#0d631b",
        "on-primary": "#ffffff",
        "primary-container": "#2e7d32",
        "on-primary-container": "#cbffc2",
        "primary-fixed": "#a3f69c",
        "primary-fixed-dim": "#88d982",
        "on-primary-fixed": "#002204",
        "on-primary-fixed-variant": "#005312",
        "inverse-primary": "#88d982",
        "secondary": "#526350",
        "on-secondary": "#ffffff",
        "secondary-container": "#d2e5cd",
        "on-secondary-container": "#566754",
        "secondary-fixed": "#d5e8d0",
        "secondary-fixed-dim": "#b9ccb5",
        "on-secondary-fixed": "#101f10",
        "on-secondary-fixed-variant": "#3b4b39",
        "tertiary": "#923357",
        "on-tertiary": "#ffffff",
        "tertiary-container": "#b14b6f",
        "on-tertiary-container": "#ffedf0",
        "tertiary-fixed": "#ffd9e2",
        "tertiary-fixed-dim": "#ffb1c7",
        "on-tertiary-fixed": "#3f001c",
        "on-tertiary-fixed-variant": "#7f2448",
        "error": "#ba1a1a",
        "on-error": "#ffffff",
        "error-container": "#ffdad6",
        "on-error-container": "#93000a",
        "outline": "#707a6c",
        "outline-variant": "#bfcaba"
      },
      fontFamily: {
        "headline": ["Inter", "Noto Sans JP", "sans-serif"],
        "body": ["Inter", "Noto Sans JP", "sans-serif"],
        "label": ["Inter", "Noto Sans JP", "sans-serif"]
      },
      borderRadius: { "DEFAULT": "1rem", "lg": "2rem", "xl": "3rem", "full": "9999px" }
    }
  },
  plugins: [
    require("@tailwindcss/forms"),
    require("@tailwindcss/typography"),
    require("@tailwindcss/container-queries"),
  ],
};
