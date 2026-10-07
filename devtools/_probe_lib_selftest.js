/** 夹具库自检（**夹具本身也要验证**，否则会把夹具的错当成功能的错 —— 这正是踩过的坑）
 *  用法：node devtools/_probe_lib_selftest.js [base]
 */
const L = require('./_probe_lib.js');
let PASS = 0, FAIL = 0;
function check(n, ok, d) { if (ok) { PASS++; console.log('  OK   ' + n + (d ? '  [' + d + ']' : '')); } else { FAIL++; console.log('  FAIL ' + n + '  ' + (d || '')); } }

(async () => {
  const { browser, page, errors } = await L.launch();
  // ① clearViaPage：页面自己也清干净（点工具应能建点，而不是被旧对象截走）
  await page.evaluate(() => { window.__ggbpyDebug; });
  await L.setTool(page, 'point');
  await L.clearViaPage(page);
  await L.setTool(page, 'point');
  const p = await L.worldToPixel(page, 3.37, -1.63);
  await page.mouse.click(p.x, p.y);
  await page.waitForTimeout(450);
  let els = (await (await page.request.get(L.BASE + '/api/state')).json()).elements;
  check('clearViaPage 后点工具能建点（说明前端也干净了）', els.length === 1, 'n=' + els.length);
  // ①b **现场复现坑①**：HTTP clear 只清服务器 → 页面仍认为原点位有对象 → 同坐标点击被截走
  await page.request.post(L.BASE + '/api/clear', { data: {} });     // 只清服务器（页面不知道）
  await L.setTool(page, 'point');
  await page.mouse.click(p.x, p.y);
  await page.waitForTimeout(450);
  els = (await (await page.request.get(L.BASE + '/api/state')).json()).elements;
  check('HTTP 清空后同坐标点击建不出点（页面本地仍是旧的 → 坐实这个坑）', els.length === 0, 'n=' + els.length);
  await L.clearViaPage(page);
  await L.setTool(page, 'point');
  await page.mouse.click(p.x, p.y);
  await page.waitForTimeout(450);
  els = (await (await page.request.get(L.BASE + '/api/state')).json()).elements;
  check('改用 clearViaPage 后同坐标点击恢复正常', els.length === 1, 'n=' + els.length);
  // ② setTool 幂等：连续两次不应把工具点没
  await L.setTool(page, 'point');
  const t = await page.evaluate(() => window.__ggbpyDebug.toolState().activeTool);
  check('setTool 幂等（连续调用后工具仍激活）', t === 'point', String(t));
  // ③ measureDrawn 按 alpha 判定：空白区域 drawn 应为 0
  const far = await L.worldToPixel(page, 12.5, 7.5);      // 右上角附近（无对象处）
  const m = await L.measureDrawn(page, 'cv', far.x, far.y, 6);
  check('measureDrawn 对空白处 drawn=0（不把透明当深色）', m.drawn === 0, JSON.stringify(m));
  // ④ proj3Pixel：3D 原点应在画布中心附近（相机看向原点）
  await page.evaluate(() => { const h = document.querySelector('#m-view .menu-btn'); if (h) h.click(); });
  await page.waitForTimeout(120);
  await page.click('#btn-3d');
  await page.waitForTimeout(800);
  const o3 = await L.proj3Pixel(page, [0, 0, 0]);
  const rect = await page.evaluate(() => { const b = document.getElementById('cv3d').getBoundingClientRect(); return { cx: b.left + b.width / 2, cy: b.top + b.height / 2 }; });
  check('proj3Pixel 把原点投到画布中心附近', Math.abs(o3.x - rect.cx) < 40 && Math.abs(o3.y - rect.cy) < 40,
        JSON.stringify({ got: o3, center: rect }));
  check('自检全程无未捕获错误', errors.length === 0, errors.join(';').slice(0, 100));
  console.log('\n夹具库自检：' + PASS + ' 通过 / ' + FAIL + ' 失败');
  await browser.close();
  process.exit(FAIL ? 1 : 0);
})().catch((e) => { console.error('SELFTEST FATAL', e); process.exit(2); });
