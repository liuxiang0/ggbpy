/**
 * ggbpy 3D 检测矩阵 —— 浏览器层（真实 Chromium，走完整前端交互）。
 *
 * 覆盖：
 *   A 3D 工具栏完整性（15 个工具按钮）
 *   B 每个工具的 happy path（真实鼠标点击 + 弹窗）
 *   C 多路径：圆锥 3 / 圆柱 3 / 立方体 4
 *   D 退化输入、取消流程、工具激活切换
 *   E 滑块（DOM range）驱动 3D 实体 + 画布像素校验
 *   F undo / redo / .ggk 往返（浏览器内）
 *   G 零 JS 错误
 *
 * 用法:
 *   node devtools/verify_3d_ui_matrix.js
 *   GGBPY_BASE=http://127.0.0.1:8091 node devtools/verify_3d_ui_matrix.js
 * 退出码: 0 全通过 / 1 有失败 / 2 服务不可用
 */
const { chromium } = require('/home/kumath/.openclaw/workspace/node_modules/playwright-core');
const fs = require('fs');
const EXE = '/home/kumath/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome';
const BASE = process.env.GGBPY_BASE || 'http://127.0.0.1:8090';

const FAILS = [];
let COUNT = 0;
function section(t) { console.log('\n=== ' + t + ' ==='); }
function check(name, cond, detail) {
  COUNT++;
  if (cond) { if (process.env.VERBOSE) console.log('  PASS ' + name + (detail ? '  ' + detail : '')); }
  else { FAILS.push(name); console.log('  FAIL ' + name + (detail ? '  ' + detail : '')); }
}

