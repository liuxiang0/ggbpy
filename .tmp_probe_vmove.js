const { chromium } = require('/home/kumath/.openclaw/workspace/node_modules/playwright-core');
(async () => {
  const b = await chromium.launch({ executablePath: '/home/kumath/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome', headless: true, args: ['--no-sandbox'] });
  const p = await b.newPage({ viewport: { width: 1400, height: 900 } });
  await p.goto('http://127.0.0.1:8090/', { waitUntil: 'load' });
  await p.waitForTimeout(900);
  const type = async (t) => { await p.fill('#cmd', t); await p.press('#cmd', 'Enter'); await p.waitForTimeout(250); };
  await type('vm=Slider[0,10,1,(-2,2),vertical]');
  await p.waitForTimeout(400);
  const st = async () => ((await (await p.request.get('http://127.0.0.1:8090/api/state')).json()).elements || []).filter((e) => e.label === 'vm')[0];
  const before = await st();
  const box = await p.evaluate(() => window.__ggbpyDebug.widgetBoxes()['vm']);
  const x = (box.x0 + box.x1) / 2, yFar = box.y0 + 8;   // 远离滑钮（值 0 → 滑钮在底部）
  await p.evaluate(([px, py]) => {
    const cv = document.getElementById('cv'), r = cv.getBoundingClientRect();
    cv.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, pointerId: 1,
      clientX: r.x + px, clientY: r.y + py, offsetX: px, offsetY: py }));
  }, [x, yFar]);
  await p.waitForTimeout(150);
  console.log('  拖轨道(远离滑钮) dragState:', JSON.stringify(await p.evaluate(() => window.__ggbpyDebug.dragState())));
  await p.evaluate(([px, py]) => {
    const cv = document.getElementById('cv'), r = cv.getBoundingClientRect();
    cv.dispatchEvent(new PointerEvent('pointermove', { bubbles: true, cancelable: true, pointerId: 1,
      clientX: r.x + px + 60, clientY: r.y + py + 30, offsetX: px + 60, offsetY: py + 30 }));
    cv.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, cancelable: true, pointerId: 1,
      clientX: r.x + px + 60, clientY: r.y + py + 30, offsetX: px + 60, offsetY: py + 30 }));
  }, [x, yFar]);
  await p.waitForTimeout(500);
  const after = await st();
  console.log('  位置 %s,%s → %s,%s | defn %s' % (before.slider_x, before.slider_y, after.slider_x, after.slider_y, after.defn));
  console.log('  滑块是否移动:', (before.slider_x !== after.slider_x || before.slider_y !== after.slider_y) ? '✓ 可以移动' : '✗ 仍不能移动');
  // 再验证：抓滑钮（值 0 → 在底部）仍能改值
  const box2 = await p.evaluate(() => window.__ggbpyDebug.widgetBoxes()['vm']);
  await p.evaluate(([px, py]) => {
    const cv = document.getElementById('cv'), r = cv.getBoundingClientRect();
    for (const t of ['pointerdown', 'pointerup']) cv.dispatchEvent(new PointerEvent(t, { bubbles: true, cancelable: true, pointerId: 1,
      clientX: r.x + px, clientY: r.y + py, offsetX: px, offsetY: py }));
  }, [(box2.x0 + box2.x1) / 2, box2.y1 - 5]);
  await p.waitForTimeout(400);
  const v = (await st()).val;
  console.log('  抓底部(近滑钮)改值 →', v, '(期望接近 0)');
  await b.close();
})();
