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
  const dialogQueue = [];                       // 统计图工具需要输入数据 → 排队应答
  page.on('dialog', async (d) => { await d.accept(dialogQueue.length ? dialogQueue.shift() : ''); });

  // 顶部按钮已收进下拉菜单（文件/导出/导入/视图/工具）：点击前先展开所在菜单
  const clickBtn = async (id) => {
    await page.evaluate((bid) => {
      const el = document.getElementById(bid);
      const menu = el && el.closest ? el.closest('#toolbar .menu') : null;
      if (menu && !menu.classList.contains('open')) {
        const head = menu.querySelector('.menu-btn');
        if (head) head.click();
      }
    }, id);
    await page.waitForTimeout(120);
    await page.click('#' + id);
  };

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
  await clickBtn('btn-undo');
  await page.waitForTimeout(500);
  const labelsUndo = (await state()).map((e) => e.label).sort();
  check('撤销按钮：恢复删除前的标签集合', JSON.stringify(labelsUndo) === JSON.stringify(labelsBeforeDel),
    labelsUndo.join(',') + ' vs ' + labelsBeforeDel.join(','));
  await clickBtn('btn-redo');
  await page.waitForTimeout(500);
  const labelsRedo = (await state()).map((e) => e.label).sort();
  check('重做按钮：回到删除后的状态', JSON.stringify(labelsRedo) === JSON.stringify(labelsAfterDel),
    labelsRedo.join(',') + ' vs ' + labelsAfterDel.join(','));
  await clickBtn('btn-clear');
  await page.waitForTimeout(500);
  check('清空按钮：构造为空（confirm 自动确认）', (await state()).length === 0,
    String((await state()).length));

  // -------------------------------------------------------------------------
  section('D. CAS 面板');
  await clickBtn('btn-cas');
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
  await clickBtn('btn-cas');
  await page.waitForTimeout(300);

  // -------------------------------------------------------------------------
  section('E. 分享按钮');
  await typeCmd('P1=(1,1)');
  await clickBtn('btn-share');
  await page.waitForTimeout(900);
  const msgShare = await page.textContent('#msg');
  check('分享后状态栏给出链接（含 ?s=）', /(\?s=|share)/i.test(msgShare || ''), (msgShare || '').slice(0, 70));

  // -------------------------------------------------------------------------
  section('F. 图片插入');
  const pngPath = path.join(os.tmpdir(), 'ggbpy_ui_px.png');
  fs.writeFileSync(pngPath, Buffer.from(
    '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000a49444154789c6300010000050001' +
    '0d0a2db40000000049454e44ae426082', 'hex'));
  await clickBtn('btn-image');
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
  await clickBtn('btn-clear');
  await page.waitForTimeout(500);
  await clickBtn('btn-image');
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
  await clickBtn('btn-clear');
  await page.waitForTimeout(400);

  // -------------------------------------------------------------------------
  section('G. 导出下载（SVG / PNG / .ggk）');
  for (const [btn, ext] of [['#btn-svg', '.svg'], ['#btn-png', '.png'], ['#btn-save', '.ggk']]) {
    const [dl] = await Promise.all([
      page.waitForEvent('download', { timeout: 15000 }).catch(() => null),
      clickBtn(btn.replace('#', '')),                   // 菜单项：先展开所在下拉菜单
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
  await clickBtn('btn-lang');
  await page.waitForTimeout(400);
  const afterLang = await page.textContent('#panel-title');
  check('语言切换改变界面文案', beforeLang !== afterLang, (afterLang || '').slice(0, 30));
  await clickBtn('btn-lang');
  await page.waitForTimeout(300);
  await clickBtn('btn-theme');
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
  // 2b) 反演工具创建的图形用 inv 命名（点仍用大写字母）
  await clear();
  await page.waitForTimeout(300);
  await typeCmd('O=(0,0)');
  await typeCmd('k=Circle[O,2]');
  await typeCmd('S1=(4,0)');
  await typeCmd('S2=(4,1)');
  await typeCmd('ss=Segment[S1,S2]');
  const cvBoxInv = await page.$eval('#cv', (el) => {
    const r = el.getBoundingClientRect();
    return { x: r.x, y: r.y };
  });
  const catTransform = await page.$('.cat-icon[data-cat="transformers"]');   // 反演工具在「变换」分类下
  if (catTransform) { await catTransform.click(); await page.waitForTimeout(250); }
  const invTool = await page.$('#cat-tools .tool-btn[data-tool="invert"]');
  if (invTool) {
    await invTool.click();
    await page.waitForTimeout(200);
    const atW = async (wx, wy) => {
      const s = await page.evaluate(([x, y]) => window.__ggbpyDebug.toScreen(x, y), [wx, wy]);
      return { x: cvBoxInv.x + s.x, y: cvBoxInv.y + s.y };
    };
    let p1 = await atW(4, 0.5);            // 点击要反演的线段
    await page.mouse.click(p1.x, p1.y);
    await page.waitForTimeout(300);
    let p2 = await atW(0, 2);              // 点击反演圆
    await page.mouse.click(p2.x, p2.y);
    await page.waitForTimeout(500);
    const labels = await state();
    const invLabels = labels.map((e) => e.label).filter((l) => /^inv\d+$/.test(l));
    check('反演工具创建的图形命名为 inv1（小写前缀）', invLabels.length === 1 && invLabels[0] === 'inv1',
      labels.map((e) => e.label).join(','));
    // 点反演仍是点命名（大写字母）：比对新增标签，避免被已有大写标签蒙过
    const before2 = new Set((await state()).map((e) => e.label));
    // 反演工具用完后会保持激活（GGB 式），此时再点按钮反而会取消工具 → 按状态决定
    const ts = await page.evaluate(() => window.__ggbpyDebug.toolState());
    if (!ts || ts.activeTool !== 'invert') {
      const invTool2 = await page.$('#cat-tools .tool-btn[data-tool="invert"]');
      await invTool2.click();
      await page.waitForTimeout(200);
    }
    p1 = await atW(4, 0);                  // 点击点 S1
    await page.mouse.click(p1.x, p1.y);
    await page.waitForTimeout(300);
    p2 = await atW(0, 2);
    await page.mouse.click(p2.x, p2.y);
    await page.waitForTimeout(500);
    const added2 = (await state()).map((e) => e.label).filter((l) => !before2.has(l));
    check('反演工具对点仍用点命名（单大写字母）',
      added2.length === 1 && /^[A-Z]$/.test(added2[0]),
      '新增=' + added2.join(','));
  } else {
    check('存在反演工具按钮', false, '未找到 .tool-btn[data-tool="invert"]');
  }

  // 3) 文字必须在提示框内垂直居中且填满（此前沿用了上一个元素残留的 textBaseline，
  //    文字整体偏低半个框高 → 看起来"只露一半"）
  const tipInk = async (wx, wy) => {
    const pg = await worldToPage(wx, wy);
    await page.mouse.move(pg.x, pg.y);
    await page.waitForTimeout(320);
    return page.evaluate(() => {
      const cvEl = document.getElementById('cv');
      const ctx = cvEl.getContext('2d');
      const rect = window.__ggbpyDebug.tipRect();
      if (!rect) return null;
      const k = cvEl.width / cvEl.clientWidth;
      const x0 = Math.round(rect.x * k), y0 = Math.round(rect.y * k);
      const w = Math.max(1, Math.round(rect.w * k)), h = Math.max(1, Math.round(rect.h * k));
      const img = ctx.getImageData(x0, y0, w, h).data;
      // 文字墨迹 = 接近提示前景色的像素（前景色由 tipColors 给出，亮/暗主题都对）
      const fgHex = window.__ggbpyDebug.tipColors().fg.replace('#', '');
      const fr = parseInt(fgHex.slice(0, 2), 16), fgc = parseInt(fgHex.slice(2, 4), 16), fb = parseInt(fgHex.slice(4, 6), 16);
      let ix0 = 1e9, iy0 = 1e9, ix1 = -1, iy1 = -1, n = 0;
      for (let y = 0; y < h; y++) {
        for (let x = 0; x < w; x++) {
          const i = (y * w + x) * 4;
          if (Math.abs(img[i] - fr) <= 40 && Math.abs(img[i + 1] - fgc) <= 40 && Math.abs(img[i + 2] - fb) <= 40) {
            n++; if (x < ix0) ix0 = x; if (y < iy0) iy0 = y; if (x > ix1) ix1 = x; if (y > iy1) iy1 = y;
          }
        }
      }
      return { rect, box: { w, h }, ink: n ? { x0: ix0, y0: iy0, x1: ix1, y1: iy1, n } : null,
               tip: window.__ggbpyDebug.hoverTip() };
    });
  };
  await typeCmd('TPINK=(0,5)');
  const ink = await tipInk(0, 5);
  if (!ink || !ink.ink) {
    check('提示文字已绘制（可测量墨迹）', false, JSON.stringify(ink));
  } else {
    const i0 = ink.ink, bw = ink.box.w, bh = ink.box.h;
    const inkH = i0.y1 - i0.y0 + 1, inkCy = (i0.y0 + i0.y1) / 2, boxCy = (bh - 1) / 2;
    check('提示文字完整落在提示框内（上下留边）', i0.y0 >= 1 && i0.y1 <= bh - 2 && i0.x0 >= 1 && i0.x1 <= bw - 2,
      'ink=' + JSON.stringify(i0) + ' box=' + JSON.stringify(ink.box));
    check('提示文字垂直居中（不再偏低半框）', Math.abs(inkCy - boxCy) <= 2,
      '文字中心=' + inkCy.toFixed(1) + ' 框中心=' + boxCy.toFixed(1));
    check('提示文字填满提示框（字高 ≥ 60% 框高）', inkH / bh >= 0.60,
      (inkH / bh * 100).toFixed(0) + '%');
  }
  // 其它对象（属性太多）只提示名称：直线
  await typeCmd('TLINE=Line[(0,0),(1,0.3)]');
  const lineTip = await tipInk(6, 1.8);
  check('直线悬停只显示名称（不堆属性）',
    !!lineTip && !!lineTip.tip && lineTip.tip.nameOnly === true && lineTip.tip.text === 'TLINE',
    JSON.stringify(lineTip && lineTip.tip));

  // 4) 可用区：提示框必须避开停靠面板（面板是 DOM 浮层，画在画布内也会被盖住）
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
  section('K3. 统计图：整张图可拖动 + 新图型渲染');
  await clear();
  await page.waitForTimeout(300);
  for (const line of ['D={3,1,4,1,5,9,2,6}', 'bc=BarChart[D]', 'lc=LineChart[D]',
                      'sc=ScatterPlot[{(1,2),(2,4),(3,3),(4,6)}]', 'dp=DotPlot[{1,2,2,3,1,3,3}]',
                      'bp=BoxPlot[D]']) {
    await typeCmd(line);
  }
  await page.waitForTimeout(300);
  // 1) 六种统计图都有命中盒、且渲染出各自颜色
  const chartBoxes = await page.evaluate(() => window.__ggbpyDebug.chartBoxes());
  check('五种统计图（柱/箱/折线/散点/点图）都有拖拽命中盒',
    ['bc', 'lc', 'sc', 'dp', 'bp'].every((l) => !!chartBoxes[l]),
    Object.keys(chartBoxes).join(','));
  const chartPx = await page.evaluate(() => {
    const cv = document.getElementById('cv');
    const ctx = cv.getContext('2d');
    const img = ctx.getImageData(0, 0, cv.width, cv.height).data;
    let line = 0, scat = 0, dot = 0;
    for (let i = 0; i < img.length; i += 4) {
      const r = img[i], g = img[i + 1], b = img[i + 2];
      if (Math.abs(r - 37) < 26 && Math.abs(g - 99) < 26 && Math.abs(b - 235) < 26) line++;
      if (Math.abs(r - 220) < 26 && Math.abs(g - 38) < 26 && Math.abs(b - 38) < 26) scat++;
      if (Math.abs(r - 124) < 26 && Math.abs(g - 58) < 26 && Math.abs(b - 237) < 26) dot++;
    }
    return { line, scat, dot };
  });
  check('折线/散点/点图都绘出了各自颜色',
    chartPx.line > 50 && chartPx.scat > 30 && chartPx.dot > 30, JSON.stringify(chartPx));
  // 饼图单独建（它很大，会盖住其它小图），再查像素
  await typeCmd('pi=PieChart[{3,5,2,4}]');
  await page.waitForTimeout(300);
  const piePx = await page.evaluate(() => {
    const cv = document.getElementById('cv');
    const ctx = cv.getContext('2d');
    const img = ctx.getImageData(0, 0, cv.width, cv.height).data;
    let pie = 0;
    for (let i = 0; i < img.length; i += 4) {
      const r = img[i], g = img[i + 1], b = img[i + 2];
      if (Math.abs(r - 239) < 30 && Math.abs(g - 68) < 30 && Math.abs(b - 68) < 30) pie++;
    }
    return pie;
  });
  check('饼图绘出扇区', piePx > 200, String(piePx));
  const pieBox = await page.evaluate(() => window.__ggbpyDebug.chartBoxes().pi);
  check('饼图也有拖拽命中盒', !!pieBox, JSON.stringify(pieBox));
  // 2) 拖动柱状图：offset 与命中盒同步位移
  // 清场：退出选择模式 + 取消任何激活的作图工具（否则 pointerdown 会被工具拦截）
  if (await page.evaluate(() => window.__ggbpyDebug.selectMode())) {
    await clickBtn('btn-select');
    await page.waitForTimeout(200);
  }
  const tsDrag = await page.evaluate(() => window.__ggbpyDebug.toolState());
  if (tsDrag && tsDrag.activeTool) {
    const tbtn = await page.$('#cat-tools .tool-btn[data-tool="' + tsDrag.activeTool + '"]');
    if (tbtn) { await tbtn.click(); await page.waitForTimeout(200); }
  }
  const box0 = (await page.evaluate(() => window.__ggbpyDebug.chartBoxes())).bc;
  const cx0 = cvBox.x + (box0.x0 + box0.x1) / 2, cy0 = cvBox.y + (box0.y0 + box0.y1) / 2;
  const beforeOff = await (await page.request.get(BASE + '/api/state')).json();
  const off0 = (beforeOff.elements.find((e) => e.label === 'bc') || {}).offset;
  await page.mouse.move(cx0, cy0);
  await page.mouse.down();
  await page.mouse.move(cx0 + 130, cy0 - 70, { steps: 8 });
  await page.waitForTimeout(400);
  await page.mouse.up();
  await page.waitForTimeout(400);
  const afterState = await (await page.request.get(BASE + '/api/state')).json();
  const off1 = (afterState.elements.find((e) => e.label === 'bc') || {}).offset;
  const box1 = await page.evaluate(() => window.__ggbpyDebug.chartBoxes().bc);
  const dBoxX = Math.round(box1.x0 - box0.x0), dBoxY = Math.round(box1.y0 - box0.y0);
  check('拖动统计图 → 整张图整体位移（命中盒位移 = 鼠标位移）',
    off1 && (off1[0] !== off0[0] || off1[1] !== off0[1]) && Math.abs(dBoxX - 130) <= 3 && Math.abs(dBoxY + 70) <= 3,
    'offset ' + JSON.stringify(off0) + '→' + JSON.stringify(off1) + ' 盒位移=' + dBoxX + ',' + dBoxY);
  // 3) 撤销回退整体移动
  await page.evaluate(() => fetch('/api/undo', { method: 'POST' }));
  await page.waitForTimeout(300);
  const undoState = await (await page.request.get(BASE + '/api/state')).json();
  const off2 = (undoState.elements.find((e) => e.label === 'bc') || {}).offset;
  check('撤销回退统计图整体移动', off2 && Math.abs(off2[0] - off0[0]) < 1e-6 && Math.abs(off2[1] - off0[1]) < 1e-6,
    JSON.stringify(off2));
  // 4) 悬停统计图 → 只提示名称
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(500);
  const box2 = await page.evaluate(() => window.__ggbpyDebug.chartBoxes().bc);
  await page.mouse.move(cvBox.x + (box2.x0 + box2.x1) / 2, cvBox.y + (box2.y0 + box2.y1) / 2);
  await page.waitForTimeout(320);
  const chTip = await page.evaluate(() => window.__ggbpyDebug.hoverTip());
  check('悬停统计图提示名称（不堆数据）',
    !!chTip && chTip.nameOnly === true, JSON.stringify(chTip));

  // -------------------------------------------------------------------------
  section('K4. 统计图菜单入口（工具按钮建图）');
  await clear();
  await page.waitForTimeout(300);
  const chartsCat = await page.$('.cat-icon[data-cat="charts"]');
  check('工具栏有「统计图」分类按钮', !!chartsCat, '');
  if (chartsCat) {
    await chartsCat.click();
    await page.waitForTimeout(300);
  }
  const chartToolKeys = await page.$$eval('#cat-tools .tool-btn[data-tool]', (els) => els.map((e) => e.getAttribute('data-tool')));
  const expectTools = ['barchart', 'histogram', 'boxplot', 'piechart', 'linechart', 'scatterplot', 'dotplot',
                       'barchart3d', 'scatterplot3d', 'surfacechart3d'];
  check('统计图分类含 10 个工具按钮（2D 七类 + 3D 三类）',
    expectTools.every((k) => chartToolKeys.indexOf(k) !== -1), chartToolKeys.join(','));
  // 分类登记不重复（用户反馈：计算 / 统计图 两处都有「直方图」）
  const catDup = await page.evaluate(() => {
    const seen = {}, dup = [];
    (window.GGB_DATA.TOOL_CATS || []).forEach((c) => (c.tools || []).forEach((t) => {
      if (seen[t]) dup.push(t + ':' + seen[t] + '+' + c.id); else seen[t] = c.id;
    }));
    return dup;
  });
  check('工具分类无重复登记（同一工具只属一个分类）', catDup.length === 0, catDup.join(','));
  // 全分类逐项校验：id 唯一 / 非空 / def ∈ tools / 渲染按钮集合 == 数据定义
  const catDefs = await page.evaluate(() => (window.GGB_DATA.TOOL_CATS || []).map((c) => ({
    id: c.id, tools: c.tools || [], def: c.def || null,
  })));
  const dupCatIds = catDefs.map((c) => c.id).filter((v, i, a) => a.indexOf(v) !== i);
  check('分类 id 唯一', dupCatIds.length === 0, dupCatIds.join(','));
  const emptyCats = catDefs.filter((c) => !c.tools.length).map((c) => c.id);
  check('每个分类都有工具（无空分类）', emptyCats.length === 0, emptyCats.join(','));
  const badDefCat = catDefs.filter((c) => c.def && c.tools.indexOf(c.def) === -1).map((c) => c.id);
  check('每个分类的默认工具 def 都在其 tools 内', badDefCat.length === 0, badDefCat.join(','));
  const catMismatch = [];
  for (const c of catDefs) {
    const icon = await page.$('.cat-icon[data-cat="' + c.id + '"]');
    if (!icon) { catMismatch.push(c.id + ':无分类按钮'); continue; }
    await icon.click();
    await page.waitForTimeout(180);
    const keys = await page.$$eval('#cat-tools .tool-btn[data-tool]', (els) => els.map((e) => e.getAttribute('data-tool')));
    const miss = c.tools.filter((t) => keys.indexOf(t) === -1);
    const extra = keys.filter((k) => c.tools.indexOf(k) === -1);
    if (miss.length || extra.length) catMismatch.push(c.id + ':缺' + miss.join('/') + '多' + extra.join('/'));
  }
  check('全部 ' + catDefs.length + ' 个分类的渲染按钮集合 = 数据定义（逐分类校验）',
    catMismatch.length === 0, catMismatch.join(';'));
  const calcCatIcon = await page.$('.cat-icon[data-cat="calculates"]');
  if (calcCatIcon) { await calcCatIcon.click(); await page.waitForTimeout(250); }
  const calcKeys = await page.$$eval('#cat-tools .tool-btn[data-tool]', (els) => els.map((e) => e.getAttribute('data-tool')));
  const calcTexts = await page.$$eval('#cat-tools .tool-btn', (els) => els.map((e) => e.textContent.trim()));
  check('「计算」分类不含直方图（barchart 仅归统计图）', calcKeys.indexOf('barchart') === -1, calcKeys.join(','));
  check('「计算」分类按钮文案里没有「直方图」', calcTexts.indexOf('直方图') === -1, calcTexts.join(','));
  if (chartsCat) { await chartsCat.click(); await page.waitForTimeout(250); }
  const backKeys = await page.$$eval('#cat-tools .tool-btn[data-tool]', (els) => els.map((e) => e.getAttribute('data-tool')));
  check('「统计图」分类仍含直方图（功能未丢）', backKeys.indexOf('barchart') !== -1, backKeys.join(','));

  const clickChartTool = async (tool, answers, wait) => {
    dialogQueue.push(...answers);
    const btn = await page.$('#cat-tools .tool-btn[data-tool="' + tool + '"]');
    if (!btn) return false;
    await btn.click();
    await page.waitForTimeout(wait || 600);
    return true;
  };
  await clickChartTool('linechart', ['1,3,2,5']);
  await clickChartTool('scatterplot', ['1,2; 3,4; 5,3']);
  await clickChartTool('dotplot', ['1,2,2,3']);
  await clickChartTool('piechart', ['3,5,2,4']);
  const afterTools = await state();
  const kinds = afterTools.map((e) => e.kind);
  check('点「折线图」按钮 → 建出 linechart',
    afterTools.some((e) => e.kind === 'linechart' && /^lc\d+$/.test(e.label)),
    afterTools.map((e) => e.label + ':' + e.kind).join(','));
  check('点「散点图」按钮 → 建出 scatterplot（解析 1,2; 3,4 输入）',
    afterTools.some((e) => e.kind === 'scatterplot'), kinds.join(','));
  check('点「点图」/「饼图」按钮 → 建出 dotplot + piechart',
    kinds.indexOf('dotplot') !== -1 && kinds.indexOf('piechart') !== -1, kinds.join(','));
  // 3D 统计图工具（无需切模式，点按钮即输入）
  await clickChartTool('barchart3d', ['1,3,2,4'], 700);
  await clickChartTool('surfacechart3d', ['1,2,3,2,3,4', '3'], 700);
  const st3tools = await (await page.request.get(BASE + '/api/state3d')).json();
  const mesh3 = (st3tools.elements || []).filter((e) => e.objtype === 'polyhedron' && e.solid && e.solid.indexOf('chart_') === 0);
  check('点「三维柱状图/三维曲面图」按钮 → state3d 出现统计图网格',
    mesh3.length >= 2 && mesh3.every((e) => ((e.data || {}).verts || []).length > 0),
    mesh3.map((e) => e.label + ':' + ((e.data || {}).verts || []).length + 'v').join(' '));

  // -------------------------------------------------------------------------
  section('K5. 数学键盘面板（static/keyboard.js）');
  await clear();
  await page.waitForTimeout(250);
  await clickBtn('btn-kbd');
  await page.waitForTimeout(250);
  const kbState = await page.evaluate(() => ({
    open: window.__ggbpyKb ? window.__ggbpyKb.isOpen() : null,
    display: getComputedStyle(document.getElementById('mathkb')).display,
  }));
  check('点 ⌨ 展开数学键盘', kbState.open === true && kbState.display !== 'none', JSON.stringify(kbState));
  await page.fill('#cmd', '');
  await page.evaluate(() => document.getElementById('cmd').focus());
  for (const k of ['7', '*', 'sqrt(']) {          // 面板实际按键：数字 / 算符 / 函数名
    await page.click('#mathkb .kb-key[data-k="' + k + '"]');
    await page.waitForTimeout(80);
  }
  const kbVal1 = await page.inputValue('#cmd');
  check('点按键插入到输入框', kbVal1 === '7*sqrt(', JSON.stringify(kbVal1));
  await page.click('#mathkb .kb-key[data-k="bs"]');
  await page.waitForTimeout(80);
  const kbVal2 = await page.inputValue('#cmd');
  check('退格键删除末位', kbVal2 === '7*sqrt', JSON.stringify(kbVal2));
  await page.click('#mathkb .kb-key[data-k="clear"]');
  await page.waitForTimeout(80);
  check('清空键清空输入框', (await page.inputValue('#cmd')) === '', '');
  await clickBtn('btn-kbd');
  await page.waitForTimeout(200);
  check('再点 ⌨ 收起键盘', (await page.evaluate(() => window.__ggbpyKb.isOpen())) === false, '');

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
  section('V. 控件/滑块锚点拖动（点击=动作 / 拖动=移位）');
  const wdErrBefore = JS_ERRORS.length;
  await typeCmd('vC=Circle[(0,0),2]');
  await typeCmd('vBT=Button["跑脚本", "vA=(2,2)", (-4,4)]');
  await typeCmd('vSL=Slider[0,10,1,(-1,-3)]');
  await page.waitForTimeout(500);
  const vRect = await page.evaluate(() => { const r = document.getElementById('cv').getBoundingClientRect(); return { x: r.x, y: r.y }; });
  const vBoxes = await page.evaluate(() => window.__ggbpyDebug.widgetBoxes());
  // ① 拖动按钮：应移动位置且**不执行脚本**
  const bt = vBoxes['vBT'];
  const bx = vRect.x + (bt.x0 + bt.x1) / 2, by = vRect.y + (bt.y0 + bt.y1) / 2;
  await page.mouse.move(bx, by);
  await page.mouse.down();
  await page.mouse.move(bx + 80, by - 50, { steps: 6 });
  await page.mouse.up();
  await page.waitForTimeout(500);
  const vEls1 = ((await (await page.request.get(BASE + '/api/state')).json()).elements) || [];
  const vBT1 = vEls1.filter((e) => e.label === 'vBT')[0];
  check('拖动按钮改变锚点（defn 同步重写）',
        !!vBT1 && String(vBT1.defn).indexOf('Button[') >= 0 && String(vBT1.defn) !== 'vBT=Button["跑脚本", "vA=(2,2)", (-4,4)]',
        vBT1 && vBT1.defn);
  check('拖动按钮不会执行脚本（无 vA 元素）', !vEls1.some((e) => e.label === 'vA'),
        String(vEls1.map((e) => e.label)));
  // ② 点击按钮：仍应执行脚本（回归）
  const bt2 = (await page.evaluate(() => window.__ggbpyDebug.widgetBoxes()))['vBT'];
  await page.mouse.click(vRect.x + (bt2.x0 + bt2.x1) / 2, vRect.y + (bt2.y0 + bt2.y1) / 2);
  await page.waitForTimeout(500);
  const vEls2 = ((await (await page.request.get(BASE + '/api/state')).json()).elements) || [];
  check('点击按钮仍执行脚本（vA 出现）', vEls2.some((e) => e.label === 'vA'), String(vEls2.map((e) => e.label)));
  // ③ 拖滑块轨道（远离滑钮）：位置变、值不变
  const sl2 = (await page.evaluate(() => window.__ggbpyDebug.widgetBoxes()))['vSL'];
  const slValBefore = (vEls2.filter((e) => e.label === 'vSL')[0] || {}).val;
  const trackX = vRect.x + sl2.x1 - 6, trackY = vRect.y + (sl2.y0 + sl2.y1) / 2;
  await page.mouse.move(trackX, trackY);
  await page.mouse.down();
  await page.mouse.move(trackX + 60, trackY - 40, { steps: 6 });
  await page.mouse.up();
  await page.waitForTimeout(500);
  const vEls3 = ((await (await page.request.get(BASE + '/api/state')).json()).elements) || [];
  const vSL3 = vEls3.filter((e) => e.label === 'vSL')[0] || {};
  check('拖滑块轨道移动整条滑块（位置变、数值不变）',
        String(vSL3.defn).indexOf('Slider[') >= 0 && String(vSL3.defn).indexOf('(-1,-3)') < 0
        && Math.abs(Number(vSL3.val) - Number(slValBefore)) < 1e-9,
        'defn=' + vSL3.defn + ' val=' + slValBefore + '→' + vSL3.val);
  check('锚点拖动无新增 JS 错误', JS_ERRORS.length === wdErrBefore,
        JS_ERRORS.slice(wdErrBefore).join(';').slice(0, 60));

  section('U. 画布滑块（线段 + 滑钮：渲染与拖动）');
  const slErrBefore = JS_ERRORS.length;
  await typeCmd('uS=Slider[0,10,1,(-2,2)]');
  await page.waitForTimeout(450);
  const slBox = await page.evaluate(() => window.__ggbpyDebug.widgetBoxes()['uS'] || null);
  check('滑块在画布上登记线段命中框（kind=slider）',
        !!slBox && slBox.kind === 'slider' && (slBox.x1 - slBox.x0) > 100 && typeof slBox.wx0 === 'number',
        JSON.stringify(slBox));
  const slRect = await page.evaluate(() => { const r = document.getElementById('cv').getBoundingClientRect(); return { x: r.x, y: r.y }; });
  const slY = slRect.y + (slBox.y0 + slBox.y1) / 2;
  const slX0 = slRect.x + slBox.x0 + 10, slX1 = slRect.x + slBox.x1 - 10;
  await page.mouse.move(slX0, slY);
  await page.mouse.down();
  await page.mouse.move(slX0 + (slX1 - slX0) * 0.7, slY, { steps: 6 });
  await page.mouse.up();
  await page.waitForTimeout(500);
  const slEl = (((await (await page.request.get(BASE + '/api/state')).json()).elements) || []).filter((e) => e.label === 'uS')[0];
  check('拖动滑钮改变数值（≈70% → 7，按步长吸附）',
        !!slEl && Math.abs(Number(slEl.val) - 7) < 1e-9, 'val=' + (slEl && slEl.val));
  const slEl2 = (((await (await page.request.get(BASE + '/api/state')).json()).elements) || []).filter((e) => e.label === 'uS')[0];
  check('拖动后滑块仍是滑块（defn/min 保留、几何不丢）',
        !!slEl2 && String(slEl2.defn).indexOf('Slider[') >= 0 && slEl2.min === 0,
        JSON.stringify({ defn: slEl2 && slEl2.defn, min: slEl2 && slEl2.min }));
  check('滑块拖动无新增 JS 错误', JS_ERRORS.length === slErrBefore,
        JS_ERRORS.slice(slErrBefore).join(';').slice(0, 60));

  section('W. 双击控件就地改说明/脚本');
  const edErrBefore = JS_ERRORS.length;
  await typeCmd('edB=Button["旧说明", "edA=(1,1)", (-4,-4)]');
  await page.waitForTimeout(450);
  const edRect = await page.evaluate(() => { const r = document.getElementById('cv').getBoundingClientRect(); return { x: r.x, y: r.y }; });
  const edBox = await page.evaluate(() => window.__ggbpyDebug.widgetBoxes()['edB']);
  dialogQueue.push('新说明');       // 说明
  dialogQueue.push('edA=(2,2)');    // 脚本
  await page.mouse.dblclick(edRect.x + (edBox.x0 + edBox.x1) / 2, edRect.y + (edBox.y0 + edBox.y1) / 2);
  await page.waitForTimeout(700);
  const edEl = (((await (await page.request.get(BASE + '/api/state')).json()).elements) || []).filter((e) => e.label === 'edB')[0] || {};
  check('双击按钮改说明与脚本（defn 同步重写）',
        edEl.caption === '新说明' && String(edEl.script).indexOf('edA=(2,2)') >= 0
        && String(edEl.defn).indexOf('新说明') >= 0,
        JSON.stringify({ caption: edEl.caption, script: edEl.script, defn: edEl.defn }));
  // 对象列表行双击 → 同一编辑器
  await typeCmd('edB2=Button["旧行说明", "edA2=(1,1)", (-3,3)]');
  await page.waitForTimeout(450);
  dialogQueue.push('行内新说明');
  dialogQueue.push('edA2=(5,5)');
  const edSel = '#objlist .obj[data-label="edB2"] .kd';
  await page.click(edSel);          // 第一次点击（列表会重渲染）
  await page.waitForTimeout(120);
  await page.click(edSel);          // 第二次点击 → 计时判定为双击
  await page.waitForTimeout(700);
  const edEl2 = (((await (await page.request.get(BASE + '/api/state')).json()).elements) || []).filter((e) => e.label === 'edB2')[0] || {};
  check('双击对象列表行改说明/脚本（与画布双击同一编辑器）',
        edEl2.caption === '行内新说明' && String(edEl2.script).indexOf('edA2=(5,5)') >= 0,
        JSON.stringify({ caption: edEl2.caption, script: edEl2.script }));
  // .df 定义式单元格：合成两次 pointerdown 驱动「计时双击」判定。
  // 已知限制：列表重渲染会让第二次真实点击落到别的行/元素（Playwright 的选择器重解析、
  // 固定坐标、原生 mouse.dblclick 三种方式都试过均不稳定），因此这里直接驱动判定逻辑本身；
  // 控件行用例（上一段）仍用真实点击。
  await typeCmd('edN=3');
  await page.waitForTimeout(400);
  await page.evaluate(() => {
    const df = document.querySelector('#objlist .obj[data-label="edN"] .df');
    df.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true }));
    return new Promise((res) => setTimeout(() => {
      df.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true }));
      res(true);
    }, 120));
  });
  await page.waitForTimeout(400);
  const dfInput = await page.$('#objlist .obj[data-label="edN"] .df input.df-edit');
  check('计时双击 .df 打开行内定义编辑（原生 dblclick 失效已修）', !!dfInput, String(!!dfInput));
  if (dfInput) {
    await dfInput.fill('edN=7');
    await page.keyboard.press('Enter');
    await page.waitForTimeout(600);
    const edN = (((await (await page.request.get(BASE + '/api/state')).json()).elements) || []).filter((e) => e.label === 'edN')[0] || {};
    check('行内编辑回车提交生效（edN=3 → 7）', Math.abs(Number(edN.val) - 7) < 1e-9, 'val=' + edN.val);
  } else {
    check('行内编辑回车提交生效（edN=3 → 7）', false, '未打开输入框');
  }
  check('就地编辑无新增 JS 错误', JS_ERRORS.length === edErrBefore,
        JS_ERRORS.slice(edErrBefore).join(';').slice(0, 60));

  section('T. 交互控件（按钮/复选框/输入框：渲染 + 点击交互）');
  const wgErrBefore = JS_ERRORS.length;
  await typeCmd('wC=Circle[(0,0),2]');
  await typeCmd('wN=3');
  await typeCmd('wCB=CheckBox["显示圆", wC, (-3,1)]');
  await typeCmd('wBT=Button["建点", "wA=(1,1)", (1,3)]');
  await typeCmd('wIB=InputBox[wN, (2,-2)]');
  await page.waitForTimeout(500);
  const wgRows = await page.$$eval('#objlist .obj', (els) => els.map((e) => e.getAttribute('data-label')));
  check('三个控件进入对象列表', ['wCB', 'wBT', 'wIB'].every((k) => wgRows.indexOf(k) >= 0), String(wgRows.slice(-5)));
  const cvRect = await page.evaluate(() => { const r = document.getElementById('cv').getBoundingClientRect(); return { x: r.x, y: r.y }; });
  const wBox = async (k) => await page.evaluate((kk) => window.__ggbpyDebug.widgetBoxes()[kk] || null, k);
  const stLabels = async () => (await (await page.request.get(BASE + '/api/state')).json()).elements || [];
  const clickWidget = async (k) => {
    const bx = await wBox(k);
    if (!bx) return false;
    await page.mouse.click(cvRect.x + (bx.x0 + bx.x1) / 2, cvRect.y + (bx.y0 + bx.y1) / 2);
    await page.waitForTimeout(500);
    return true;
  };
  const vis0 = (await stLabels()).filter((e) => e.label === 'wC')[0];
  const okCB = await clickWidget('wCB');
  const vis1 = (await stLabels()).filter((e) => e.label === 'wC')[0];
  check('点击复选框切换目标可见性', okCB && vis0 && vis1 && vis1.visible === false,
        'visible ' + (vis0 && vis0.visible) + ' → ' + (vis1 && vis1.visible));
  const hadA = (await stLabels()).some((e) => e.label === 'wA');
  const okBT = await clickWidget('wBT');
  const hasA = (await stLabels()).some((e) => e.label === 'wA');
  check('点击按钮执行脚本（脚本创建的对象出现）', okBT && !hadA && hasA, 'hadA=' + hadA + ' hasA=' + hasA);
  dialogQueue.push('9');
  const okIB = await clickWidget('wIB');
  const nEl = (await stLabels()).filter((e) => e.label === 'wN')[0];
  check('点击输入框修改绑定对象的值', okIB && nEl && Math.abs(Number(nEl.val) - 9) < 1e-9,
        'n=' + (nEl && nEl.val));
  check('控件渲染/交互无新增 JS 错误', JS_ERRORS.length === wgErrBefore,
        JS_ERRORS.slice(wgErrBefore).join(';').slice(0, 60));

  section('X. 视图按钮（顶部放大/缩小/复位，即时生效）');
  const vbErrBefore = JS_ERRORS.length;
  const scaleOf = async () => await page.evaluate(() => {
    const a = window.__ggbpyDebug.toScreen(0, 0), c = window.__ggbpyDebug.toScreen(1, 0);
    return c.x - a.x;
  });
  const centerWorld = async () => await page.evaluate(() => {
    const r = document.getElementById('cv').getBoundingClientRect();
    const a = window.__ggbpyDebug.toScreen(0, 0), b = window.__ggbpyDebug.toScreen(1, 0);
    const sc = b.x - a.x;
    return { wx: (r.width / 2 - a.x) / sc };
  });
  const hasBtns = !!(await page.$('#btn-zoomin')) && !!(await page.$('#btn-zoomout')) && !!(await page.$('#btn-home'));
  check('顶栏存在放大/缩小/复位三个按钮', hasBtns, String(hasBtns));
  const vs0 = await scaleOf();
  await page.click('#btn-zoomin');
  await page.waitForTimeout(220);
  const vs1 = await scaleOf();
  const vc1 = await centerWorld();
  check('放大即时 ×1.3，且以画布中心为锚点（中心世界坐标不动）',
        Math.abs(vs1 / vs0 - 1.3) < 0.02 && Math.abs(vc1.wx) < 0.08,
        'scale ' + vs0.toFixed(2) + '→' + vs1.toFixed(2) + ' wx=' + vc1.wx.toFixed(3));
  await page.click('#btn-zoomout');
  await page.waitForTimeout(220);
  const vs2 = await scaleOf();
  check('缩小即时 ×1/1.3（回到原比例）', Math.abs(vs2 - vs0) < 0.6,
        vs1.toFixed(2) + '→' + vs2.toFixed(2) + '（基准 ' + vs0.toFixed(2) + '）');
  await page.click('#btn-home');
  await page.waitForTimeout(220);
  const vs3 = await scaleOf();
  const vc3 = await centerWorld();
  check('复位即时回到启动视图（比例回基准、原点居中）',
        Math.abs(vs3 - vs0) < 0.6 && Math.abs(vc3.wx) < 0.08,
        'scale=' + vs3.toFixed(2) + '（基准 ' + vs0.toFixed(2) + '）wx=' + vc3.wx.toFixed(3));
  check('视图按钮无新增 JS 错误', JS_ERRORS.length === vbErrBefore,
        JS_ERRORS.slice(vbErrBefore).join(';').slice(0, 60));

  section('AB. 命令帮助显示参数 + 唯一匹配提示 + Tab 补全');
  const abErrBefore = JS_ERRORS.length;
  // datalist 的 label 带完整签名
  const abOpt = await page.evaluate(() => {
    const o = [...document.querySelectorAll('#cmd-list option')];
    const hit = o.filter((x) => String(x.getAttribute('label') || '').indexOf('Slider[最小值') >= 0);
    return { total: o.length, withSig: o.filter((x) => String(x.getAttribute('label') || '').indexOf('[') >= 0).length, hit: hit.length };
  });
  check('命令下拉（datalist）每项都带参数签名', abOpt.total > 100 && abOpt.withSig === abOpt.total && abOpt.hit === 1,
        JSON.stringify(abOpt));
  // 多候选也要有提示（此前只在"前缀唯一"时提示 ✗ → 大多数输入没有反馈）
  await page.fill('#cmd', 'SetSlider');
  await page.waitForTimeout(200);
  const abList = await page.evaluate(() => {
    const h = document.getElementById('cmd-hint');
    const items = h ? [...h.querySelectorAll('.cmd-cand')] : [];
    return { shown: h && h.style.display !== 'none', n: items.length,
             texts: items.map((x) => x.textContent), cur: items.findIndex((x) => x.className.indexOf('cur') >= 0) };
  });
  check('输入 SetSlider → 列出多个候选且每项带完整参数签名',
        abList.shown && abList.n >= 2 && abList.texts.some((x) => x.indexOf('SetSliderLength') === 0)
        && abList.texts.every((x) => x.indexOf('[') > 0),
        JSON.stringify({ n: abList.n, cur: abList.cur, first: abList.texts[0] }));
  // ↑↓ 切换选中
  await page.keyboard.press('ArrowDown');
  await page.waitForTimeout(150);
  const abSel = await page.evaluate(() => {
    const items = [...document.querySelectorAll('#cmd-hint .cmd-cand')];
    return { cur: items.findIndex((x) => x.className.indexOf('cur') >= 0), txt: (items.find((x) => x.className.indexOf('cur') >= 0) || {}).textContent };
  });
  check('按 ↓ 可切换候选选中项', abSel.cur === 1, JSON.stringify(abSel));
  // Tab 补全选中项
  await page.keyboard.press('Tab');
  await page.waitForTimeout(150);
  const abVal = await page.evaluate(() => document.getElementById('cmd').value);
  check('按 Tab 把**选中候选**的完整输入内容填入命令栏',
        abVal === abSel.txt, abVal + ' vs ' + abSel.txt);
  // 前缀更具体 → 候选收敛为一条
  await page.fill('#cmd', 'SetSliderL');
  await page.waitForTimeout(200);
  const abOne = await page.evaluate(() => {
    const items = [...document.querySelectorAll('#cmd-hint .cmd-cand')];
    return { n: items.length, txt: items[0] ? items[0].textContent : '' };
  });
  check('前缀具体到唯一命令 → 候选收敛为一条（含参数）',
        abOne.n === 1 && abOne.txt.indexOf('SetSliderLength') === 0 && abOne.txt.indexOf('像素长度') > 0,
        JSON.stringify(abOne));
  // 帮助弹窗：**只显示命令名**（简洁、一屏放下）+ 悬停 title 显示完整参数 + 可拖拽调整大小/可滚动
  await page.click('#btn-help');
  await page.waitForTimeout(450);
  const hp = await page.evaluate(() => {
    const pop = document.getElementById('help-pop');
    const body = pop.querySelector('.help-body');
    const chips = [...body.querySelectorAll('.hc-cmd')];
    const one = chips.find((c) => c.getAttribute('data-cmd') === 'SetSliderLength');
    return { chips: chips.length, withBracket: chips.filter((c) => c.textContent.indexOf('[') >= 0).length,
             title: one ? one.getAttribute('title') : null, text: one ? one.textContent : null,
             resize: getComputedStyle(pop).resize, fits: !(body.scrollHeight > body.clientHeight) };
  });
  check('帮助弹窗只显示命令名（190 条，一屏放得下）',
        hp.chips === 190 && hp.withBracket === 0 && hp.fits === true,
        JSON.stringify({ chips: hp.chips, withBracket: hp.withBracket, fits: hp.fits }));
  check('悬停 title 给出该命令的完整参数',
        hp.text === 'SetSliderLength' && hp.title === 'SetSliderLength[滑块, 像素长度]',
        JSON.stringify({ text: hp.text, title: hp.title }));
  check('帮助窗口可用鼠标拖拽调整大小（resize: both）', hp.resize === 'both', hp.resize);
  // 默认尺寸下 190 条刚好一屏放下（不溢出 ✓）；窗口缩小或命令增多时依赖 overflow-y:auto 滚动 + PageDown 翻页
  const scCap = await page.evaluate(() => {
    const body = document.querySelector('#help-pop .help-body');
    return { overflowY: getComputedStyle(body).overflowY, flex: getComputedStyle(body).flexGrow };
  });
  check('命令列表容器可滚动（overflow-y:auto，窗口缩小时即可上下移动）',
        scCap.overflowY === 'auto', JSON.stringify(scCap));
  await page.evaluate(() => { const p = document.getElementById('help-pop'); if (p && p.parentNode) p.parentNode.removeChild(p); });
  // 回归：弹窗反复打开不再累积委托监听 → 点一次 CAS 命令只插入一次（曾点一次插两次 ✗）
  await page.click('#btn-help');
  await page.waitForTimeout(300);
  const casChip = await page.$('#help-pop .hc-cas');
  if (casChip) await casChip.click();
  await page.waitForTimeout(350);
  const casVal = await page.evaluate(() => {
    const el = document.querySelector('#cas-panel input, #cas input');
    return el ? el.value : '';
  });
  check('帮助弹窗里的 CAS 命令只插入一次（不重复）',
        (String(casVal).match(/[A-Za-z]+\[\]/g) || []).length === 1, JSON.stringify(casVal));
  // 关闭帮助弹窗（否则它会盖住画布，影响后续滚轮/点击用例）
  await page.evaluate(() => {
    const p = document.getElementById('help-pop');
    if (p) { p.style.display = 'none'; if (p.parentNode) p.parentNode.removeChild(p); }
  });
  await page.waitForTimeout(150);
  // 模板态：**高亮当前参数位 + Tab/Enter 依次跳参**（用户请求 2）
  const abSnap = () => page.evaluate(() => {
    const el = document.getElementById('cmd'), h = document.getElementById('cmd-hint');
    const ps = h ? [...h.querySelectorAll('.cmd-param')] : [];
    return { v: el.value, s: el.selectionStart,
             sel: el.value.slice(el.selectionStart, el.selectionEnd),
             shown: !!h && h.style.display !== 'none', n: ps.length,
             cur: ps.findIndex((x) => x.className.indexOf('cur') >= 0),
             msg: (document.getElementById('msg') || {}).textContent || '' };
  });
  // 备选形式（`Midpoint[点, 点] 或 Midpoint[线段]`）不是可提交文本 → 补全只填首个形式
  await page.fill('#cmd', 'Midpoint');
  await page.waitForTimeout(200);
  await page.keyboard.press('Tab');                       // 候选 → 补全
  await page.waitForTimeout(200);
  let abT = await abSnap();
  check('模板补全只填首个形式（不再带「或」备选）', abT.v === 'Midpoint[点, 点]', abT.v);
  check('补全后自动选中第一个参数 + 提示高亮当前参数',
        abT.sel === '点' && abT.shown && abT.n === 2 && abT.cur === 0,
        JSON.stringify({ sel: abT.sel, shown: abT.shown, n: abT.n, cur: abT.cur }));
  await page.keyboard.press('Tab');
  await page.waitForTimeout(150);
  abT = await abSnap();
  check('Tab 跳到第 2 个参数（高亮跟随）', abT.sel === '点' && abT.s === 12 && abT.cur === 1,
        JSON.stringify({ sel: abT.sel, s: abT.s, cur: abT.cur }));
  await page.keyboard.press('Tab');
  await page.waitForTimeout(150);
  abT = await abSnap();
  check('末参再 Tab 循环回第 1 个参数', abT.s === 9 && abT.cur === 0, JSON.stringify({ s: abT.s, cur: abT.cur }));
  // Shift+Tab 反向跳参（循环）
  await page.keyboard.down('Shift');
  await page.keyboard.press('Tab');
  await page.keyboard.up('Shift');
  await page.waitForTimeout(150);
  abT = await abSnap();
  check('Shift+Tab 从第 1 个参数反向跳到最后一个（循环）', abT.s === 12 && abT.cur === 1,
        JSON.stringify({ s: abT.s, cur: abT.cur }));
  await page.keyboard.down('Shift');
  await page.keyboard.press('Tab');
  await page.keyboard.up('Shift');
  await page.waitForTimeout(150);
  abT = await abSnap();
  check('Shift+Tab 再按 → 回到上一个参数', abT.s === 9 && abT.cur === 0, JSON.stringify({ s: abT.s, cur: abT.cur }));
  // Enter 在中间参数上跳参（不提交）
  await page.fill('#cmd', 'Angle');
  await page.waitForTimeout(200);
  await page.keyboard.press('Tab');
  await page.waitForTimeout(200);
  abT = await abSnap();
  const abMsg0 = abT.msg;
  check('Angle 模板切出 3 个参数且选中第 1 个', abT.n === 3 && abT.sel === '点A' && abT.cur === 0,
        JSON.stringify({ n: abT.n, sel: abT.sel, cur: abT.cur }));
  await page.keyboard.press('Enter');
  await page.waitForTimeout(200);
  abT = await abSnap();
  check('Enter 在中间参数上跳参（不提交：值/消息不变）',
        abT.sel === '顶点B' && abT.v === 'Angle[点A, 顶点B, 点C]（有向 0..360°）' && abT.msg === abMsg0,
        JSON.stringify({ sel: abT.sel, v: abT.v }));
  // 点提示里的参数可直接选中
  const abP1 = await page.evaluate(() => {
    const p = document.querySelectorAll('#cmd-hint .cmd-param')[1];
    const r = p.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  });
  await page.mouse.click(abP1.x, abP1.y);
  await page.waitForTimeout(150);
  abT = await abSnap();
  check('点提示里的参数 → 输入框选中它', abT.sel === '顶点B' && abT.cur === 1,
        JSON.stringify({ sel: abT.sel, cur: abT.cur }));
  // 参数按顶层逗号切分：`(x,y)` 里的逗号不算
  await page.fill('#cmd', 'Slider[0,10,1,(-2,2)]');
  await page.waitForTimeout(200);
  abT = await abSnap();
  check('参数按顶层逗号切分（(x,y) 内逗号不切）', abT.n === 4, JSON.stringify({ n: abT.n }));
  // 本轮补登记的签名可用：候选带参数、补全只填首个形式（备选形式不整串塞入）
  await page.fill('#cmd', 'PerpendicularBisector');
  await page.waitForTimeout(200);
  await page.keyboard.press('Tab');
  await page.waitForTimeout(200);
  abT = await abSnap();
  check('补登记的签名可用（PerpendicularBisector 补全只填首个形式、并选中首参）',
        abT.v === 'PerpendicularBisector[线段]' && abT.sel === '线段' && abT.cur === 0,
        JSON.stringify({ v: abT.v, sel: abT.sel, cur: abT.cur }));
  await page.fill('#cmd', 'MacroList');
  await page.waitForTimeout(200);
  await page.keyboard.press('Tab');
  await page.waitForTimeout(200);
  abT = await abSnap();
  check('无参数命令（MacroList[]）不进模板态：只填名字、不显示参数位提示',
        abT.v === 'MacroList[]' && abT.shown === false && abT.n === 0,
        JSON.stringify({ v: abT.v, shown: abT.shown, n: abT.n }));
  // 可选参数（签名里带 ?）淡显 + 位序提示（数字，语言无关）
  await page.fill('#cmd', 'Slider');
  await page.waitForTimeout(200);
  await page.keyboard.press('Tab');                 // 候选 → 补全（6 个参数，其中 4 个可选）
  await page.waitForTimeout(200);
  const abTpl = await page.evaluate(() => {
    const h = document.getElementById('cmd-hint');
    const ps = [...h.querySelectorAll('.cmd-param')];
    return { n: ps.length, opt: ps.filter((x) => x.className.indexOf('cmd-opt') >= 0).length,
             cur: ps.findIndex((x) => x.className.indexOf('cur') >= 0),
             pos: (h.querySelector('.cmd-pos') || {}).textContent || '' };
  });
  check('模板提示标出可选参数（`步长?/(x,y)?/vertical?/px?` 共 4 个）并给出位序 1/6',
        abTpl.n === 6 && abTpl.opt === 4 && abTpl.cur === 0 && abTpl.pos === '1/6',
        JSON.stringify(abTpl));
  await page.keyboard.press('Tab');
  await page.waitForTimeout(150);
  const abPos2 = await page.evaluate(() => (document.querySelector('#cmd-hint .cmd-pos') || {}).textContent || '');
  check('跳参后位序跟随（2/6）', abPos2 === '2/6', abPos2);
  await page.fill('#cmd', '');
  await page.waitForTimeout(150);
  abT = await abSnap();
  check('清空输入 → 参数提示收起', abT.shown === false, JSON.stringify({ shown: abT.shown }));
  check('命令帮助/补全无新增 JS 错误', JS_ERRORS.length === abErrBefore,
        JS_ERRORS.slice(abErrBefore).join(';').slice(0, 60));

  section('Z. 动画：速度/方向/往返 + 播放中拖动');
  const anErrBefore = JS_ERRORS.length;
  const anVal = async (l) => Number(((((await (await page.request.get(BASE + '/api/state')).json()).elements) || []).filter((e) => e.label === l)[0] || {}).val);
  const anSet = async (t) => { await typeCmd(t); };   // 必须走命令栏：纯 HTTP 不会刷新 SPA 的 elements
  const anCfg = async () => await page.evaluate(() => window.__ggbpyDebug.animState());

  // ① 设置生效（步间隔 + 方向 + 每滑块方向）
  dialogQueue.push('40,down');
  await page.click('#btn-anim-set');
  await page.waitForTimeout(250);
  const cfg1 = await anCfg();
  check('动画设置生效（步间隔/方向/每滑块方向）',
        cfg1.ms === 40 && cfg1.dir === 'down', JSON.stringify({ ms: cfg1.ms, dir: cfg1.dir }));

  // ② down 方向：用**大范围**滑块（区间 0..10000，短窗口内不可能回绕）→ 必须下降
  await anSet('anC=Slider[0,10000,1,(-6,4)]');
  await anSet('SetValue[anC,5000]');
  await page.waitForTimeout(300);
  const c0 = await anVal('anC');
  await page.click('#btn-anim-play');
  await page.waitForTimeout(150);
  const cfg2 = await anCfg();
  const c1 = await anVal('anC');
  check('方向 down：大范围滑块确定性下降（无回绕干扰）',
        cfg2.dirs && cfg2.dirs.anC === 'down' && c1 < c0, 'anC ' + c0 + '→' + c1 + ' dir=' + (cfg2.dirs || {}).anC);
  await page.click('#btn-anim-stop');
  await page.waitForTimeout(200);

  // ③ bounce 往返：窄范围 0..4，值 3 → 触顶后必须转为下降（采样中既有升也有降）
  dialogQueue.push('25,bounce');
  await page.click('#btn-anim-set');
  await page.waitForTimeout(200);
  await anSet('anD=Slider[0,4,1,(-6,3)]');
  await anSet('SetValue[anD,3]');
  await page.waitForTimeout(250);
  await page.click('#btn-anim-play');
  const samples = [];
  for (let k = 0; k < 10; k++) { await page.waitForTimeout(70); samples.push(await anVal('anD')); }
  let sawUp = false, sawDown = false;
  for (let k = 1; k < samples.length; k++) {
    if (samples[k] > samples[k - 1]) sawUp = true;
    if (samples[k] < samples[k - 1]) sawDown = true;
  }
  check('方向 bounce：到达边界后往返（采样中既有上升也有下降）',
        sawUp && sawDown, JSON.stringify(samples));

  // ④ 播放中拖动不打断播放，且值仍在区间内
  await anSet('anE=Slider[0,10,1,(-6,1)]');
  await page.waitForTimeout(250);
  await page.evaluate(() => {
    const b = window.__ggbpyDebug.widgetBoxes()['anE'];
    const cv = document.getElementById('cv'), r = cv.getBoundingClientRect();
    const fire = (t, x) => cv.dispatchEvent(new PointerEvent(t, { bubbles: true, cancelable: true, pointerId: 1,
      clientX: r.x + x, clientY: r.y + (b.y0 + b.y1) / 2, offsetX: x, offsetY: (b.y0 + b.y1) / 2 }));
    fire('pointerdown', b.x0 + 4); fire('pointerup', b.x0 + 4);
  });
  await page.waitForTimeout(300);
  const playingAfter = await page.evaluate(() => window.__ggbpyDebug.playingLabels());
  const e1 = await anVal('anE');
  // 设计如此：任何画布交互都会停止动画（避免与手动操作打架），拖动滑钮亦然
  check('播放中拖动滑钮 → 动画停止（刻意设计）且值仍在区间内',
        playingAfter.indexOf('anE') < 0 && e1 >= 0 && e1 <= 10,
        'labels=' + JSON.stringify(playingAfter) + ' anE=' + e1);
  await page.click('#btn-anim-stop');
  await page.waitForTimeout(200);
  const anStop = await page.evaluate(() => window.__ggbpyDebug.playingLabels());
  check('全部暂停：集合清空', anStop.length === 0, JSON.stringify(anStop));
  check('动画无新增 JS 错误', JS_ERRORS.length === anErrBefore,
        JS_ERRORS.slice(anErrBefore).join(';').slice(0, 60));

  section('AA. 竖直滑块：轨道沿 y、播放按钮在底部、功能不变');
  const vtErrBefore = JS_ERRORS.length;
  await typeCmd('vtS=Slider[0,10,1,(-2,2),vertical]');
  await page.waitForTimeout(500);
  const vtBox = await page.evaluate(() => window.__ggbpyDebug.widgetBoxes()['vtS'] || null);
  check('竖直滑块命中框：axis=y、轨道沿 y、播放按钮在轨道底部之下',
        !!vtBox && vtBox.axis === 'y' && vtBox.vert === true
        && Math.abs((vtBox.wy1 - vtBox.wy0) - 3) < 1e-6 && vtBox.playY0 > vtBox.y1,
        JSON.stringify({ axis: vtBox && vtBox.axis, playY0: vtBox && vtBox.playY0, y1: vtBox && vtBox.y1 }));
  // 值拖动：**本轮已定位并覆盖** —— 老问题真因不是合成指针，而是**命中框重叠取第一个**：
  //   AA 的 vtS 与 U 段的 uS 同在 (-2,2)：横滑块的矩形罩住竖滑块的滑钮 → sliderAt 返回 uS
  //   → 按下的其实是 uS → 拖竖滑块"没反应"（值恒 5）。已改为按「到各自轨道的垂距」取最近者。
  //   独立页面可复现（devtools/probe_widget_overlap.js）：修复前 drag label=uS，修复后=竖滑块。
  // 这里用**自建的一对同锚点横/竖滑块**做回归（不依赖 U 段的残留状态）。
  await typeCmd('ovH=Slider[0,10,1,(5,3)]');
  await typeCmd('ovV=Slider[0,10,1,(5,3),vertical]');
  await page.waitForTimeout(500);
  const ovPair = await page.evaluate(() => {
    const w = window.__ggbpyDebug.widgetBoxes();
    const u = w['ovH'], v = w['ovV'];
    return {
      u: u && { axis: u.axis, x0: u.x0, x1: u.x1, y0: u.y0, y1: u.y1, knobX: u.knobX },
      v: v && { axis: v.axis, x0: v.x0, x1: v.x1, y0: v.y0, y1: v.y1, knobX: v.knobX, knobY: v.knobY },
      hitVknob: v ? window.__ggbpyDebug.sliderAt(v.knobX, v.knobY) : null,
      hitHknob: u ? window.__ggbpyDebug.sliderAt(u.knobX, (u.y0 + u.y1) / 2) : null
    };
  });
  check('同锚点横/竖滑块：竖滑块的滑钮命中**竖滑块**（修复前返回横滑块 ✗）',
        ovPair.hitVknob === 'ovV' && !!ovPair.v && !!ovPair.u
        && ovPair.v.knobX >= ovPair.u.x0 && ovPair.v.knobX <= ovPair.u.x1
        && ovPair.v.knobY >= ovPair.u.y0 && ovPair.v.knobY <= ovPair.u.y1,   // 该点确实落在横滑块矩形内
        JSON.stringify({ hit: ovPair.hitVknob, hitH: ovPair.hitHknob }));
  {
    const r = await page.evaluate(() => { const q = document.getElementById('cv').getBoundingClientRect(); return { left: q.left, top: q.top }; });
    const before = await state();
    const vt0 = (before.filter((e) => e.label === 'ovV')[0] || {}).value;
    const ht0 = (before.filter((e) => e.label === 'ovH')[0] || {}).value;
    await page.mouse.move(r.left + ovPair.v.knobX, r.top + ovPair.v.knobY);
    await page.mouse.down();
    await page.waitForTimeout(80);
    const dDown = await page.evaluate(() => window.__ggbpyDebug.dragState());
    await page.mouse.move(r.left + ovPair.v.knobX, r.top + ovPair.v.y0 + 4, { steps: 6 });   // 拖到轨道顶部 = max
    await page.mouse.up();
    await page.waitForTimeout(450);
    const after = await state();
    const vt1 = (after.filter((e) => e.label === 'ovV')[0] || {}).value;
    const ht1 = (after.filter((e) => e.label === 'ovH')[0] || {}).value;
    check('拖竖滑块的滑钮 → 抓到的是竖滑块', dDown && dDown.label === 'ovV' && dDown.slider === true,
          JSON.stringify(dDown));
    check('拖竖滑块滑钮到顶部 → 竖滑块值变到最大（10），横滑块不受影响',
          /10/.test(String(vt1)) && ht1 === ht0 && vt1 !== vt0,
          JSON.stringify({ vt: vt0 + '→' + vt1, ht: ht0 + '→' + ht1 }));
    // 同源的「整体移动」：抓轨道（非滑钮）拖动 → 锚点移动，且 vertical 标志保留
    const vBox = await page.evaluate(() => window.__ggbpyDebug.widgetBoxes()['ovV']);
    const midY = (vBox.y0 + vBox.y1) / 2;
    check('抓竖直滑块轨道（非滑钮）命中仍是竖滑块',
          (await page.evaluate(([x, y]) => window.__ggbpyDebug.sliderAt(x, y), [vBox.x0 + (vBox.x1 - vBox.x0) / 2, midY])) === 'ovV');
    await page.mouse.move(r.left + vBox.x0 + (vBox.x1 - vBox.x0) / 2, r.top + midY);
    await page.mouse.down();
    await page.waitForTimeout(80);
    const dPos = await page.evaluate(() => window.__ggbpyDebug.dragState());
    await page.mouse.move(r.left + vBox.x0 + (vBox.x1 - vBox.x0) / 2 + 40, r.top + midY, { steps: 5 });
    await page.mouse.up();
    await page.waitForTimeout(450);
    const movedEl = (await state()).filter((e) => e.label === 'ovV')[0] || {};
    const anchorX = (String(movedEl.defn).match(/\(([-0-9.]+),/) || [])[1];
    check('拖轨道 → 滑块整体移动（锚点变、defn 仍带 vertical）',
          /vertical/.test(String(movedEl.defn)) && anchorX !== undefined && Math.abs(Number(anchorX) - 5) > 0.3,
          JSON.stringify({ defn: movedEl.defn, anchorX: anchorX, drag: dPos }));
  }
  await typeCmd('SetValue[vtS,5]');
  await page.waitForTimeout(300);
  const vtBox2 = await page.evaluate(() => window.__ggbpyDebug.widgetBoxes()['vtS'] || null);
  check('竖直滑块滑钮纵向位置与值一致（值 5/区间 0..10 → 纵向居中）',
        !!vtBox2 && typeof vtBox2.knobY === 'number'
        && Math.abs(vtBox2.knobY - (vtBox2.y0 + vtBox2.y1) / 2) < 5,
        JSON.stringify(vtBox2 && { knobY: vtBox2.knobY, mid: (vtBox2.y0 + vtBox2.y1) / 2 }));
  // 轨道长度按 px（屏幕长度恒定）：默认 140，SetSliderLength 后随之变化
  const pxTrack0 = await page.evaluate(() => {
    const b = window.__ggbpyDebug.widgetBoxes()['vtS']; return b ? Math.round(Math.abs(b.s1 - b.s0)) : -1;
  });
  await typeCmd('SetSliderLength[vtS, 260]');
  await page.waitForTimeout(350);
  const pxTrack1 = await page.evaluate(() => {
    const b = window.__ggbpyDebug.widgetBoxes()['vtS']; return b ? Math.round(Math.abs(b.s1 - b.s0)) : -1;
  });
  check('轨道长度按 px（默认 140 → SetSliderLength 260 后 260，竖直同样生效）',
        pxTrack0 === 140 && pxTrack1 === 260, 'px ' + pxTrack0 + '→' + pxTrack1);
  check('竖直滑块无新增 JS 错误', JS_ERRORS.length === vtErrBefore,
        JS_ERRORS.slice(vtErrBefore).join(';').slice(0, 60));

  section('Y. 滑块范围/步长：列表行 ⚙ 按钮就地编辑');
  const seErrBefore = JS_ERRORS.length;
  await typeCmd('seS=Slider[0,10,1,(-2,-5)]');   // 与 U 段的 uS 错开位置，避免命中框重叠
  await page.waitForTimeout(450);
  // 真实点击对象列表滑块行的 ⚙（不冲突入口：滑块的画布双击会被「改值拖动」抢占）
  dialogQueue.push('-5,5,0.5');
  await page.click('#objlist .obj[data-label="seS"] button.sb');
  await page.waitForTimeout(600);
  const seEl = (((await (await page.request.get(BASE + '/api/state')).json()).elements) || []).filter((e) => e.label === 'seS')[0] || {};
  check('点 ⚙ 改范围/步长生效（min/max/step 与 defn 同步）',
        Number(seEl.min) === -5 && Number(seEl.max) === 5 && Math.abs(Number(seEl.step) - 0.5) < 1e-9
        && String(seEl.defn).indexOf('Slider[-5,5,0.5,') >= 0,
        JSON.stringify({ min: seEl.min, max: seEl.max, step: seEl.step, defn: seEl.defn }));
  const seBox2 = await page.evaluate(() => window.__ggbpyDebug.widgetBoxes()['seS'] || null);
  check('改范围后滑块仍渲染在画布上（命中框仍在）',
        !!seBox2 && seBox2.kind === 'slider' && Math.abs(seBox2.wx1 - seBox2.wx0 - 3) < 1e-6,
        JSON.stringify(seBox2));
  // 滑块右侧 ▶/⏸ 播放切换（与对象列表 ▶ 同一实现 sliderPlay）
  const seBox3 = await page.evaluate(() => window.__ggbpyDebug.widgetBoxes()['seS'] || null);
  const seRect2 = await page.evaluate(() => { const r = document.getElementById('cv').getBoundingClientRect(); return { x: r.x, y: r.y }; });
  // 段首清理：若前面的用例留下了播放中的滑块，先点它的播放框停掉（playState 是全局单例）
  const sePrev = await page.evaluate(() => window.__ggbpyDebug.playLabel());
  if (sePrev) {
    await page.evaluate((lb) => {
      const b = window.__ggbpyDebug.widgetBoxes()[lb];
      if (!b) return;
      const cv = document.getElementById('cv');
      const r = cv.getBoundingClientRect();
      const x = b.playX0 + 12, y = b.playY0 + 12;
      cv.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, pointerId: 1,
        clientX: r.x + x, clientY: r.y + y, offsetX: x, offsetY: y }));
    }, sePrev);
    await page.waitForTimeout(250);
  }
  check('滑块右侧有播放按钮，且命中判定正确（初始 ▶，未播放）',
        typeof seBox3.playX0 === 'number' && seBox3.playing === false
        && (await page.evaluate(([x, y]) => window.__ggbpyDebug.playAt(x, y), [seBox3.playX0 + 12, seBox3.playY0 + 12])) === 'seS',
        JSON.stringify({ playing: seBox3.playing, playX0: seBox3.playX0 }));
  // 用合成 pointerdown 直接打在画布的播放框上：全量矩阵里对象列表面板可能覆盖该位置，
  // 真实鼠标点击会落到列表行（实测踩到：启动了另一个滑块的播放）
  const seFire = async () => await page.evaluate(([x, y]) => {
    const cv = document.getElementById('cv');
    const r = cv.getBoundingClientRect();
    cv.dispatchEvent(new PointerEvent('pointerdown', {
      bubbles: true, cancelable: true, pointerId: 1,
      clientX: r.x + x, clientY: r.y + y, offsetX: x, offsetY: y
    }));
  }, [seBox3.playX0 + 12, seBox3.playY0 + 12]);
  await seFire();
  await page.waitForTimeout(400);
  const seP1 = await page.evaluate(() => window.__ggbpyDebug.playLabel());
  const seB1 = await page.evaluate(() => window.__ggbpyDebug.widgetBoxes()['seS'].playing);
  check('点 ▶ 开始播放（图标切为 ⏸）', seP1 === 'seS' && seB1 === true,
        'playLabel=' + seP1 + ' playing=' + seB1);
  await seFire();
  await page.waitForTimeout(400);
  const seP2 = await page.evaluate(() => window.__ggbpyDebug.playLabel());
  const seB2 = await page.evaluate(() => window.__ggbpyDebug.widgetBoxes()['seS'].playing);
  check('再点 → 暂停（图标切回 ▶）', seP2 === null && seB2 === false,
        'playLabel=' + seP2 + ' playing=' + seB2);
  check('滑块范围编辑无新增 JS 错误', JS_ERRORS.length === seErrBefore,
        JS_ERRORS.slice(seErrBefore).join(';').slice(0, 60));

  section('S. 角度有向 0..360°：优角绘制到反射扇区');
  const angErrBefore = JS_ERRORS.length;
  await typeCmd('XAx=(2,0)');
  await typeCmd('XBx=(1,0)');
  await typeCmd('XCx=(0,-1)');            // 逆时针从 BA 到 BC = 225°（优角）
  await typeCmd('XG=Angle[XAx,XBx,XCx]');
  await page.waitForTimeout(400);
  const xg = await byLabel('XG');
  check('优角数值为 225°（不再折成 135°）', !!xg && Math.abs(Number(xg.deg) - 225) < 1e-6, xg && String(xg.deg));
  const angPix = await page.evaluate(({ el, dpr }) => {
    const cv = document.getElementById('cv');
    const g = cv.getContext('2d');
    const S = window.__ggbpyDebug.toScreen(el.cx, el.cy);
    const rad = el.rad;
    let inSpan = 0, outSpan = 0, reflex = 0;
    const R = Math.min(130, Math.max(50, Math.round(Math.abs(el.arc_r * S.scale * 2))));
    for (let dx = -R; dx <= R; dx++) {
      for (let dy = -R; dy <= R; dy++) {
        const x = Math.round(S.x + dx), y = Math.round(S.y + dy);
        if (x < 0 || y < 0) continue;
        const d = g.getImageData(x * dpr, y * dpr, 1, 1).data;
        if (!(d[3] > 200 && d[2] > 150 && d[0] > 60 && d[0] < 220 && d[1] < 170)) continue;
        let rel = Math.atan2(-dy, dx) - el.ang1;
        while (rel < 0) rel += 2 * Math.PI;
        while (rel >= 2 * Math.PI) rel -= 2 * Math.PI;
        const inArc = rel <= rad + 0.15;
        if (inArc) {
          inSpan++;
          if (rel > Math.PI * 0.9 && rel < rad - 0.1) reflex++;   // 反射部分（>162° 且未到端点）
        } else {
          outSpan++;
        }
      }
    }
    return { inSpan: inSpan, outSpan: outSpan, reflex: reflex, rad: rad * 180 / Math.PI, R: R };
  }, { el: xg, dpr: await page.evaluate(() => window.devicePixelRatio || 1) });
  check('弧线+标注像素落在有向扇区 [0, rad]（数量足够）', angPix.inSpan >= 60, JSON.stringify(angPix));
  check('优角弧线覆盖反射扇区（>180° 部分有像素；旧实现止于 135°）', angPix.reflex >= 5, JSON.stringify(angPix));
  check('角度渲染无新增 JS 错误', JS_ERRORS.length === angErrBefore,
        JS_ERRORS.slice(angErrBefore).join(';').slice(0, 60));

  section('R. 剖分面积标注 + 内联列表动态链（memo 修复）');
  const tessErr2 = JS_ERRORS.length;
  await typeCmd('ZAx=(0,0)');
  await typeCmd('ZBx=(4,0)');
  await typeCmd('ZCx=(4,4)');
  await typeCmd('ZDx=(0,4)');
  await typeCmd('ZV=Voronoi[{ZAx,ZBx,ZCx,ZDx}]');
  await page.waitForTimeout(400);
  const zv1 = await byLabel('ZV');
  check('内联点标签列表 Voronoi 经 HTTP 返回 areas/centroids',
        !!zv1 && (zv1.areas || []).length === 4 && (zv1.centroids || []).length === 4,
        JSON.stringify(zv1 && { a: (zv1.areas || []).length, c: (zv1.centroids || []).length }));
  check('摘要 value 含数量与总面积', !!zv1 && /4 个多边形/.test(zv1.value) && /总面积/.test(zv1.value),
        zv1 && zv1.value);
  const zvAreas1 = (zv1 && zv1.areas ? zv1.areas.map((v) => Number(v).toFixed(3)) : []).join(',');
  await typeCmd('SetCoords[ZAx,-3,-3]');
  await page.waitForTimeout(450);
  const zv2 = await byLabel('ZV');
  const zvAreas2 = (zv2 && zv2.areas ? zv2.areas.map((v) => Number(v).toFixed(3)) : []).join(',');
  check('移动点后面积随内联列表刷新（memo 修复链路）', zvAreas1 !== zvAreas2 && zvAreas2 !== '',
        zvAreas1 + ' → ' + zvAreas2);
  check('面积标注渲染无新增 JS 错误', JS_ERRORS.length === tessErr2,
        JS_ERRORS.slice(tessErr2).join(';').slice(0, 60));

  section('Q. 点标签列表 {A,B}（解析层新能力）');
  const plErrBefore = JS_ERRORS.length;
  await typeCmd('PAx=(1,1)');
  await typeCmd('PBx=(4,1)');
  await typeCmd('LPT={PAx,PBx}');
  await page.waitForTimeout(350);
  const plRows = await page.$$eval('#objlist .obj', (els) => els.map((e) => e.getAttribute('data-label')));
  check('点标签列表进入对象列表', plRows.indexOf('LPT') >= 0, String(plRows.slice(-3)));
  const plState = await byLabel('LPT');
  check('点标签列表序列化为 point 列表（两条坐标）',
        !!plState && plState.itemkind === 'point' && (plState.items || []).length === 2,
        JSON.stringify(plState && { k: plState.itemkind, n: (plState.items || []).length }));
  check('点标签列表渲染无新增 JS 错误', JS_ERRORS.length === plErrBefore,
        JS_ERRORS.slice(plErrBefore).join(';').slice(0, 60));

  section('P. 茎叶图（新图表：渲染 + 可拖动命中框）');
  const stemErrBefore = JS_ERRORS.length;
  await typeCmd('ZS=StemPlot[{12,15,23,11,31,45,45}]');
  await page.waitForTimeout(400);
  const stemRows = await page.$$eval('#objlist .obj', (els) => els.map((e) => e.getAttribute('data-label')));
  check('StemPlot 结果进入对象列表', stemRows.indexOf('ZS') >= 0, String(stemRows.slice(-3)));
  const stemBox = await page.evaluate(() => window.__ggbpyDebug.chartBox('ZS'));
  check('茎叶图登记可拖动命中框（宽度/高度合理）',
        !!stemBox && (stemBox.x1 - stemBox.x0) > 40 && (stemBox.y1 - stemBox.y0) > 20,
        JSON.stringify(stemBox));
  check('茎叶图渲染无新增 JS 错误', JS_ERRORS.length === stemErrBefore,
        JS_ERRORS.slice(stemErrBefore).join(';').slice(0, 60));

  section('O. 统计图缩放策略统一（柱高/饼半径随缩放变化）');
  const csErrBefore = JS_ERRORS.length;
  await typeCmd('ZB1=BarChart[{3,1,4,1,5,9,2,6}]');
  await typeCmd('ZP1=PieChart[{3,5,2}]');
  await page.waitForTimeout(500);
  const boxBefore = await page.evaluate(() => ({
    scale: window.__ggbpyDebug.toScreen(1, 0).scale,
    bar: window.__ggbpyDebug.chartBox('ZB1'),
    pie: window.__ggbpyDebug.chartBox('ZP1'),
  }));
  await page.mouse.move(600, 450);
  await page.mouse.wheel(0, -300);              // 滚轮放大
  await page.waitForTimeout(600);               // 等 180ms 延迟重载完成
  const boxAfter = await page.evaluate(() => ({
    scale: window.__ggbpyDebug.toScreen(1, 0).scale,
    bar: window.__ggbpyDebug.chartBox('ZB1'),
    pie: window.__ggbpyDebug.chartBox('ZP1'),
  }));
  const boxW = (b) => (b ? b.x1 - b.x0 : 0);
  const boxH = (b) => (b ? b.y1 - b.y0 : 0);
  check('滚轮确实放大（scale 增大）', boxAfter.scale > boxBefore.scale * 1.05,
        boxBefore.scale + ' → ' + boxAfter.scale);
  check('柱状图高度随缩放变化（世界坐标策略）',
        !!boxBefore.bar && !!boxAfter.bar && boxH(boxAfter.bar) > boxH(boxBefore.bar) * 1.05,
        boxH(boxBefore.bar).toFixed(1) + ' → ' + boxH(boxAfter.bar).toFixed(1));
  check('饼图直径随缩放变化（世界坐标策略）',
        !!boxBefore.pie && !!boxAfter.pie && boxW(boxAfter.pie) > boxW(boxBefore.pie) * 1.05,
        boxW(boxBefore.pie).toFixed(1) + ' → ' + boxW(boxAfter.pie).toFixed(1));
  check('缩放统计图无新增 JS 错误', JS_ERRORS.length === csErrBefore,
        JS_ERRORS.slice(csErrBefore).join(';').slice(0, 60));

  section('N. 二维剖分渲染（Delaunay / Voronoi 多边形列表）');
  const tessErrBefore = JS_ERRORS.length;
  await typeCmd('Pts={(0,0),(4,0),(4,4),(0,4),(2,2)}');
  await typeCmd('Del=Delaunay[Pts]');
  await typeCmd('Vor=Voronoi[Pts]');
  await page.waitForTimeout(400);
  const tessRows = await page.$$eval('#objlist .obj', (els) => els.map((e) => e.getAttribute('data-label')));
  check('Delaunay 结果进入对象列表', tessRows.indexOf('Del') >= 0, String(tessRows.slice(-4)));
  check('Voronoi 结果进入对象列表', tessRows.indexOf('Vor') >= 0, String(tessRows.slice(-4)));
  check('绘制多边形列表无新增 JS 错误', JS_ERRORS.length === tessErrBefore,
        JS_ERRORS.slice(tessErrBefore).join(';').slice(0, 60));

  // -------------------------------------------------------------------------
  section('AC. 格点吸附（默认关 / 开启吸附到格点 / 吸附后复用已有点 / Shift 临时吸附）');
  const acErrBefore = JS_ERRORS.length;
  const acSnap = () => page.evaluate(() => window.__ggbpyDebug.snapState());
  const acStep = await page.evaluate(() => window.__ggbpyDebug.gridStep());
  const acGrid = (v) => Math.abs(v / acStep - Math.round(v / acStep)) < 1e-6;
  const acPts = async () => (await state()).filter((e) => e.kind === 'point');
  const acToolPoint = async () => {
    // 工具按钮是「选中再点取消」→ 必须先看状态，否则会把工具点没 ✗
    const t = await page.evaluate(() => window.__ggbpyDebug.toolState());
    if (t.activeTool !== 'point') { await page.click('#cat-tools .tool-btn[data-tool="point"]'); await page.waitForTimeout(200); }
  };
  const acClickWorld = async (wx, wy, shift) => {
    const s = await page.evaluate(([x, y]) => window.__ggbpyDebug.toScreen(x, y), [wx, wy]);
    const r = await page.evaluate(() => { const q = document.getElementById('cv').getBoundingClientRect(); return { left: q.left, top: q.top }; });
    if (shift) await page.keyboard.down('Shift');
    await page.mouse.click(r.left + s.x, r.top + s.y);
    await page.waitForTimeout(450);
    if (shift) await page.keyboard.up('Shift');
  };
  // 复位必须走**页面自己的清空按钮**：HTTP /api/clear 不通知前端 → 页面本地仍有旧对象，
  // 点击会被 hitAnyPoint/widgetHit 截走，表现为「点了没反应」（曾据此误判吸附坏了 ✗）
  await clickBtn('btn-clear');
  await page.waitForTimeout(450);
  check('吸附默认关闭（按钮无 active）',
        (await acSnap()).on === false && !(await page.evaluate(() => document.getElementById('btn-snap').classList.contains('active'))),
        JSON.stringify(await acSnap()));
  await acToolPoint();
  await acClickWorld(-5.37, -3.63);                       // 明显不在格点上
  let acList = await acPts();
  check('未开吸附 → 落点保留原始坐标（不吸附）',
        acList.length === 1 && Math.abs(acList[0].x + 5.37) < 0.01 && Math.abs(acList[0].y + 3.63) < 0.01,
        JSON.stringify(acList.map((e) => [e.label, e.x, e.y])));
  // 开启吸附
  await page.evaluate(() => { const h = document.querySelector('#m-view .menu-btn'); if (h) h.click(); });
  await page.waitForTimeout(120);
  await page.click('#btn-snap');
  await page.waitForTimeout(250);
  check('点「吸附」→ 开启 + 按钮 active + 明确提示',
        (await acSnap()).on === true
        && (await page.evaluate(() => document.getElementById('btn-snap').classList.contains('active')))
        && /吸附/.test(await page.textContent('#msg')),
        (await page.textContent('#msg')).slice(0, 24));
  await clickBtn('btn-clear');
  await page.waitForTimeout(450);
  await acToolPoint();
  await acClickWorld(-5.37, -3.63);
  acList = await acPts();
  check('开吸附 → 落点吸附到格点（坐标是步长整数倍）',
        acList.length === 1 && acGrid(acList[0].x) && acGrid(acList[0].y),
        JSON.stringify({ step: acStep, got: acList.map((e) => [e.x, e.y]) }));
  check('吸附确实改变了落点（≠ 原始 -5.37/-3.63）',
        acList.length === 1 && (Math.abs(acList[0].x + 5.37) > 1e-9 || Math.abs(acList[0].y + 3.63) > 1e-9),
        JSON.stringify(acList.map((e) => [e.x, e.y])));
  const acLabel = acList.length ? acList[0].label : null;
  await acToolPoint();
  await acClickWorld(-5.37, -3.63);                       // 同一落点 → 吸附到同一格点
  acList = await acPts();
  check('吸附后同一落点再点 → 复用已有点（格点处不新建重叠点）',
        acList.length === 1 && acLabel !== null && acList[0].label === acLabel,
        JSON.stringify(acList.map((e) => e.label)));
  // 原点不再画标记后，用户仍可用**吸附**取到 (0,0)：点靠近原点处 → 落点恰为 (0,0)
  await clickBtn('btn-clear');
  await page.waitForTimeout(450);
  await acToolPoint();
  await acClickWorld(0.2, -0.2);
  acList = await acPts();
  check('原点无标记后仍可吸附取到 (0,0)',
        acList.length === 1 && Math.abs(acList[0].x) < 1e-9 && Math.abs(acList[0].y) < 1e-9,
        JSON.stringify(acList.map((e) => [e.x, e.y])));
  // Shift 临时吸附
  await page.evaluate(() => { const h = document.querySelector('#m-view .menu-btn'); if (h) h.click(); });
  await page.waitForTimeout(120);
  await page.click('#btn-snap');
  await page.waitForTimeout(250);
  await clickBtn('btn-clear');
  await page.waitForTimeout(450);
  await acToolPoint();
  await acClickWorld(-5.37, -3.63, true);
  acList = await acPts();
  check('未开吸附 + 按住 Shift → 临时吸附到格点',
        (await acSnap()).on === false && acList.length === 1 && acGrid(acList[0].x) && acGrid(acList[0].y),
        JSON.stringify(acList.map((e) => [e.x, e.y])));
  // 指针捕获：曾误写成自递归 capturePointer(ev) → 栈溢出被吞 → 捕获**静默失效** ✗（已修）
  await clickBtn('btn-clear');
  await page.waitForTimeout(400);
  await typeCmd('PC1=(0,0)');
  // 必须先退出工具态：工具分支在 pointerdown 里直接 return（不走拖拽/捕获路径）
  const acToolNow = await page.evaluate(() => window.__ggbpyDebug.toolState().activeTool);
  if (acToolNow) {
    await page.click('#cat-tools .tool-btn[data-tool="' + acToolNow + '"]');
    await page.waitForTimeout(250);
  }
  check('拖拽前已退出工具态（否则 pointerdown 走工具分支，不建捕获）',
        (await page.evaluate(() => window.__ggbpyDebug.toolState().activeTool)) === null,
        JSON.stringify(await page.evaluate(() => window.__ggbpyDebug.toolState())));
  const pcScreen = await page.evaluate(() => window.__ggbpyDebug.toScreen(0, 0));
  const pcRect = await page.evaluate(() => { const q = document.getElementById('cv').getBoundingClientRect(); return { left: q.left, top: q.top }; });
  await page.evaluate(() => { window.__pid = null; document.getElementById('cv').addEventListener('pointerdown', (e) => { window.__pid = e.pointerId; }, true); });
  await page.mouse.move(pcRect.left + pcScreen.x, pcRect.top + pcScreen.y);
  await page.mouse.down();
  await page.waitForTimeout(150);
  const pcHeld = await page.evaluate(() => {
    const cv = document.getElementById('cv');
    return window.__pid != null ? cv.hasPointerCapture(window.__pid) : false;
  });
  await page.mouse.up();
  await page.waitForTimeout(250);
  check('按下画布对象后画布**捕获**该指针（修复前自递归 → 捕获静默失效）', pcHeld === true, String(pcHeld));
  check('格点吸附/指针捕获无新增 JS 错误', JS_ERRORS.length === acErrBefore,
        JS_ERRORS.slice(acErrBefore).join(';').slice(0, 60));

  // -------------------------------------------------------------------------
  section('AD. 坐标系：原点不画标记（保持干净）');
  const adErrBefore = JS_ERRORS.length;
  await clickBtn('btn-clear');
  await page.waitForTimeout(400);
  await clickBtn('btn-home');                       // 复位视图 → 原点回到画布中心
  await page.waitForTimeout(350);
  for (const id of ['btn-grid', 'btn-axes']) {      // 确保网格/坐标轴开启（否则断言会空转）
    const on = await page.evaluate((i) => document.getElementById(i).classList.contains('active'), id);
    if (!on) { await clickBtn(id); await page.waitForTimeout(150); }
  }
  const adOrigin = await page.evaluate(() => {
    const s = window.__ggbpyDebug.toScreen(0, 0);
    const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
    const R = 14, n = R * 2 + 1;
    const d = ctx.getImageData(Math.round(s.x - R), Math.round(s.y - R), n, n).data;
    let drawn = 0;
    for (let i = 0; i < d.length; i += 4) if (d[i + 3] !== 0) drawn++;   // 空白处 alpha=0，必须按 alpha 判
    return { ox: Math.round(s.x), oy: Math.round(s.y), box: n * n, drawn: drawn };
  });
  // 实测：仅有坐标轴 ≈ 165；旧「灰点+圆环+O」≈ 253；坐标轴关掉 ≈ 0
  check('2D 原点邻域只有坐标轴、没有原点标记（60 < 已绘制像素 < 200）',
        adOrigin.drawn > 60 && adOrigin.drawn < 200, JSON.stringify(adOrigin));
  check('坐标轴渲染无新增 JS 错误', JS_ERRORS.length === adErrBefore,
        JS_ERRORS.slice(adErrBefore).join(';').slice(0, 60));

  // -------------------------------------------------------------------------
  section('AE. 全局快捷键（Ctrl+Shift+G/X/S，复用菜单按钮同一实现）');
  const aeErrBefore = JS_ERRORS.length;
  const aeState = () => page.evaluate(() => ({
    grid: document.getElementById('btn-grid').classList.contains('active'),
    axes: document.getElementById('btn-axes').classList.contains('active'),
    snapOn: window.__ggbpyDebug.snapState().on,
    msg: (document.getElementById('msg') || {}).textContent || ''
  }));
  const ae0 = await aeState();
  await page.keyboard.press('Control+Shift+KeyG');
  await page.waitForTimeout(220);
  const aeG1 = await aeState();
  await page.keyboard.press('Control+Shift+KeyG');
  await page.waitForTimeout(220);
  const aeG2 = await aeState();
  check('Ctrl+Shift+G 切换网格显示（再按恢复）',
        aeG1.grid === !ae0.grid && aeG2.grid === ae0.grid,
        JSON.stringify({ 初始: ae0.grid, 一次: aeG1.grid, 两次: aeG2.grid }));
  await page.keyboard.press('Control+Shift+KeyX');
  await page.waitForTimeout(220);
  const aeX1 = await aeState();
  await page.keyboard.press('Control+Shift+KeyX');
  await page.waitForTimeout(220);
  const aeX2 = await aeState();
  check('Ctrl+Shift+X 切换坐标轴显示（再按恢复）',
        aeX1.axes === !ae0.axes && aeX2.axes === ae0.axes,
        JSON.stringify({ 初始: ae0.axes, 一次: aeX1.axes, 两次: aeX2.axes }));
  await page.keyboard.press('Control+Shift+KeyS');
  await page.waitForTimeout(220);
  const aeS1 = await aeState();
  check('Ctrl+Shift+S 切换吸附并给出提示',
        aeS1.snapOn === !ae0.snapOn && /吸附/.test(aeS1.msg),
        JSON.stringify({ snapOn: aeS1.snapOn, msg: aeS1.msg.slice(0, 20) }));
  await page.keyboard.press('Control+Shift+KeyS');           // 还原
  await page.waitForTimeout(200);
  // 误触守护：无修饰键的字母（在命令框里打字）不应触发任何切换
  await page.fill('#cmd', 'gx');
  await page.waitForTimeout(200);
  const aePlain = await aeState();
  check('无修饰键的字母不会误触（命令框输入 gx 后状态不变）',
        aePlain.grid === ae0.grid && aePlain.axes === ae0.axes && aePlain.snapOn === ae0.snapOn,
        JSON.stringify({ grid: aePlain.grid, axes: aePlain.axes, snapOn: aePlain.snapOn }));
  await page.fill('#cmd', '');
  await page.waitForTimeout(150);
  const aeTitles = await page.evaluate(() => ['btn-grid', 'btn-axes', 'btn-snap']
    .map((i) => document.getElementById(i).getAttribute('title') || ''));
  check('三个开关的悬停提示写明快捷键（可发现性）',
        aeTitles[0].indexOf('Ctrl+Shift+G') >= 0 && aeTitles[1].indexOf('Ctrl+Shift+X') >= 0
        && aeTitles[2].indexOf('Ctrl+Shift+S') >= 0, JSON.stringify(aeTitles));
  check('全局快捷键无新增 JS 错误', JS_ERRORS.length === aeErrBefore,
        JS_ERRORS.slice(aeErrBefore).join(';').slice(0, 60));

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