const TOOLS = ['pt3d', 'seg3d', 'line3d', 'plane3d', 'sphere3d', 'cube3d', 'cone3d',
  'cylinder3d', 'prism3d', 'pyramid3d', 'tetra3d', 'octa3d', 'hexa3d', 'icosa3d', 'dodeca3d'];

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, headless: true, args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  const errs = [];
  page.on('pageerror', e => errs.push('PAGEERROR: ' + e.message));
  page.on('console', m => {
    const t = m.text();
    if (m.type() === 'error' && t.indexOf('favicon') === -1 && t.indexOf('404') === -1) errs.push('CONSOLE: ' + t.slice(0, 110));
  });
  let dialogAnswer = null;
  page.on('dialog', async d => { if (dialogAnswer === 'CANCEL') await d.dismiss(); else await d.accept(dialogAnswer == null ? '' : dialogAnswer); });
  await page.goto(BASE + '/', { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);

  // ---- 基础工具 ----
  const api = (path, body, method) => page.evaluate(async ([p, b, m]) => {
    const opt = { method: m || (b !== undefined && b !== null ? 'POST' : 'GET') };
    if (b !== undefined && b !== null) {
      opt.headers = { 'Content-Type': typeof b === 'string' ? 'text/plain' : 'application/json' };
      opt.body = typeof b === 'string' ? b : JSON.stringify(b);
    }
    const r = await fetch(p, opt);
    const txt = await r.text();
    try { return { status: r.status, json: JSON.parse(txt), headers: {} }; }
    catch (e) { return { status: r.status, text: txt, headers: {} }; }
  }, [path, body, method]);

  const inp = async (t) => api('/api/input', { text: t });
  const clearApi = async () => api('/api/clear', {});
  const state3d = async () => (await api('/api/state3d')).json.elements || [];
  const state = async () => (await api('/api/state')).json.elements || [];
  const byDefn = async (re) => (await state3d()).filter(e => re.test(e.defn || ''));

  const reset = async (prep) => {
    await clearApi();
    if (prep) for (const t of prep) await inp(t);
    await page.reload({ waitUntil: 'networkidle' });
    await page.waitForTimeout(450);
    await open3d();
  };
  const open3d = async () => {
    const on = await page.evaluate(() => document.body.classList.contains('mode3d') || !!document.getElementById('cv3d') && getComputedStyle(document.getElementById('cv3d')).display !== 'none');
    if (!on) { await page.click('#btn-3d'); await page.waitForTimeout(700); }
    const hasCat = await page.$('.cat-icon[data-cat="d3"]');
    if (hasCat) { await page.click('.cat-icon[data-cat="d3"]'); await page.waitForTimeout(200); }
  };
  const toolActive = (tool) => page.evaluate((t) => {
    const b = document.querySelector('#cat-tools .tool-btn[data-tool="' + t + '"]');
    return !!b && b.className.indexOf('active') !== -1;
  }, tool);
  const setTool = async (tool) => {
    if (!(await toolActive(tool))) { await page.click('#cat-tools .tool-btn[data-tool="' + tool + '"]'); await page.waitForTimeout(200); }
  };
  const rect3d = () => page.evaluate(() => {
    const c = document.getElementById('cv3d'); const b = c.getBoundingClientRect();
    return { x: b.x, y: b.y, width: c.clientWidth, height: c.clientHeight };
  });
  const proj = async (p) => {
    const r = await rect3d(); const K = 0.3536; const s = Math.min(r.width, r.height) * 0.42 / 14;
    return { x: r.x + r.width / 2 + (p[0] + K * p[1]) * s, y: r.y + r.height / 2 - (p[2] + K * p[1]) * s };
  };
  const click3d = async (p, wait) => {
    const q = await proj(p);
    await page.mouse.move(q.x, q.y, { steps: 3 });
    await page.mouse.down(); await page.mouse.up();
    await page.waitForTimeout(wait || 700);
  };
  const nonBgPixels = () => page.evaluate(() => {
    const c = document.getElementById('cv3d');
    const ctx = c.getContext('2d');
    const d = ctx.getImageData(0, 0, c.width, c.height).data;
    let n = 0;
    for (let i = 0; i < d.length; i += 4) {
      if (Math.abs(d[i] - d[i + 1]) > 12 || Math.abs(d[i + 1] - d[i + 2]) > 12 || d[i] < 235) n++;
    }
    return n;
  });

  // ---- 服务探针 ----
  section('A. 服务与工具栏完整性');
  const probe = await api('/');
  check('服务可达 ' + BASE, probe && probe.status === 200, 'status=' + (probe && probe.status));
  if (!probe || probe.status !== 200) { console.log('服务不可用：PORT=8091 ./run.sh'); await browser.close(); process.exit(2); }
  await reset();
  const btnCount = await page.evaluate((tools) => tools.filter(t => !!document.querySelector('#cat-tools .tool-btn[data-tool="' + t + '"]')).length, TOOLS);
  check('d3 分类 15 个工具按钮', btnCount === 15, btnCount + '/15');

  // ---- B. happy path ----
  section('B. 每个工具 happy path');
  const HAPPY = [
    ['pt3d', [[-3, 0, 0]], null, /^$/, 'point'],
    ['seg3d', [[-4, 2, 0], [4, 2, 0]], null, /Segment\[/, 'geo3d'],
    ['line3d', [[-4, -2, 0], [4, -2, 0]], null, /Line\[/, 'geo3d'],
    ['plane3d', [[-4, 4, 0], [4, 4, 0], [0, -4, 0]], null, /Plane\[/, 'geo3d'],
    ['sphere3d', [[-2, 0, 0], [2, 0, 0]], null, /Sphere\[/, 'geo3d'],
    ['cube3d', [[-3, -3, 0], [3, -3, 0]], null, /Cube\[/, 'geo3d'],
    ['cone3d', [[0, 0, 0], [0, 4, 0]], '2', /Cone\[/, 'geo3d'],
    ['cylinder3d', [[0, 0, 0], [0, 4, 0]], '2', /Cylinder\[/, 'geo3d'],
    ['prism3d', [[-4, -3, 0], [0, -3, 0], [-2, 1, 0]], null, /Prism\[/, 'geo3d'],
    ['pyramid3d', [[-4, -3, 0], [0, -3, 0], [-2, 1, 0]], null, /Pyramid\[/, 'geo3d'],
    ['tetra3d', [[-4, -3, 0], [0, -3, 0], [-2, 1, 0]], null, /Tetrahedron\[/, 'geo3d'],
    ['octa3d', [[-4, -3, 0], [0, -3, 0], [-2, 1, 0]], null, /Octahedron\[/, 'geo3d'],
    ['hexa3d', [[-4, -3, 0], [0, -3, 0], [-2, 1, 0]], null, /Hexahedron\[/, 'geo3d'],
    ['icosa3d', [[-4, -3, 0], [0, -3, 0], [-2, 1, 0]], null, /Icosahedron\[/, 'geo3d'],
    ['dodeca3d', [[-4, -3, 0], [0, -3, 0], [-2, 1, 0]], null, /Dodecahedron\[/, 'geo3d'],
  ];
  for (const [tool, clicks, ans, re, kind] of HAPPY) {
    await reset();
    dialogAnswer = ans;
    await setTool(tool);
    for (const c of clicks) await click3d(c);
    const els = await state3d();
    let hit;
    if (tool === 'pt3d') hit = els.filter(e => e.kind === 'point').pop();
    else hit = els.filter(e => re.test(e.defn || '') && !e.error).pop();
    const bad = els.filter(e => e.error);
    check('工具 ' + tool + ' 生成对象', !!hit && hit.kind === kind, hit ? hit.defn : '无（' + JSON.stringify(els.map(e => e.defn)) + '）');
    if (tool !== 'pt3d') check('工具 ' + tool + ' 无错误元素', bad.length === 0, JSON.stringify(bad.map(e => e.error)));
  }

  // ---- C. 多路径 ----
  section('C. 圆锥 3 模式 / 圆柱 3 模式 / 立方体 4 模式');
  const PREP_CONE = ['O=(0,0)', 'c=Circle[O,2]', 'A3=(0,0,5)', 'B3=(0,0,0)', 'C3=(2,0,0)'];
  const coneInfo = async () => (await state3d()).filter(e => /Cone\[/.test(e.defn || ''));
  // cone A: 圆 + 高度
  await reset(PREP_CONE);
  dialogAnswer = '3';
  await setTool('cone3d');
  await click3d([0, 2, 0]);
  let cs = await coneInfo();
  check('圆锥模式A 圆+高度', cs.length === 1 && !cs[0].error && cs[0].solid === 'cone', JSON.stringify(cs.map(e => e.defn)));
  // cone B: 顶点 + 底心 + 半径
  await reset(PREP_CONE);
  dialogAnswer = '2';
  await setTool('cone3d');
  await click3d([0, 0, 5]);
  await click3d([0, 0, 0]);
  cs = await coneInfo();
  check('圆锥模式B 顶点+底心+半径', cs.length === 1 && !cs[0].error && cs[0].solid === 'cone', JSON.stringify(cs.map(e => e.defn)));
  // cone C: 取消半径框 → 经典三点
  await reset(PREP_CONE);
  dialogAnswer = 'CANCEL';
  await setTool('cone3d');
  await click3d([0, 0, 5]);
  await click3d([0, 0, 0]);
  await click3d([2, 0, 0]);
  cs = await coneInfo();
  check('圆锥模式C 取消→三点式', cs.length === 1 && !cs[0].error, JSON.stringify(cs.map(e => e.defn)));
  // cylinder A/B/C
  const cylInfo = async () => (await state3d()).filter(e => /Cylinder\[/.test(e.defn || ''));
  await reset(PREP_CONE);
  dialogAnswer = '3';
  await setTool('cylinder3d');
  await click3d([0, 2, 0]);
  let ys = await cylInfo();
  check('圆柱模式A 圆+高度', ys.length === 1 && !ys[0].error && ys[0].solid === 'cylinder', JSON.stringify(ys.map(e => e.defn)));
  await reset(PREP_CONE);
  dialogAnswer = '2';
  await setTool('cylinder3d');
  await click3d([0, 0, 5]);
  await click3d([0, 0, 0]);
  ys = await cylInfo();
  check('圆柱模式B 底心+顶心+半径', ys.length === 1 && !ys[0].error, JSON.stringify(ys.map(e => e.defn)));
  await reset(PREP_CONE);
  dialogAnswer = 'CANCEL';
  await setTool('cylinder3d');
  await click3d([0, 0, 5]);
  await click3d([0, 0, 0]);
  await click3d([2, 0, 0]);
  ys = await cylInfo();
  check('圆柱模式C 取消→三点式', ys.length === 1 && !ys[0].error, JSON.stringify(ys.map(e => e.defn)));
  // cube A: 两点
  await reset();
  await setTool('cube3d');
  await click3d([-3, -3, 0]);
  await click3d([1, -3, 0]);
  let cub = (await byDefn(/Cube\[/));
  check('立方体A 两点', cub.length === 1 && !cub[0].error, JSON.stringify(cub.map(e => e.defn)));
  // cube B: 点线段
  await reset(['A3=(0,0,0)', 'B3=(2,0,0)', 'S3=Segment[A3,B3]']);
  await setTool('cube3d');
  await click3d([1, 0, 0]);
  cub = await byDefn(/Cube\[/);
  check('立方体B 线段', cub.length === 1 && !cub[0].error, JSON.stringify(cub.map(e => e.defn)));
  // cube C: 线段 + 方向点
  await reset(['A3=(0,0,0)', 'B3=(2,0,0)', 'S3=Segment[A3,B3]', 'D3=(0,3,0)']);
  await setTool('cube3d');
  await click3d([0, 3, 0]);
  await click3d([1, 0, 0]);
  cub = await byDefn(/Cube\[/);
  check('立方体C 线段+方向点', cub.length === 1 && !cub[0].error, JSON.stringify(cub.map(e => e.defn)));
  // cube D: 正方形多边形
  await reset(['P1=(-4,0)', 'P2=(-2,0)', 'P3=(-2,2)', 'P4=(-4,2)', 'Sq=Polygon[P1,P2,P3,P4]']);
  await setTool('cube3d');
  await click3d([-3, 1, 0]);
  cub = await byDefn(/Cube\[/);
  check('立方体D 正方形多边形', cub.length === 1 && !cub[0].error, JSON.stringify(cub.map(e => e.defn)));

  // ---- D. 退化 / 取消 / 工具切换 ----
  section('D. 退化输入、取消、工具激活切换');
  await reset();
  await setTool('seg3d');
  await click3d([-2, 0, 0]);
  await click3d([-2, 0, 0]);
  let els = await state3d();
  let segs = els.filter(e => /Segment\[/.test(e.defn || ''));
  check('零长线段 → 错误元素（非静默无效几何）',
    segs.length === 0 || segs.every(e => e.error), JSON.stringify(segs.map(e => e.error || e.defn)));
  await reset();
  await setTool('sphere3d');
  await click3d([-2, 0, 0]);
  await click3d([-2, 0, 0]);
  els = await state3d();
  const sphs = els.filter(e => /Sphere\[/.test(e.defn || ''));
  check('零半径球 → 错误元素', sphs.length === 0 || sphs.every(e => e.error), JSON.stringify(sphs.map(e => e.error || e.defn)));
  await reset();
  const act0 = await toolActive('cube3d');
  await setTool('cube3d');
  const act1 = await toolActive('cube3d');
  await page.click('#cat-tools .tool-btn[data-tool="cube3d"]');
  await page.waitForTimeout(200);
  const act2 = await toolActive('cube3d');
  check('工具激活/取消激活切换（F9 现状锁定）', act1 === true && act2 === false, 'before=%s after1=%s after2=%s'.replace('%s', act0).replace('%s', act1).replace('%s', act2));
  await setTool('cube3d');
  const act3 = await toolActive('cube3d');
  check('可重新激活工具', act3 === true, String(act3));
  // 取消流程：开始造立方体后重新点击工具按钮 → 已选清空（再点两点仍应新建）
  await reset();
  await setTool('cube3d');
  await click3d([-3, -3, 0]);
  await page.click('#cat-tools .tool-btn[data-tool="cube3d"]');   // 取消
  await page.waitForTimeout(150);
  await setTool('cube3d');
  await click3d([-3, -3, 0]);
  await click3d([1, -3, 0]);
  cub = await byDefn(/Cube\[/);
  check('中途取消后重新开始仍可作图', cub.length === 1 && !cub[0].error, JSON.stringify(cub.map(e => e.defn)));

  // ---- E. 滑块驱动 + 像素 ----
  section('E. 滑块驱动 3D 实体 + 画布像素');
  // 滑块控件只出现在 2D 视图的对象列表里，因此这里停在 2D 视图操作
  await clearApi();
  for (const t of ['O=(0,0,0)', 'hh=Slider[1,5,0.5]', 'S=Sphere[O,hh]']) await inp(t);
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(500);
  let sph = (await state3d()).filter(e => /Sphere\[O,hh\]/.test(e.defn || ''))[0];
  check('滑块球初始 r=1', sph && Math.abs(sph.data.r - 1) < 1e-9, sph ? String(sph.data.r) : 'missing');
  const hasSlider = await page.$('input.slider[data-label="hh"]');
  check('对象列表出现滑块控件', !!hasSlider, hasSlider ? 'ok' : '未找到 input.slider');
  if (hasSlider) {
    await page.evaluate(() => {
      const el = document.querySelector('input.slider[data-label="hh"]');
      el.value = '4.5';
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await page.waitForTimeout(900);
    sph = (await state3d()).filter(e => /Sphere\[O,hh\]/.test(e.defn || ''))[0];
    check('滑块拖动 → 球 r 联动为 4.5', sph && Math.abs(sph.data.r - 4.5) < 1e-6, sph ? String(sph.data.r) : 'missing');
  }
  await reset();
  await setTool('cube3d');
  await click3d([-3, -3, 0]);
  await click3d([1, -3, 0]);
  await page.waitForTimeout(800);
  const px = await nonBgPixels();
  check('3D 画布确实绘制出对象（像素 > 500）', px > 500, 'non-bg pixels=' + px);

  // ---- F. undo / redo / .ggk 往返 ----
  section('F. undo / redo / .ggk 往返（浏览器内）');
  await reset(['O=(0,0)', 'c=Circle[O,2]']);
  await inp('co=Cone[c,3]');
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(400);
  await open3d();
  let cones = (await state3d()).filter(e => /Cone\[/.test(e.defn || ''));
  check('准备：圆锥已创建', cones.length === 1 && !cones[0].error, String(cones.length));
  await page.click('#btn-undo');
  await page.waitForTimeout(900);
  cones = (await state3d()).filter(e => /Cone\[/.test(e.defn || ''));
  check('浏览器 undo 移除圆锥', cones.length === 0, String(cones.length));
  await page.click('#btn-redo');
  await page.waitForTimeout(900);
  cones = (await state3d()).filter(e => /Cone\[/.test(e.defn || ''));
  check('浏览器 redo 恢复圆锥且 solid 保留', cones.length === 1 && cones[0].solid === 'cone',
    JSON.stringify(cones.map(e => e.solid)));
  const ggk = await page.evaluate(async () => await (await fetch('/api/download')).text());
  check('.ggk 内容为 JSON', ggk.trim().startsWith('{'), ggk.slice(0, 40));
  await api('/api/clear', {});
  const loaded = await api('/api/load', ggk);
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(400);
  await open3d();
  const after = (await state3d()).filter(e => /Cone\[/.test(e.defn || ''));
  check('.ggk 往返后圆锥恢复', after.length === 1 && !after[0].error && after[0].solid === 'cone',
    JSON.stringify(after.map(e => e.solid + ':' + e.error)));

  // ---- G. 功能验收：嵌套输入 / 截面渲染 / 体积 ----
  section('G. 嵌套命令输入 / 截面渲染 / Volume·Area');
  await reset(['O=(0,0,0)']);
  // 通过真实输入框提交嵌套命令
  const cmdBox = await page.$('#cmd');
  check('主输入框存在', !!cmdBox, cmdBox ? 'ok' : '未找到 #cmd');
  if (cmdBox) {
    await page.fill('#cmd', 'k=Cone[Circle[O,2],3]');
    await page.press('#cmd', 'Enter');
    await page.waitForTimeout(900);
    let ks = (await state3d()).filter(e => /Cone\[/.test(e.defn || ''));
    check('UI 输入嵌套命令 → 圆锥生成', ks.length === 1 && !ks[0].error && ks[0].solid === 'cone',
      JSON.stringify(ks.map(e => e.defn + ':' + e.error)));
    check('UI 状态栏无错误提示', await page.evaluate(() => {
      const el = document.querySelector('#msg') || document.querySelector('#status');
      return !el || el.textContent.indexOf('错误') === -1;
    }), await page.evaluate(() => { const el = document.querySelector('#msg') || document.querySelector('#status'); return el ? el.textContent.slice(0, 60) : ''; }));
  }
  // 平面截立体 → 截面元素 + 画布确实画出
  await reset(['O=(0,0,0)', 'pl=Plane[O,(1,0,0),(0,1,0)]', 'cu=Cube[O,(2,0,0)]']);
  await inp('sec=Intersect[pl,cu]');
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(400);
  await open3d();
  await page.waitForTimeout(600);
  const secs = (await state3d()).filter(e => e.objtype === 'section');
  check('截面元素出现在 state3d', secs.length === 1 && secs[0].data.count >= 3,
    JSON.stringify(secs.map(e => e.data && e.data.count)));
  const secPx = await nonBgPixels();
  check('截面已渲染（像素 > 500）', secPx > 500, 'non-bg pixels=' + secPx);
  // 3D 对象列表应显示「截面」类型名
  const listTxt = await page.evaluate(() => {
    const el = document.querySelector('#obj-list') || document.querySelector('.obj-list') || document.body;
    return el ? el.textContent : '';
  });
  check('3D 列表显示截面类型名', listTxt.indexOf('截面') !== -1 || listTxt.indexOf('Section') !== -1,
    listTxt.replace(/\s+/g, ' ').slice(0, 80));
  // Volume / Area 经 UI 输入
  await page.fill('#cmd', 'V=Volume[cu]');
  await page.press('#cmd', 'Enter');
  await page.waitForTimeout(700);
  const vEl = await page.evaluate(async () => {
    const st = await (await fetch('/api/state')).json();
    const e = st.elements.filter(x => x.label === 'V')[0];
    return e ? e.value : null;
  });
  check('UI 输入 Volume[cu] = 8', vEl && vEl.indexOf('8') !== -1, String(vEl));
  await page.fill('#cmd', 'A=Area[cu]');
  await page.press('#cmd', 'Enter');
  await page.waitForTimeout(700);
  const aEl = await page.evaluate(async () => {
    const st = await (await fetch('/api/state')).json();
    const e = st.elements.filter(x => x.label === 'A')[0];
    return e ? e.value : null;
  });
  check('UI 输入 Area[cu] = 24', aEl && aEl.indexOf('24') !== -1, String(aEl));

  // 第四批：空间圆（球∩平面）与体∩体渲染
  await reset(['O=(0,0,0)', 'sp=Sphere[O,2]', 'pl=Plane[O,(1,0,0),(0,1,0)]']);
  await inp('cc=Intersect[sp,pl]');
  await inp('P1=(1,1,1)');
  await inp('P2=(3,1,1)');
  await inp('cu=Cube[O,(2,0,0)]');
  await inp('cu2=Cube[P1,P2]');
  await inp('cap=Intersect[cu,cu2]');
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(400);
  await open3d();
  await page.waitForTimeout(700);
  const els4 = await state3d();
  const cc4 = els4.filter(e => e.objtype === 'circle3d')[0];
  const cap4 = els4.filter(e => /Intersect\[cu,cu2\]/.test(e.defn || ''))[0];
  check('空间圆元素出现（r=2）', !!cc4 && Math.abs((cc4.data || {}).r - 2) < 1e-9,
    cc4 ? String(cc4.data.r) : 'missing');
  check('体∩体元素出现（8 顶点）', !!cap4 && (cap4.data.verts || []).length === 8,
    cap4 ? String((cap4.data.verts || []).length) : 'missing');
  const px4 = await nonBgPixels();
  check('空间圆/交集已渲染（像素 > 500）', px4 > 500, 'non-bg pixels=' + px4);
  const listTxt4 = await page.evaluate(() => {
    const el = document.querySelector('#obj-list') || document.querySelector('.obj-list') || document.body;
    return el ? el.textContent : '';
  });
  check('列表显示「空间圆」', listTxt4.indexOf('空间圆') !== -1 || listTxt4.indexOf('Circle (3D)') !== -1,
    listTxt4.replace(/\s+/g, ' ').slice(0, 80));

  // 第五批：样式快照（UI 撤销/重做后 wire/locked 不丢）与球∩球交圆
  await reset(['O=(0,0,0)', 'c=Circle[O,2]']);
  await inp('co=Cone[c,3]');
  await inp('SetWire[co,true]');
  await inp('SetLocked[co,true]');
  await inp('A=(2,0,0)');
  await inp('s1=Sphere[O,2]');
  await inp('s2=Sphere[A,2]');
  await inp('sc=Intersect[s1,s2]');
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(400);
  await open3d();
  await page.waitForTimeout(600);
  let els5 = await state3d();
  let co5 = els5.filter(e => e.label === 'co')[0];
  check('准备：圆锥线框/锁定已置位', !!co5 && co5.wire === true && co5.locked === true,
    co5 ? ('wire=' + co5.wire + ' locked=' + co5.locked) : 'missing');
  const sc5 = els5.filter(e => e.objtype === 'circle3d')[0];
  check('球∩球 → 空间圆渲染元素', !!sc5 && Math.abs((sc5.data || {}).r - Math.sqrt(3)) < 1e-9,
    sc5 ? String(sc5.data.r) : 'missing');
  await page.click('#btn-undo');
  await page.waitForTimeout(900);
  els5 = await state3d();
  co5 = els5.filter(e => e.label === 'co')[0];
  check('UI undo 后 wire/locked 保留', !!co5 && co5.wire === true && co5.locked === true,
    co5 ? ('wire=' + co5.wire + ' locked=' + co5.locked) : 'missing');
  await page.click('#btn-redo');
  await page.waitForTimeout(900);
  els5 = await state3d();
  co5 = els5.filter(e => e.label === 'co')[0];
  check('UI redo 后 wire/locked 保留', !!co5 && co5.wire === true && co5.locked === true,
    co5 ? ('wire=' + co5.wire + ' locked=' + co5.locked) : 'missing');
  const px5 = await nonBgPixels();
  check('交圆/线框圆锥已渲染（像素 > 500）', px5 > 500, 'non-bg pixels=' + px5);

  // 第六批：OBJ / STL 导出按钮（真实下载校验）
  await reset(['O=(0,0,0)', 'cc=Circle[O,2]', 'cu=Cube[O,(2,0,0)]', 'co=Cone[cc,3]']);
  await open3d();
  for (const [id, ext, needle] of [['btn-obj', 'obj', 'v '], ['btn-stl', 'stl', 'facet normal']]) {
    const btn = await page.$('#' + id);
    check('导出按钮存在 #' + id, !!btn, btn ? 'ok' : 'missing');
    if (!btn) continue;
    const [dl] = await Promise.all([
      page.waitForEvent('download', { timeout: 20000 }).catch(() => null),
      page.click('#' + id),
    ]);
    check('#' + id + ' 触发下载 .' + ext, !!dl && new RegExp('\\.' + ext + '$').test(dl.suggestedFilename()),
      dl ? dl.suggestedFilename() : 'no download');
    if (dl) {
      const p = await dl.path();
      const txt = p ? fs.readFileSync(p, 'utf8') : '';
      check('.' + ext + ' 内容含「' + needle + '」且非空', txt.indexOf(needle) !== -1 && txt.length > 50,
        'bytes=' + txt.length);
    }
  }

  // 第七批：曲面 + OBJ 文件导入（真实 setInputFiles）
  await reset(['O=(0,0,0)']);
  await page.fill('#cmd', 'surf=Surface[x^2-y^2,-2,2,-2,2,12]');
  await page.press('#cmd', 'Enter');
  await page.waitForTimeout(900);
  await open3d();
  await page.waitForTimeout(600);
  let els7 = await state3d();
  const surf7 = els7.filter(e => e.solid === 'surface')[0];
  check('曲面经输入框建成（13²=169 顶点）', !!surf7 && (surf7.data.verts || []).length === 169,
    surf7 ? String((surf7.data.verts || []).length) : 'missing');
  const px7 = await nonBgPixels();
  check('曲面已渲染（像素 > 500）', px7 > 500, 'non-bg pixels=' + px7);
  // OBJ 文件导入
  const objPath = require('os').tmpdir() + '/ggbpy_ui_test.obj';
  fs.writeFileSync(objPath, ['v 0 0 0', 'v 2 0 0', 'v 2 2 0', 'v 0 2 0',
    'v 0 0 2', 'v 2 0 2', 'v 2 2 2', 'v 0 2 2',
    'f 1 2 3 4', 'f 5 6 7 8', 'f 1 2 6 5', 'f 2 3 7 6', 'f 3 4 8 7', 'f 4 1 5 8'].join('\n'));
  const hasInput = await page.$('#objfile');
  check('OBJ 导入文件输入存在', !!hasInput, hasInput ? 'ok' : 'missing');
  if (hasInput) {
    await page.setInputFiles('#objfile', objPath);
    await page.waitForTimeout(1200);
    await page.reload({ waitUntil: 'networkidle' });
    await page.waitForTimeout(400);
    await open3d();
    await page.waitForTimeout(500);
    els7 = await state3d();
    const mesh7 = els7.filter(e => e.solid === 'mesh')[0];
    check('OBJ 导入生成网格元素（8/6/12）', !!mesh7 && (mesh7.data.verts || []).length === 8
      && (mesh7.data.faces || []).length === 6 && (mesh7.data.edges || []).length === 12,
      mesh7 ? (mesh7.data.verts.length + '/' + mesh7.data.faces.length + '/' + mesh7.data.edges.length) : 'missing');
    const pxM = await nonBgPixels();
    check('导入网格已渲染（像素 > 500）', pxM > 500, 'non-bg pixels=' + pxM);
  }

  // 第八批：参数曲面 + STL 文件导入
  await reset(['O=(0,0,0)']);
  await page.fill('#cmd', 'tor=SurfaceParam[(2+cos(s))*cos(t),(2+cos(s))*sin(t),sin(s),s,t,0,2*pi,0,2*pi,16]');
  await page.press('#cmd', 'Enter');
  await page.waitForTimeout(900);
  await open3d();
  await page.waitForTimeout(600);
  let els8 = await state3d();
  const tor8 = els8.filter(e => e.solid === 'surface' && /SurfaceParam/.test(e.defn || ''))[0];
  check('参数曲面经输入框建成（17²=289 顶点）', !!tor8 && (tor8.data.verts || []).length === 289,
    tor8 ? String((tor8.data.verts || []).length) : 'missing');
  const px8 = await nonBgPixels();
  check('参数曲面已渲染（像素 > 500）', px8 > 500, 'non-bg pixels=' + px8);
  // STL 导入（ASCII）
  const stlPath = require('os').tmpdir() + '/ggbpy_ui_test.stl';
  fs.writeFileSync(stlPath, ['solid tetra',
    '  facet normal 0 0 -1', '    outer loop', '      vertex 0 0 0', '      vertex 2 0 0',
    '      vertex 0 2 0', '    endloop', '  endfacet',
    '  facet normal 0 -1 0', '    outer loop', '      vertex 0 0 0', '      vertex 0 0 2',
    '      vertex 2 0 0', '    endloop', '  endfacet',
    '  facet normal -1 0 0', '    outer loop', '      vertex 0 0 0', '      vertex 0 2 0',
    '      vertex 0 0 2', '    endloop', '  endfacet',
    '  facet normal 1 1 1', '    outer loop', '      vertex 2 0 0', '      vertex 0 0 2',
    '      vertex 0 2 0', '    endloop', '  endfacet', 'endsolid tetra'].join('\n'));
  await page.setInputFiles('#objfile', stlPath);
  await page.waitForTimeout(1200);
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(400);
  await open3d();
  await page.waitForTimeout(500);
  els8 = await state3d();
  const stlMesh = els8.filter(e => e.solid === 'mesh')[0];
  check('STL 导入生成网格元素（4/4/6）', !!stlMesh && (stlMesh.data.verts || []).length === 4
    && (stlMesh.data.faces || []).length === 4 && (stlMesh.data.edges || []).length === 6,
    stlMesh ? (stlMesh.data.verts.length + '/' + stlMesh.data.faces.length + '/' + stlMesh.data.edges.length) : 'missing');

  // 第九批：球×立体交线渲染 + GLTF 导出按钮
  await reset(['O=(0,0,0)']);
  await inp('cu=Cube[(0,0,0),(2,0,0)]');
  await inp('sA=Sphere[(1,1,1),1.2]');
  await inp('xA=Intersect[sA,cu]');
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(400);
  await open3d();
  await page.waitForTimeout(700);
  const els9 = await state3d();
  const xA9 = els9.filter(e => e.objtype === 'curve3d')[0];
  check('球×立体交线元素出现（curve3d，段数 > 100）',
    !!xA9 && (xA9.data.segs || []).length > 100,
    xA9 ? String((xA9.data.segs || []).length) : 'missing');
  const px9 = await nonBgPixels();
  check('交线已渲染（像素 > 500）', px9 > 500, 'non-bg pixels=' + px9);
  const listTxt9 = await page.evaluate(() => {
    const el = document.querySelector('#obj-list') || document.querySelector('.obj-list') || document.body;
    return el ? el.textContent : '';
  });
  check('列表显示「交线」', listTxt9.indexOf('交线') !== -1 || listTxt9.indexOf('Intersection curve') !== -1,
    listTxt9.replace(/\s+/g, ' ').slice(0, 60));
  // GLTF 按钮真实下载
  const gltfBtn = await page.$('#btn-gltf');
  check('GLTF 导出按钮存在', !!gltfBtn, gltfBtn ? 'ok' : 'missing');
  if (gltfBtn) {
    const [dlG] = await Promise.all([
      page.waitForEvent('download', { timeout: 20000 }).catch(() => null),
      page.click('#btn-gltf'),
    ]);
    check('GLTF 按钮触发下载 .gltf', !!dlG && /\.gltf$/.test(dlG.suggestedFilename()),
      dlG ? dlG.suggestedFilename() : 'no download');
    if (dlG) {
      const pg = await dlG.path();
      const txtG = pg ? fs.readFileSync(pg, 'utf8') : '';
      let gg = null;
      try { gg = JSON.parse(txtG); } catch (e) { gg = null; }
      check('下载的 glTF 是合法 JSON 且含 mesh 数据',
        !!gg && gg.asset && gg.asset.version === '2.0' && Array.isArray(gg.meshes) && gg.meshes.length >= 1,
        gg ? ('meshes=' + gg.meshes.length) : ('bytes=' + txtG.length));
    }
  }

  // 第十批：大网格渲染预算（计时）+ glTF 文件导入
  await reset(['O=(0,0,0)']);
  await page.fill('#cmd', 'big=ImplicitSurface[x^2+y^2+z^2-4=0,-2.2,2.2,-2.2,2.2,-2.2,2.2,28]');
  await page.press('#cmd', 'Enter');
  await page.waitForTimeout(1500);
  await open3d();
  await page.waitForTimeout(700);
  let els10 = await state3d();
  const big10 = els10.filter(e => e.solid === 'surface')[0];
  const bigFaces = big10 ? (big10.data.faces || []).length : 0;
  check('大网格等值面已建成（面数 > 3000）', bigFaces > 3000, 'faces=' + bigFaces);
  // 输入框在 3D 模式下创建对象后，客户端 3D 列表应立即刷新（回归：此前要切模式才出现）
  const clientN = await page.evaluate(() => window.__ggbpyDebug.els3dCount());
  check('3D 模式下输入后客户端 3D 列表已刷新', clientN >= 1, 'els3d=' + clientN);
  const dbg = await page.evaluate(() => !!(window.__ggbpyDebug && window.__ggbpyDebug.render3d));
  check('渲染调试钩子可用', dbg, dbg ? 'ok' : 'missing');
  if (dbg) {
    const budget = await page.evaluate(() => window.__ggbpyDebug.faceBudget());
    check('面预算生效（2000）', budget === 2000, String(budget));
    const ms = await page.evaluate(() => {
      const t0 = performance.now();
      for (let i = 0; i < 3; i++) window.__ggbpyDebug.render3d();
      return performance.now() - t0;
    });
    check('大网格 3 次重绘 < 1500ms（预算 + 跳过遮挡测试）', ms < 1500, ms.toFixed(0) + 'ms');
    const cacheN = await page.evaluate(() => window.__ggbpyDebug.cacheSize());
    check('LOD 面表已缓存', cacheN >= 1, 'cache=' + cacheN);
  }
  const px10 = await nonBgPixels();
  check('大网格仍渲染出内容（像素 > 500）', px10 > 500, 'non-bg pixels=' + px10);
  // glTF 文件导入
  const gltfPath = require('os').tmpdir() + '/ggbpy_ui_test.gltf';
  const miniGltf = {
    asset: { version: '2.0' },
    scene: 0,
    scenes: [{ nodes: [0] }],
    nodes: [{ mesh: 0, name: 'tri' }],
    meshes: [{ name: 'tri', primitives: [{ attributes: { POSITION: 0 }, indices: 1, mode: 4 }] }],
    accessors: [
      { bufferView: 0, componentType: 5126, count: 4, type: 'VEC3', min: [0, 0, 0], max: [2, 2, 0] },
      { bufferView: 1, componentType: 5123, count: 6, type: 'SCALAR' }
    ],
    bufferViews: [
      { buffer: 0, byteOffset: 0, byteLength: 48 },
      { buffer: 0, byteOffset: 48, byteLength: 12 }
    ],
    buffers: [{ byteLength: 60, uri: 'data:application/octet-stream;base64,' +
      Buffer.from(new Float32Array([0, 0, 0, 2, 0, 0, 2, 2, 0, 0, 2, 0]).buffer).toString('base64') +
      Buffer.from(new Uint16Array([0, 1, 2, 0, 2, 3]).buffer).toString('base64') }]
  };
  fs.writeFileSync(gltfPath, JSON.stringify(miniGltf));
  await page.setInputFiles('#objfile', gltfPath);
  await page.waitForTimeout(1200);
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(400);
  await open3d();
  await page.waitForTimeout(500);
  els10 = await state3d();
  const gmesh = els10.filter(e => e.solid === 'mesh')[0];
  check('glTF 导入生成网格（4 顶点 / 2 三角）', !!gmesh && (gmesh.data.verts || []).length === 4
    && (gmesh.data.faces || []).length === 2,
    gmesh ? (gmesh.data.verts.length + '/' + gmesh.data.faces.length) : 'missing');
  const pxG = await nonBgPixels();
  check('glTF 导入网格已渲染（像素 > 500）', pxG > 500, 'non-bg pixels=' + pxG);

  // 第十一批：协方差椭球 + 曲面参数线渲染
  await reset(['O=(0,0,0)']);
  await page.fill('#cmd', 'L={(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)}');
  await page.press('#cmd', 'Enter');
  await page.waitForTimeout(500);
  await page.fill('#cmd', 'ell=CovarianceEllipsoid[L,2]');
  await page.press('#cmd', 'Enter');
  await page.waitForTimeout(800);
  await page.fill('#cmd', 'cyl=SurfaceParam[cos(t),sin(t),s,s,t,0,2,0,2*pi,16]');
  await page.press('#cmd', 'Enter');
  await page.waitForTimeout(800);
  await page.fill('#cmd', 'iso=SurfaceIsoline[cyl,1,1]');
  await page.press('#cmd', 'Enter');
  await page.waitForTimeout(800);
  await open3d();
  await page.waitForTimeout(800);
  const els11 = await state3d();
  const ell11 = els11.filter(e => e.label === 'ell')[0];
  const iso11 = els11.filter(e => e.label === 'iso')[0];
  check('椭球元素出现（441 顶点 surface）',
    !!ell11 && ell11.solid === 'surface' && (ell11.data.verts || []).length === 441,
    ell11 ? (ell11.solid + '/' + (ell11.data.verts || []).length) : 'missing');
  check('参数线元素出现（curve3d 120 段）',
    !!iso11 && iso11.objtype === 'curve3d' && (iso11.data.segs || []).length === 120,
    iso11 ? (iso11.objtype + '/' + (iso11.data.segs || []).length) : 'missing');
  const clientN11 = await page.evaluate(() => window.__ggbpyDebug.els3dCount());
  check('输入后 3D 列表含 4 个对象', clientN11 === 4, 'els3d=' + clientN11);
  const px11 = await nonBgPixels();
  check('椭球与参数线已渲染（像素 > 500）', px11 > 500, 'non-bg pixels=' + px11);

  // 第十二批：帮助面板筛选/点击插入 + 凸包渲染
  await reset(['O=(0,0,0)']);
  await page.fill('#cmd', 'cube={(0,0,0),(2,0,0),(2,2,0),(0,2,0),(0,0,2),(2,0,2),(2,2,2),(0,2,2)}');
  await page.press('#cmd', 'Enter');
  await page.waitForTimeout(400);
  await page.fill('#cmd', 'h1=ConvexHull[cube]');
  await page.press('#cmd', 'Enter');
  await page.waitForTimeout(700);
  await open3d();
  await page.waitForTimeout(600);
  const els12 = await state3d();
  const hull12 = els12.filter(e => e.solid === 'hull')[0];
  check('凸包元素出现（8 顶点 / 12 三角）',
    !!hull12 && (hull12.data.verts || []).length === 8 && (hull12.data.faces || []).length === 12,
    hull12 ? (hull12.data.verts.length + '/' + hull12.data.faces.length) : 'missing');
  const px12 = await nonBgPixels();
  check('凸包已渲染（像素 > 500）', px12 > 500, 'non-bg pixels=' + px12);
  // 帮助面板：筛选 + 点击插入
  await page.click('#btn-help');
  await page.waitForTimeout(600);
  const hasSearch = await page.$('#help-search');
  check('帮助面板有筛选框', !!hasSearch, hasSearch ? 'ok' : 'missing');
  if (hasSearch) {
    const total0 = await page.evaluate(() => document.querySelectorAll('#help-cmds .hc-cmd').length);
    await page.fill('#help-search', 'surface');
    await page.waitForTimeout(300);
    const visible = await page.evaluate(() => {
      let n = 0;
      document.querySelectorAll('#help-cmds .hc-cmd').forEach(function (el) {
        if (el.style.display !== 'none') n++;
      });
      return n;
    });
    check('筛选 "surface" 后可见项减少且非空', visible > 0 && visible < total0,
      'visible=' + visible + ' total=' + total0);
    const names = await page.evaluate(() => {
      const out = [];
      document.querySelectorAll('#help-cmds .hc-cmd').forEach(function (el) {
        if (el.style.display !== 'none') out.push(el.getAttribute('data-cmd'));
      });
      return out;
    });
    const namesLc = names.map(function (n) { return String(n).toLowerCase(); });
    check('筛选结果含 SurfaceIsoline/SurfacePoint/SurfaceProject',
      namesLc.indexOf('surfaceisoline') !== -1 && namesLc.indexOf('surfacepoint') !== -1
      && namesLc.indexOf('surfaceproject') !== -1, JSON.stringify(names.slice(0, 8)));
    await page.click('#help-cmds .hc-cmd[data-cmd="SurfacePoint"]');
    await page.waitForTimeout(200);
    const inserted = await page.evaluate(() => document.getElementById('cmd').value);
    check('点击命令插入 Name[]', inserted === 'SurfacePoint[]', inserted);
    const closeBtn = await page.$('#help-close');
    if (closeBtn) await closeBtn.click();
    await page.waitForTimeout(200);
  }

  // ---- H. JS 错误 ----
  section('H. JS 错误');
  check('零 JS 错误（favicon/404 除外）', errs.length === 0, errs.slice(0, 3).join(' | '));

  console.log('\n' + '='.repeat(60));
  console.log('3D 浏览器检测矩阵 @ ' + BASE + '：' + COUNT + ' 项断言，' + FAILS.length + ' 失败');
  FAILS.forEach(f => console.log('  FAILED: ' + f));
  console.log('结果: ' + (FAILS.length ? 'FAILED' : 'ALL PASS'));
  await browser.close();
  process.exit(FAILS.length ? 1 : 0);
})().catch(e => { console.error('FATAL', e); process.exit(1); });
