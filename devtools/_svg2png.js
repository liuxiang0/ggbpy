#!/usr/bin/env node
/**
 * SVG → PNG 预览（本机没有 rsvg-convert / cairosvg，但有 playwright-core + Chromium）
 * 用法：node devtools/_svg2png.js <in.svg> <out.png> [scale]
 */
const { chromium } = require('/home/kumath/.openclaw/workspace/node_modules/playwright-core');
const path = require('path');

(async () => {
  const [svg, png, scaleArg] = process.argv.slice(2);
  if (!svg || !png) { console.error('用法: node _svg2png.js <in.svg> <out.png> [scale]'); process.exit(2); }
  const scale = Number(scaleArg || 2);
  const browser = await chromium.launch({
    executablePath: '/home/kumath/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome',
    headless: true, args: ['--no-sandbox'],
  });
  const page = await browser.newPage({ viewport: { width: 1200, height: 800 }, deviceScaleFactor: scale });
  await page.goto('file://' + path.resolve(svg), { waitUntil: 'load' });
  await page.waitForTimeout(250);
  const el = page.locator('svg').first();
  const box = await el.boundingBox();
  await el.screenshot({ path: png });
  await browser.close();
  console.log(JSON.stringify({ w: Math.round(box.width * scale), h: Math.round(box.height * scale) }));
})();
