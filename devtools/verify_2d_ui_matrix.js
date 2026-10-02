#!/usr/bin/env node
/**
 * ggbpy 2D 前端回归矩阵（P1-G）
 *
 * 补上 REVIEW_12_BATCHES.md「前端盲区」：编辑栏（改色/显隐/锁定/重定义/改名/删除）、
 * 撤销/重做/清空、CAS 面板、分享、图片插入、导出下载、2D 工具点击建点、语言/主题切换。
 *
 * 用法：node devtools/verify_2d_ui_matrix.js [base]
 * 环境变量 GGBPY_BASE（默认 http://127.0.0.1:8090）
 */
const { chromium } = require('/home/kumath/.openclaw/workspace/node_modules/playwright-core');
const fs = require('fs');
const os = require('os');
const path = require('path');

const EXE = '/home/kumath/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome';
const BASE = process.env.GGBPY_BASE || process.argv[2] || 'http://127.0.0.1:8090';

let PASS = 0;
let FAIL = 0;
const FAILED = [];
const JS_ERRORS = [];

function section(t) { console.log('\n=== ' + t + ' ==='); }
function check(name, ok, detail) {
  if (ok) { PASS++; console.log('  OK   ' + name + (detail ? '  [' + detail + ']' : '')); }
  else { FAIL++; FAILED.push(name); console.log('  FAIL ' + name + '  ' + (detail || '')); }
}

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, headless: true, args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  page.on('pageerror', (e) => JS_ERRORS.push(String(e && e.message || e)));
  page.on('dialog', async (d) => { await d.accept(); });

  const state = async () => (await (await page.request.get(BASE + '/api/state')).json()).elements || [];
  const byLabel = async (l) => (await state()).filter((e) => e.label === l)[0] || null;
  const clear = async () => {
    await page.request.post(BASE + '/api/clear', { data: {} });
  };
  const typeCmd = async (t) => {
    await page.fill('#cmd', t);
    await page.press('#cmd', 'Enter');
    await page.waitForTimeout(320);
  };
  const selectRow = async (label) => {
    // 若该行已是选中态，再点一次会取消选择 → 需要确保编辑栏可见
    for (let i = 0; i < 2; i++) {
      await page.click('#objlist .obj[data-label="' + label + '"]');
      await page.waitForTimeout(280);
      const vis = await page.evaluate(() => document.getElementById('editbar').style.display !== 'none');
      if (vis) return;
    }
  };

  await page.goto(BASE + '/', { waitUntil: 'networkidle' });
  await page.waitForTimeout(300);
  await clear();

  // -------------------------------------------------------------------------
  section('A. 输入框创建 + 对象列表');
  await typeCmd('A=(0,0)');
  await typeCmd('B=(4,0)');
  await typeCmd('s=Segment[A,B]');
  await typeCmd('f(x)=x^2');
  const labelsA = (await state()).map((e) => e.label).sort();
  check('输入框创建 4 个对象', JSON.stringify(labelsA) === JSON.stringify(['A', 'B', 'f', 's']), labelsA.join(','));
  const rows = await page.$$eval('#objlist .obj', (els) => els.map((e) => e.getAttribute('data-label')));
  check('对象列表渲染出 4 行', rows.length === 4, rows.join(','));

  // -------------------------------------------------------------------------
  section('B. 编辑栏：改色 / 显隐 / 锁定 / 重定义 / 改名 / 删除');
  await selectRow('s');
  const ebShown = await page.evaluate(() => document.getElementById('editbar').style.display !== 'none');
  check('选中对象后编辑栏出现', ebShown);
  const ebLabel = await page.textContent('#eb-label');
  check('编辑栏显示选中标签 s', (ebLabel || '').trim() === 's', ebLabel);
  await page.click('#editbar .sw[data-c="#059669"]');
  await page.waitForTimeout(350);
  const sEl = await byLabel('s');
  check('改色：swatch 点击 → 颜色 #059669', sEl && sEl.color === '#059669', sEl && sEl.color);
  const visChecked0 = await page.isChecked('#eb-vis');
  check('显隐：选中可见对象时勾选框为选中态', visChecked0 === true, String(visChecked0));
  await page.click('#eb-vis');                       // 取消勾选 → 隐藏
  await page.waitForTimeout(400);
  const sVis = await byLabel('s');
  check('显隐：取消勾选 → visible=false', !!sVis && sVis.visible === false, String(sVis && sVis.visible));
  await page.click('#eb-vis');                       // 重新勾选 → 显示
  await page.waitForTimeout(400);
  const sVis2 = await byLabel('s');
  check('显隐：重新勾选 → 恢复显示', !!sVis2 && sVis2.visible !== false, String(sVis2 && sVis2.visible));
  await page.click('#eb-lock');
  await page.waitForTimeout(350);
  const sLock = await byLabel('s');
  check('锁定：勾选 → locked=true', sLock && sLock.locked === true, String(sLock && sLock.locked));
  await page.click('#eb-lock');
  await page.waitForTimeout(250);
  // 重定义：必须同名（改标签请用"改名"）——先锁住该守卫，再做合法重定义
  await page.fill('#eb-defn', 'X=(0,0)');
  await page.click('#eb-redef');
  await page.waitForTimeout(400);
  const msgBad = await page.textContent('#msg');
  check('重定义改成别的标签 → 明确报错（提示用 Rename）',
    /不一致|Rename|改名/i.test(msgBad || ''), (msgBad || '').slice(0, 56));
  await selectRow('A');
  await page.fill('#eb-defn', 'A=(1,5)');
  await page.click('#eb-redef');
  await page.waitForTimeout(450);
  const aNew = await byLabel('A');
  check('重定义：A → (1,5)（同名改定义）',
    !!aNew && Math.abs(aNew.x - 1) < 1e-9 && Math.abs(aNew.y - 5) < 1e-9,
    aNew ? '(' + aNew.x + ',' + aNew.y + ')' : 'null');
  await selectRow('A');
  await page.fill('#eb-name', 'A2');
  await page.click('#eb-rename');
  await page.waitForTimeout(450);
  check('改名：A → A2（旧标签消失）', !!(await byLabel('A2')) && !(await byLabel('A')),
    (await state()).map((e) => e.label).join(','));
  const labelsBeforeDel = (await state()).map((e) => e.label).sort();
  await selectRow('B');
  await page.click('#eb-del');
  await page.waitForTimeout(450);
  const labelsAfterDel = (await state()).map((e) => e.label).sort();
  check('删除：B 及其依赖被级联删除', labelsAfterDel.length < labelsBeforeDel.length
    && labelsAfterDel.indexOf('B') === -1, labelsBeforeDel.join(',') + ' → ' + labelsAfterDel.join(','));

  // -------------------------------------------------------------------------
  section('C. 撤销 / 重做 / 清空按钮');
  await page.click('#btn-undo');
  await page.waitForTimeout(500);
  const labelsUndo = (await state()).map((e) => e.label).sort();
  check('撤销按钮：恢复删除前的标签集合', JSON.stringify(labelsUndo) === JSON.stringify(labelsBeforeDel),
    labelsUndo.join(',') + ' vs ' + labelsBeforeDel.join(','));
  await page.click('#btn-redo');
  await page.waitForTimeout(500);
  const labelsRedo = (await state()).map((e) => e.label).sort();
  check('重做按钮：回到删除后的状态', JSON.stringify(labelsRedo) === JSON.stringify(labelsAfterDel),
    labelsRedo.join(',') + ' vs ' + labelsAfterDel.join(','));
  await page.click('#btn-clear');
  await page.waitForTimeout(500);
  check('清空按钮：构造为空（confirm 自动确认）', (await state()).length === 0,
    String((await state()).length));

  // -------------------------------------------------------------------------
  section('D. CAS 面板');
  await page.click('#btn-cas');
  await page.waitForTimeout(500);
  const casVisible = await page.evaluate(() => document.getElementById('cas-panel').style.display !== 'none');
  check('CAS 面板打开', casVisible);
  await page.fill('#cas-cmd', 'Expand[(x+1)^2]');
  await page.click('#cas-go');
  await page.waitForTimeout(900);
  const cells = await page.$$eval('#cas-cells .cas-cell, #cas-cells > *', (els) => els.length);
  check('CAS 执行后出现单元', cells > 0, 'cells=' + cells);
  const casText = await page.textContent('#cas-cells');
  check('CAS 结果包含展开式 x^2+2x+1', /x\^?2|x²/i.test(casText || ''), (casText || '').replace(/\s+/g, ' ').slice(0, 60));
  await page.click('#btn-cas');
  await page.waitForTimeout(300);

  // -------------------------------------------------------------------------
  section('E. 分享按钮');
  await typeCmd('P1=(1,1)');
  await page.click('#btn-share');
  await page.waitForTimeout(900);
  const msgShare = await page.textContent('#msg');
  check('分享后状态栏给出链接（含 ?s=）', /(\?s=|share)/i.test(msgShare || ''), (msgShare || '').slice(0, 70));

  // -------------------------------------------------------------------------
  section('F. 图片插入');
  const pngPath = path.join(os.tmpdir(), 'ggbpy_ui_px.png');
  fs.writeFileSync(pngPath, Buffer.from(
    '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000a49444154789c6300010000050001' +
    '0d0a2db40000000049454e44ae426082', 'hex'));
  await page.click('#btn-image');
  await page.setInputFiles('#imgfile', pngPath);
  await page.waitForTimeout(900);
  const imgMsg = await page.textContent('#msg');
  check('选择图片后进入放置模式', /(点击图片左下角基点|Click the lower-left)/i.test(imgMsg || ''), (imgMsg || '').slice(0, 50));
  // 两次点击确定两个基点（图片工具需要 A、B 两个基点）
  await page.mouse.click(600, 430, { delay: 60 });
  await page.waitForTimeout(900);
  await page.mouse.click(900, 680, { delay: 60 });
  await page.waitForTimeout(1200);
  const imgEls = (await state()).filter((e) => e.kind === 'image');
  check('两次点击基点后创建 Image 元素', imgEls.length >= 1, 'n=' + imgEls.length);
  // 回归：0ms 快击（down→up 无间隔）曾导致待插入图片被清空。
  // 注意用 UI 清空（会同步刷新客户端 elements），否则客户端仍持有旧标签，工具判定会失真。
  await page.click('#btn-clear');
  await page.waitForTimeout(500);
  await page.click('#btn-image');
  await page.setInputFiles('#imgfile', pngPath);
  await page.waitForTimeout(700);
  await page.mouse.click(700, 500);            // 不传 delay → 瞬时点击
  await page.waitForTimeout(800);
  const ts1 = await page.evaluate(() => window.__ggbpyDebug.toolState());
  check('0ms 快击后仍保持待插入图片（pending=true）', ts1.pending === true, JSON.stringify(ts1));
  await page.mouse.click(1000, 700);
  await page.waitForTimeout(1100);
  const fastImgs = (await state()).filter((e) => e.kind === 'image');
  check('0ms 快击两次仍能插入图片', fastImgs.length >= 1, 'n=' + fastImgs.length);
  await page.click('#btn-clear');
  await page.waitForTimeout(400);

  // -------------------------------------------------------------------------
  section('G. 导出下载（SVG / PNG / .ggk）');
  for (const [btn, ext] of [['#btn-svg', '.svg'], ['#btn-png', '.png'], ['#btn-save', '.ggk']]) {
    const [dl] = await Promise.all([
      page.waitForEvent('download', { timeout: 15000 }).catch(() => null),
      page.click(btn),
    ]);
    check('导出按钮 ' + btn + ' 触发下载 ' + ext,
      !!dl && dl.suggestedFilename().toLowerCase().endsWith(ext),
      dl ? dl.suggestedFilename() : 'no download');
  }

  // -------------------------------------------------------------------------
  section('H. 2D 工具点击建点');
  await clear();
  await page.waitForTimeout(300);
  const ptTool = await page.$('#cat-tools .tool-btn[data-tool="point"]');
  check('存在「点」工具按钮', !!ptTool, ptTool ? 'ok' : 'missing');
  if (ptTool) {
    await ptTool.click();
    await page.waitForTimeout(250);
    await page.mouse.click(480, 420);
    await page.waitForTimeout(500);
    const n1 = (await state()).filter((e) => e.kind === 'point').length;
    check('画布点击创建点对象', n1 >= 1, 'points=' + n1);
  }

  // -------------------------------------------------------------------------
  section('I. 语言 / 主题切换不报错');
  const beforeLang = await page.textContent('#panel-title');
  await page.click('#btn-lang');
  await page.waitForTimeout(400);
  const afterLang = await page.textContent('#panel-title');
  check('语言切换改变界面文案', beforeLang !== afterLang, (afterLang || '').slice(0, 30));
  await page.click('#btn-lang');
  await page.waitForTimeout(300);
  await page.click('#btn-theme');
  await page.waitForTimeout(300);
  check('主题切换后页面仍可用（无致命错误）', JS_ERRORS.length === 0, JS_ERRORS.slice(0, 2).join(' | '));

  // -------------------------------------------------------------------------
  section('K2. 悬停提示：锚点在光标一侧 + 提示框完整可见');
  await clear();
  await page.waitForTimeout(300);
  await typeCmd('O=(0,0)');
  await typeCmd('c=Circle[O,3]');
  const cvBox = await page.$eval('#cv', (el) => {
    const r = el.getBoundingClientRect();
    return { x: r.x, y: r.y, w: r.width, h: r.height };
  });
  const geo = await page.evaluate(() => {
    const d = window.__ggbpyDebug.toScreen(0, 0);
    return { xmin: -d.x / d.scale, ymin: -(d.cssH - d.y) / d.scale, w: d.cssW / d.scale, h: d.cssH / d.scale,
             cssW: d.cssW, cssH: d.cssH };
  });
  const worldToPage = async (wx, wy) => {
    const s = await page.evaluate(([x, y]) => window.__ggbpyDebug.toScreen(x, y), [wx, wy]);
    return { x: cvBox.x + s.x, y: cvBox.y + s.y };
  };
  // 1) 圆的提示锚点必须落在圆上「离光标最近」的一侧
  const dirs = [['上', 0, 3.03, 0, 1], ['下', 0, -3.03, 0, -1], ['右', 3.03, 0, 1, 0], ['左', -3.03, 0, -1, 0]];
  let anchorOk = 0;
  const anchorDetail = [];
  for (const [nm, wx, wy, ex, ey] of dirs) {
    const pg = await worldToPage(wx, wy);
    await page.mouse.move(pg.x, pg.y);
    await page.waitForTimeout(260);
    const tip = await page.evaluate(() => window.__ggbpyDebug.hoverTip());
    if (tip) {
      // 锚点应朝光标方向：与单位方向向量的点积接近 r
      const dot = tip.x * ex + tip.y * ey;
      anchorDetail.push(nm + ':' + tip.x.toFixed(2) + ',' + tip.y.toFixed(2));
      if (dot > 2.9) anchorOk++;
    } else {
      anchorDetail.push(nm + ':null');
    }
  }
  check('圆/圆弧悬停锚点在光标一侧（4 个方向都对）', anchorOk === 4, anchorDetail.join(' '));
  // 2) 提示框必须完整落在画布内（含靠边翻转/夹取）
  const hoverableBottom = await page.evaluate(() => {
    const cv = document.getElementById('cv');
    const r = cv.getBoundingClientRect();
    for (let y = r.bottom - 6; y > r.top; y -= 6) {
      const el = document.elementFromPoint(r.left + r.width * 0.5, y);
      if (el && el.id === 'cv') return y - r.top;
    }
    return r.height;
  });
  const edgeCases = [
    ['顶部', geo.xmin + geo.w / 2, geo.ymin + geo.h - 0.35],
    ['左侧', geo.xmin + 0.35, geo.ymin + geo.h / 2],
    ['右侧', geo.xmin + geo.w - 0.35, geo.ymin + geo.h / 2],
  ];
  let edgeOk = 0;
  const edgeDetail = [];
  for (let i = 0; i < edgeCases.length; i++) {
    const [nm, wx, wy] = edgeCases[i];
    const lab = 'HT' + i;
    await typeCmd(lab + '=(' + wx.toFixed(2) + ',' + wy.toFixed(2) + ')');
    const pg = await worldToPage(wx, wy);
    await page.mouse.move(pg.x, pg.y);
    await page.waitForTimeout(300);
    const info = await page.evaluate(() => ({ rect: window.__ggbpyDebug.tipRect(), tip: window.__ggbpyDebug.hoverTip() }));
    const r = info.rect;
    const inside = !!r && r.x >= 0 && r.y >= 0 && r.x + r.w <= geo.cssW && r.y + r.h <= geo.cssH;
    if (inside && info.tip && info.tip.label === lab) edgeOk++;
    edgeDetail.push(nm + ':' + (r ? JSON.stringify(r) : 'null') + (inside ? '✓' : '✗'));
  }
  // 底部：只在画布可见（未被面板覆盖）时验证
  if (hoverableBottom > 40) {
    const wy = geo.ymin + (geo.cssH - hoverableBottom) / (geo.cssH / geo.h) + 0.3;
    await typeCmd('HTb=(' + (geo.xmin + geo.w / 2).toFixed(2) + ',' + wy.toFixed(2) + ')');
    const pg = await worldToPage(geo.xmin + geo.w / 2, wy);
    await page.mouse.move(pg.x, pg.y);
    await page.waitForTimeout(300);
    const info = await page.evaluate(() => ({ rect: window.__ggbpyDebug.tipRect(), tip: window.__ggbpyDebug.hoverTip() }));
    const r = info.rect;
    const inside = !!r && r.x >= 0 && r.y >= 0 && r.x + r.w <= geo.cssW && r.y + r.h <= geo.cssH;
    if (inside && info.tip && info.tip.label === 'HTb') edgeOk++;
    edgeDetail.push('底部:' + (r ? JSON.stringify(r) : 'null') + (inside ? '✓' : '✗'));
  }
  check('靠边悬停时提示框完整可见（自动翻转/夹取）', edgeOk === edgeCases.length + (hoverableBottom > 40 ? 1 : 0),
    edgeDetail.join(' '));
  // 3) 可用区：提示框必须避开停靠面板（面板是 DOM 浮层，画在画布内也会被盖住）
  const area = await page.evaluate(() => window.__ggbpyDebug.tipArea());
  const panelOverlaps = area.bottom < geo.cssH - 1 || area.left > 1 || area.right < geo.cssW - 1;
  check('可用区计算已扣除停靠面板（收缩了可见范围）', panelOverlaps, JSON.stringify(area));
  const areaBottomWorld = await page.evaluate(([cx, cy]) => {
    const d = window.__ggbpyDebug.toScreen(0, 0);
    const xmin = -d.x / d.scale, ymin = -(d.cssH - d.y) / d.scale;
    return { x: xmin + cx / d.scale, y: ymin + (d.cssH - cy) / d.scale };
  }, [geo.cssW * 0.5, area.bottom - 6]);
  await typeCmd('HTarea=(' + areaBottomWorld.x.toFixed(2) + ',' + areaBottomWorld.y.toFixed(2) + ')');
  const areaScreen = await page.evaluate(([wx, wy]) => window.__ggbpyDebug.toScreen(wx, wy),
    [areaBottomWorld.x, areaBottomWorld.y]);
  await page.mouse.move(cvBox.x + areaScreen.x, cvBox.y + areaScreen.y);
  await page.waitForTimeout(320);
  const areaInfo = await page.evaluate(() => ({ rect: window.__ggbpyDebug.tipRect(), tip: window.__ggbpyDebug.hoverTip() }));
  const rArea = areaInfo.rect;
  const inArea = !!rArea && rArea.x >= area.left && rArea.y >= area.top
    && rArea.x + rArea.w <= area.right && rArea.y + rArea.h <= area.bottom;
  check('面板上沿附近悬停：提示框落在可用区内（不再被抓一半）', inArea && !!areaInfo.tip,
    (rArea ? JSON.stringify(rArea) : 'null') + ' 可用区=' + JSON.stringify(area));

  // -------------------------------------------------------------------------
  section('K. 会话隔离（cookie 持久 + 新上下文独立）');
  await clear();
  await page.waitForTimeout(300);
  await typeCmd('SESS1=(1,1)');
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(500);
  const afterReload = await state();
  check('同页面刷新后构造保留（cookie 会话持久）',
    afterReload.some((e) => e.label === 'SESS1'), afterReload.map((e) => e.label).join(','));
  const ctx2 = await browser.newContext();
  const page2 = await ctx2.newPage();
  await page2.goto(BASE + '/', { waitUntil: 'networkidle' });
  await page2.waitForTimeout(300);
  const st2 = await (await page2.request.get(BASE + '/api/state')).json();
  check('新浏览器上下文 → 独立空会话', ((st2 || {}).elements || []).length === 0,
    'n=' + ((st2 || {}).elements || []).length);
  await page2.request.post(BASE + '/api/input', { data: { text: 'OTHER=(9,9)' } });
  await page2.waitForTimeout(300);
  const st1 = await state();
  check('新会话写入不影响原会话', !st1.some((e) => e.label === 'OTHER'),
    st1.map((e) => e.label).join(','));
  const st2b = await (await page2.request.get(BASE + '/api/state')).json();
  check('新会话自己能看到自己的对象',
    ((st2b || {}).elements || []).some((e) => e.label === 'OTHER'),
    ((st2b || {}).elements || []).map((e) => e.label).join(','));
  await ctx2.close();

  // -------------------------------------------------------------------------
  section('J. JS 错误');
  check('全流程无未捕获 JS 错误', JS_ERRORS.length === 0, JS_ERRORS.slice(0, 3).join(' | '));

  await browser.close();
  console.log('\n' + '='.repeat(56));
  console.log('2D 前端检测矩阵 @ ' + BASE + '：' + (PASS + FAIL) + ' 项断言，' + FAIL + ' 失败');
  if (FAIL) {
    for (const n of FAILED) console.log('  FAILED: ' + n);
    console.log('结果: FAILED');
    process.exit(1);
  }
  console.log('结果: ALL PASS');
  process.exit(0);
})().catch((e) => { console.error('FATAL', e); process.exit(1); });
