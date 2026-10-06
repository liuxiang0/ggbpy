const { chromium } = require('/home/kumath/.openclaw/workspace/node_modules/playwright-core');
(async () => {
  const b = await chromium.launch({ executablePath: '/home/kumath/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome', headless: true, args: ['--no-sandbox'] });
  const p = await b.newPage({ viewport: { width: 1400, height: 900 } });
  await p.goto('http://127.0.0.1:8090/', { waitUntil: 'load' });
  await p.waitForTimeout(900);
  await p.fill('#cmd', 'vm=Slider[0,10,1,(-2,2),vertical]');
  await p.press('#cmd', 'Enter');
  await p.waitForTimeout(500);
  const el = async () => ((await (await p.request.get('http://127.0.0.1:8090/api/state')).json()).elements || []).filter((e) => e.label === 'vm')[0];
  const b0 = await el();
  console.log('  初始 slider_x/y =', b0.slider_x, b0.slider_y, '| val =', b0.val, '| vert =', b0.slider_vert);
  const box = await p.evaluate(() => window.__ggbpyDebug.widgetBoxes()['vm']);
  const cx = (box.x0 + box.x1) / 2, cyFar = box.y0 + 8;    // 远离滑钮（val=0 → 滑钮在底部）
  const fire = async (type, px, py, moveTo) => await p.evaluate(([t, x, y, m]) => {
    const cv = document.getElementById('cv'), r = cv.getBoundingClientRect();
    cv.dispatchEvent(new PointerEvent(t, { bubbles: true, cancelable: true, pointerId: 1,
      clientX: r.x + (m ? m[0] : x), clientY: r.y + (m ? m[1] : y), offsetX: m ? m[0] : x, offsetY: m ? m[1] : y }));
  }, [type, px, py, moveTo || null]);
  await fire('pointerdown', cx, cyFar);
  await p.waitForTimeout(120);
  console.log('  dragState:', JSON.stringify(await p.evaluate(() => window.__ggbpyDebug.dragState())));
  await fire('pointermove', cx, cyFar, [cx + 70, cyFar + 40]);
  await fire('pointerup', cx, cyFar, [cx + 70, cyFar + 40]);
  await p.waitForTimeout(500);
  const b1 = await el();
  console.log('  拖后 slider_x/y =', b1.slider_x, b1.slider_y, '| defn =', b1.defn);
  console.log('  判定:', (b0.slider_x !== b1.slider_x || b0.slider_y !== b1.slider_y) ? '✓ 整条滑块被移动' : '✗ 未移动');
  await b.close();
})();
