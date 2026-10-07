/**
 * 探针公共夹具（**已踩过的坑 → 可复用函数**；写探针时先 require 本文件，别自己重写）
 *
 * 每一节都对应一次真实误判（详见 memory/2026-10-07.md 与 SOUL.md《防重蹈覆辙》）：
 *  ① clearViaPage()  —— 不能用 HTTP `POST /api/clear` 代替「页面清空」：
 *                       它只改服务器，**不通知前端**；页面本地仍有旧对象 → 同坐标点击会被
 *                       hitAnyPoint/widgetHit 截走，表现为「点了没反应」，曾据此误判「吸附坏了」✗
 *  ② setTool()       —— 工具按钮是「选中再点取消」：盲点会把工具关掉 ✗；本函数幂等 + 断言 activeTool
 *  ③ measureDrawn()  —— 画布空白处是 `rgba(0,0,0,0)`：**只看亮度会把透明当深色** ✗
 *                       （曾量出「原点邻域 732/841 深色」的荒谬基线）→ 必须按 alpha 判定
 *  ④ worldToPixel() / proj3Pixel() —— 2D/3D 世界坐标 → 页面像素（省得每次手算 offset）
 *  ⑤ launch()        —— 统一收集 pageerror/console error 与自动应答 dialog（清空按钮会 confirm）
 *
 * 用法：`const L = require('./_probe_lib.js'); const { browser, page } = await L.launch();`
 */
const { chromium } = require('/home/kumath/.openclaw/workspace/node_modules/playwright-core');
const EXE = '/home/kumath/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome';
const BASE = process.env.GGBPY_BASE || 'http://127.0.0.1:8090';

/** 启动浏览器并返回 { browser, page, errors }；errors 收集未捕获异常与 console.error */
async function launch(base) {
  const browser = await chromium.launch({ executablePath: EXE, headless: true, args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push('PAGEERROR: ' + String((e && e.message) || e)));
  page.on('console', (m) => {
    const t = m.text();
    if (m.type() === 'error' && t.indexOf('favicon') === -1 && t.indexOf('404') === -1) {
      errors.push('CONSOLE: ' + t.slice(0, 120));
    }
  });
  page.on('dialog', async (d) => { await d.accept(''); });   // 清空/删除等 confirm
  await page.goto((base || BASE) + '/', { waitUntil: 'networkidle' });
  await page.waitForTimeout(400);
  return { browser, page, errors };
}

/** 坑①：走**页面自己的清空按钮**（HTTP clear 不通知前端 → 会造成假故障） */
async function clearViaPage(page) {
  await page.evaluate(() => {
    const el = document.getElementById('btn-clear');
    const menu = el && el.closest ? el.closest('#toolbar .menu') : null;
    if (menu && !menu.classList.contains('open')) {
      const h = menu.querySelector('.menu-btn');
      if (h) h.click();
    }
  });
  await page.waitForTimeout(120);
  await page.click('#btn-clear');
  await page.waitForTimeout(450);
}

/** 坑②：幂等选工具（按钮「选中再点取消」）并断言真的激活了 */
async function setTool(page, tool) {
  const cur = await page.evaluate(() => window.__ggbpyDebug.toolState().activeTool);
  if (cur !== tool) {
    await page.click('#cat-tools .tool-btn[data-tool="' + tool + '"]');
    await page.waitForTimeout(200);
  }
  const now = await page.evaluate(() => window.__ggbpyDebug.toolState().activeTool);
  if (now !== tool) throw new Error('工具未激活: 期望 ' + tool + '，实际 ' + now);
}

/** 坑③：按 **alpha** 统计画布已绘制像素（透明 ≠ 深色） */
async function measureDrawn(page, canvasId, cx, cy, R) {
  return await page.evaluate(([id, x, y, r]) => {
    const cv = document.getElementById(id);
    const ctx = cv.getContext('2d');
    const n = r * 2 + 1;
    const d = ctx.getImageData(Math.round(x - r), Math.round(y - r), n, n).data;
    let drawn = 0, dark = 0;
    for (let i = 0; i < d.length; i += 4) {
      if (d[i + 3] === 0) continue;                       // 透明 = 未绘制（关键）
      drawn++;
      if (0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2] < 200) dark++;
    }
    return { cx: Math.round(x), cy: Math.round(y), box: n * n, drawn: drawn, dark: dark };
  }, [canvasId, cx, cy, R]);
}

/** 坑④：2D 世界坐标 → **页面像素**（可直接喂给 page.mouse.click） */
async function worldToPixel(page, wx, wy) {
  const s = await page.evaluate(([x, y]) => window.__ggbpyDebug.toScreen(x, y), [wx, wy]);
  const r = await page.evaluate(() => {
    const b = document.getElementById('cv').getBoundingClientRect();
    return { left: b.left, top: b.top };
  });
  return { x: r.left + s.x, y: r.top + s.y };
}

/** 坑④（3D）：3D 世界坐标 → **页面像素** */
async function proj3Pixel(page, p3) {
  const s = await page.evaluate((p) => window.__ggbpyDebug.proj3At(p), p3);
  const r = await page.evaluate(() => {
    const b = document.getElementById('cv3d').getBoundingClientRect();
    return { left: b.left, top: b.top };
  });
  return { x: r.left + s.x, y: r.top + s.y };
}

module.exports = { BASE, launch, clearViaPage, setTool, measureDrawn, worldToPixel, proj3Pixel };
