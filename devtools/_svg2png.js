#!/usr/bin/env node
/**
 * SVG → PNG 预览（本机没有 rsvg-convert / cairosvg，但有 playwright-core + Chromium）
 * 用法：node devtools/_svg2png.js <in.svg> <out.png> [scale]
 *
 * 关键点：**按 SVG 自身的 width/height 截图**（而不是 `el.screenshot()` 取元素包围盒）——
 * 后者会受页面/视口影响（例如 3D 导出图会被撑成整页 1184×800，四周留白 ✗）。
 */
const fs = require('fs');
const path = require('path');
const { chromium } = require('/home/kumath/.openclaw/workspace/node_modules/playwright-core');

(async () => {
  const [svg, png, scaleArg] = process.argv.slice(2);
  if (!svg || !png) { console.error('用法: node _svg2png.js <in.svg> <out.png> [scale]'); process.exit(2); }
  const scale = Number(scaleArg || 2);
  const src = fs.readFileSync(svg, 'utf8');
  const mw = /\bwidth="(\d+(?:\.\d+)?)"/.exec(src);
  const mh = /\bheight="(\d+(?:\.\d+)?)"/.exec(src);
  const w = Math.round(mw ? Number(mw[1]) : 1000);
  const h = Math.round(mh ? Number(mh[1]) : 620);
  const browser = await chromium.launch({
    executablePath: '/home/kumath/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome',
    headless: true, args: ['--no-sandbox'],
  });
  const page = await browser.newPage({ viewport: { width: w + 40, height: h + 40 }, deviceScaleFactor: scale });
  await page.goto('file://' + path.resolve(svg), { waitUntil: 'load' });
  await page.waitForTimeout(200);
  await page.screenshot({ path: png, clip: { x: 0, y: 0, width: w, height: h } });
  await browser.close();
  console.log(JSON.stringify({ w: w * scale, h: h * scale }));
})();
