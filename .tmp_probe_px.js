const { chromium } = require('/home/kumath/.openclaw/workspace/node_modules/playwright-core');
(async () => {
  const b = await chromium.launch({ executablePath: '/home/kumath/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome', headless: true, args: ['--no-sandbox'] });
  const p = await b.newPage({ viewport: { width: 1400, height: 900 } });
  await p.goto('http://127.0.0.1:8090/', { waitUntil: 'load' });
  await p.waitForTimeout(900);
  const type = async (t) => { await p.fill('#cmd', t); await p.press('#cmd', 'Enter'); await p.waitForTimeout(250); };
  const box = async (l) => await p.evaluate((k) => window.__ggbpyDebug.widgetBoxes()[k] || null, l);
  const val = async (l) => Number((((await (await p.request.get('http://127.0.0.1:8090/api/state')).json()).elements || []).filter((e) => e.label === l)[0] || {}).val);
  await type('h1=Slider[0,10,1,(-4,4)]');
  const b1 = await box('h1');
  console.log('  水平默认: 轨道 px =', Math.round(Math.abs(b1.s1 - b1.s0)), '(期望 140)');
  await type('SetSliderLength[h1, 240]');
  const b2 = await box('h1');
  console.log('  设 240 后: 轨道 px =', Math.round(Math.abs(b2.s1 - b2.s0)), '| state.slider_px =',
    ((await (await p.request.get('http://127.0.0.1:8090/api/state')).json()).elements || []).filter((e) => e.label === 'h1')[0].slider_px);
  await type('v1=Slider[0,10,1,(-4,0),vertical,200]');
  const b3 = await box('v1');
  console.log('  竖直 200px: 轨道 px =', Math.round(Math.abs(b3.s1 - b3.s0)), '| 方向朝上 =', b3.s1 < b3.s0, '| 播放按钮在底部 =', b3.playY0 > b3.y1);
  // 拖动仍改值（水平，靠右 → 接近 max）
  const v0 = await val('h1');
  await p.evaluate(([px, py]) => {
    const cv = document.getElementById('cv'), r = cv.getBoundingClientRect();
    for (const t of ['pointerdown', 'pointerup']) cv.dispatchEvent(new PointerEvent(t, { bubbles: true, cancelable: true, pointerId: 1,
      clientX: r.x + px, clientY: r.y + py, offsetX: px, offsetY: py }));
  }, [b2.s1 - 4, (b2.y0 + b2.y1) / 2]);
  await p.waitForTimeout(400);
  console.log('  拖到右端: 值', v0, '→', await val('h1'), '(期望接近 10)');
  await b.close();
})();
