// Alpine.js / htmx を node_modules から static/js へコピーする。
// CDN 依存を無くし、Django の staticfiles（WhiteNoise）から配信するため。
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const targets = [
  ["node_modules/alpinejs/dist/cdn.min.js", "static/js/alpine.min.js"],
  ["node_modules/htmx.org/dist/htmx.min.js", "static/js/htmx.min.js"],
];

mkdirSync(join(root, "static/js"), { recursive: true });
for (const [src, dest] of targets) {
  copyFileSync(join(root, src), join(root, dest));
  console.log(`copied ${src} -> ${dest}`);
}
