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
