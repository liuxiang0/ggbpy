/* ggbpy P0 前端：画布渲染 + 拖拽 + 缩放平移 + 代数输入 */
(function () {
  'use strict';

  var canvas = document.getElementById('cv');
  var ctx = canvas.getContext('2d');
  // 数值容差（与 kernel/tolerance.py 对应分级）：判断"等于 0 / 重合 / 退化"时统一用这些常量，
  // 不要写裸 1e-12 之类字面量（devtools/test_tolerance.py 会扫描并阻止新增）。
  var EPSILON = 1e-12;   // 判定"等于 0"（分母/行列式/叉积）
  var COORD = 1e-9;      // 坐标/长度尺度（点重合、退化长度）
  var COARSE = 1e-6;     // 采样/取景尺度（角度、最小跨度）

  // 数据表见 static/data.js（P2 拆分）；缺文件时退化为空表
  var GGB_DATA = window.GGB_DATA || {};
  // 会话隔离（P2）：首次访问生成随机 sid 写入 cookie —— 不同浏览器/上下文各自独立，
  // 未带 cookie 的脚本请求仍落到 default 会话（保持既有 API 兼容）。
  (function ensureSessionId() {
    try {
      var mSid = document.cookie.match(/(?:^|;\s*)ggbpy_sid=([^;]*)/);
      if (!mSid || !mSid[1] || mSid[1] === 'default') {
        var rnd = 'web_' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-4);
        document.cookie = 'ggbpy_sid=' + rnd + ';path=/;max-age=86400;SameSite=Lax';
      }
    } catch (e) { /* cookie 不可用时退回 default 会话 */ }
  })();
  var cmdEl = document.getElementById('cmd');
  var msgEl = document.getElementById('msg');
  var listEl = document.getElementById('objlist');

  // ---------- i18n ----------
  // 文案表见 static/i18n.js（P2 拆分）；缺文件时退化为显示原始 key
  var I18N = window.GGB_I18N || { zh: {}, en: {} };
  var MSG_MAP_EN = {
    '已撤销': 'Undone', '没有可撤销的操作': 'Nothing to undo',
    '已重做': 'Redone', '没有可重做的操作': 'Nothing to redo',
    '已清空': 'Cleared', '已加载': 'Loaded', 'OK:OK': 'OK',
    '已开启格点吸附（可按住 Shift 临时吸附）': 'Grid snap ON (hold Shift for temporary snap)',
    '已关闭格点吸附': 'Grid snap OFF',
  };
  var lang = localStorage.getItem('ggb_lang') || 'zh';

  // ---------- 明暗主题 ----------
  var theme = localStorage.getItem('ggb_theme') || 'light';
  var C = null;   // canvas 绘制颜色（随主题）
  function themeColors() {
    var dark = theme === 'dark';
    return {
      grid: dark ? '#1e293b' : '#f3f4f6',
      major: dark ? '#475569' : '#9ca3af',
      tick: dark ? '#94a3b8' : '#6b7280',
      axis: dark ? '#cbd5e1' : '#374151',
      text: dark ? '#e2e8f0' : '#111827',
      label: dark ? '#e2e8f0' : '#1f2937',
      tipBg: dark ? 'rgba(226,232,240,.92)' : 'rgba(15,23,42,.85)',
      tipFg: dark ? '#0f172a' : '#fff'
    };
  }
  function applyTheme() {
    document.body.setAttribute('data-theme', theme);
    C = themeColors();
    var tb = document.getElementById('btn-theme');
    if (tb) tb.textContent = theme === 'dark' ? '☀️' : '🌙';
  }
  applyTheme();
  btn('btn-theme', function () {
    theme = theme === 'light' ? 'dark' : 'light';
    localStorage.setItem('ggb_theme', theme);
    applyTheme();
    render();
  });


  var RE_MAP_EN = [
    [/^找不到对象 (.+)$/, 'Object $1 not found'],
    [/^找不到点 (.+)$/, 'Point $1 not found'],
    [/^对象 (.+) 已存在，请换一个名字$/, 'Object $1 already exists, choose another name'],
    [/^对象 (.+) 已存在$/, 'Object $1 already exists'],
    [/^(.+) 已锁定，不能移动$/, '$1 is locked, cannot move'],
    [/^(.+) 已锁定，不能删除$/, '$1 is locked, cannot delete'],
    [/^(.+) 已锁定，不能重命名$/, '$1 is locked, cannot rename'],
    [/^(.+) 已锁定，不能重定义$/, '$1 is locked, cannot redefine'],
    [/^(.+) 是派生对象，不能移动$/, '$1 is a derived object, cannot move'],
    [/^(.+) 暂不支持拖拽$/, '$1 does not support dragging'],
    [/^存在锁定的依赖对象 (.+)，不能删除$/, 'locked dependent object $1 exists, cannot delete'],
  ];

  btn('btn-lang', function () {
    lang = (lang === 'zh') ? 'en' : 'zh';
    localStorage.setItem('ggb_lang', lang);
    applyLang();
    renderCatbar();
    if (activeCat) showCat(activeCat);
    render();
  });
  function angleUnit() { return localStorage.getItem('ggb_angle_unit') === 'rad' ? 'rad' : 'deg'; }
  function refreshAngleUnitBtn() {
    var ab = document.getElementById('btn-angunit');
    if (ab) ab.textContent = angleUnit() === 'rad' ? 'rad' : '°';
  }
  btn('btn-angunit', function () {
    localStorage.setItem('ggb_angle_unit', angleUnit() === 'deg' ? 'rad' : 'deg');
    refreshAngleUnitBtn();
    render();
  });
  refreshAngleUnitBtn();

  var view = { xmin: -8, xmax: 8, ymin: -8, ymax: 8 };
  var scale = 60;                 // px per world unit
  var elements = [];
  var selected = null;
  var listCursor = -1;   // 对象列表键盘光标行索引（↑/↓ 移动，Enter 选择）
  var drag = null;                // 拖拽中的自由点
  var pan = null;                 // 平移状态
  var dragPending = false;
  var lastDrag = null;
  var cssW = 0, cssH = 0, dpr = 1;  // 画布 CSS 逻辑尺寸（物理 = ×devicePixelRatio）
  var touches = {}, pinch = null;  // 多点触控：双指捏合缩放
  var hoverTip = null;              // 悬停坐标提示
  var dbgTipRect = null;            // 最近一次绘制的提示框位置（检测用）
  var selectMode = false;           // 选择工具模式（🖱）
  var selectedMulti = [];           // 框选多选集合
  var pendingImage = null;          // 待插入图片：{id, ratio}
  var marquee = null;               // 框选矩形（选择模式拖动）
  var toolPreview = null;           // 工具绘制中的动态预览（随鼠标）
  var shiftDrag = null;            // 选中对象整体拖动
  var shiftAccum = { dx: 0, dy: 0 };
  var shiftPending = false;

  // ---------- 视口 ----------
  function resize() {
    var wrap = document.getElementById('stage-wrap');
    cssW = wrap.clientWidth; cssH = wrap.clientHeight;
    dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(cssW * dpr);
    canvas.height = Math.round(cssH * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    fitView();
    if (mode3d) resize3d(); else loadState();
  }

  function fitView() {
    var w = cssW, h = cssH;
    if (!w || !h) return;
    var s = Math.min(w / (view.xmax - view.xmin), h / (view.ymax - view.ymin));
    scale = s;
    var cx = (view.xmin + view.xmax) / 2;
    var cy = (view.ymin + view.ymax) / 2;
    view.xmin = cx - w / (2 * s);
    view.xmax = cx + w / (2 * s);
    view.ymin = cy - h / (2 * s);
    view.ymax = cy + h / (2 * s);
  }

  // 画布上"实际可见可用区"（Canvas 坐标）：扣除停靠在底/左/右的对象面板浮层，
  // 否则画在画布内、但被 DOM 面板盖住的提示只露出一半。

  function wxp(sx) { return view.xmin + sx / scale; }
  function wyp(sy) { return view.ymin + (cssH - sy) / scale; }


  // ---------- 数据 ----------
  function loadState() {
    fetch('/api/state' + viewParams()).then(function (r) { return r.json(); }).then(function (d) {
      elements = d.elements;
      updateUndoBtns(d);
      render();
    }).catch(function () {});
  }

  function api(method, url, body, cb) {
    var opts = { method: method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    fetch(url, opts).then(function (r) { return r.json(); }).then(function (d) { cb(d); updateUndoBtns(d); }).catch(function (e) {
      setMsg('网络错误: ' + e, true);
    });
  }

  function updateUndoBtns(d) {
    if (!d || typeof d.can_undo === 'undefined') return;
    var ub = document.getElementById('btn-undo'), rb2 = document.getElementById('btn-redo');
    if (ub) ub.disabled = !d.can_undo;
    if (rb2) rb2.disabled = !d.can_redo;
  }

  // 试卷渲染/导出已抽到 static/exam.js（P2 前端拆分）；保留同名薄包装，调用点不变
  var _examMod = window.GGB_EXAM.create({
    t: t, setMsg: setMsg,
    getExam: function () { return exam; },
    getLang: function () { return lang; },
  });
  function renderExam() { return _examMod.renderExam.apply(null, arguments); }
  function exportExam() { return _examMod.exportExam.apply(null, arguments); }
  function escHtml(s) { return _examMod.escHtml(s); }

  // 面板渲染已抽到 static/panels.js（P2 前端拆分）；此处提供状态访问 + 同名薄包装
  function _panelStateGet(k) {
    switch (k) {
      case 'CAS_COMMANDS': return CAS_COMMANDS;
      case 'casOpen': return casOpen;
      case 'casPanel': return casPanel;
      case 'CMD_W': return CMD_W;
      case 'FN_T': return FN_T;
      case 'FN_W': return FN_W;
      case 'GREEK_T': return GREEK_T;
      case 'GREEK_W': return GREEK_W;
      case 'CHART_KINDS': return CHART_KINDS;
      case 'EPSILON': return EPSILON;
      case 'drag3dObj': return drag3dObj;
      case 'objShift3d': return objShift3d;
      case 'CHART_TOOL_CMD': return CHART_TOOL_CMD;
      case 'COORD': return COORD;
      case 'hintEl': return hintEl;
      case 'pendingImage': return pendingImage;
      case 'shiftKeyPressed': return shiftKeyPressed;
      case 'snapOn': return snapOn;
      case 'toolBusy': return toolBusy;
      case 'toolPointQueue': return toolPointQueue;
      case 'imgCache': return imgCache;
      case 'MSG_MAP_EN': return MSG_MAP_EN;
      case 'RE_MAP_EN': return RE_MAP_EN;
      case 'toolSel3d': return toolSel3d;
      case 'COARSE': return COARSE;
      case 'axisTicks3d': return axisTicks3d;
      case 'cam': return cam;
      case 'ctx3': return ctx3;
      case 'dbgProjCalls': return dbgProjCalls;
      case 'ortho3d': return ortho3d;
      case 'view3dMode': return view3dMode;
      case 'PIE_PAL': return PIE_PAL;
      case 'canvas': return canvas;
      case 'chartBoxes': return chartBoxes;
      case 'widgetBoxes': return widgetBoxes;
      case 'C': return C;
      case 'planeZ': return planeZ;
      case 'ctx3': return ctx3;
      case 'dbgProjReuse': return dbgProjReuse;
      case 'dbgOccTests': return dbgOccTests;
      case 'dbgLastFaces': return dbgLastFaces;
      case 'dbgLastSegs': return dbgLastSegs;
      case 'MESH_EDGE_BUDGET': return MESH_EDGE_BUDGET;
      case 'OCCLUSION_BUDGET': return OCCLUSION_BUDGET;
      case 'cssH': return cssH;
      case 'cssW': return cssW;
      case 'ctx': return ctx;
      case 'scale': return scale;
      case 'showAxes': return showAxes;
      case 'showGrid': return showGrid;
      case 'view': return view;
      case 'I18N': return I18N;
      case 'TOOL_CATS': return TOOL_CATS;
      case 'activeCat': return activeCat;
      case 'activeTool': return activeTool;
      case 'casCellsEl': return casCellsEl;
      case 'elements': return elements;
      case 'els3d': return els3d;
      case 'lang': return lang;
      case 'listCursor': return listCursor;
      case 'listEl': return listEl;
      case 'mode3d': return mode3d;
      case 'playState': return playState;
      case 'playingLabels': return playState ? Object.keys(playState.labels) : [];
      case 'selected': return selected;
      case 'selected3d': return selected3d;
      case 'selectedMulti': return selectedMulti;
      case 'tool3d': return tool3d;
      case 'toolSel': return toolSel;
      default: return undefined;
    }
  }
  var _overlay = window.GGB_OVERLAY.create({ get: _panelStateGet, findEl3d: findEl3d, line3: line3, proj3: proj3 });
  var _scene = window.GGB_SCENE.create({
    get: _panelStateGet, set: _panelStateSet,
    line3: line3, proj3: proj3, selectMeshFaces: selectMeshFaces,
  });

  function _panelStateSet(k, v) {
    if (k === 'activeCat') { activeCat = v; return; }
    if (k === 'dbgProjCalls') { dbgProjCalls = v; return; }
    if (k === 'dbgProjReuse') { dbgProjReuse = v; return; }
    if (k === 'dbgOccTests') { dbgOccTests = v; return; }
    if (k === 'dbgLastFaces') { dbgLastFaces = v; return; }
    if (k === 'dbgLastSegs') { dbgLastSegs = v; return; }

    if (k === 'toolSel3d') { toolSel3d = v; return; }    if (k === 'elements') { elements = v; return; }
    if (k === 'pendingImage') { pendingImage = v; return; }
    if (k === 'scale') { scale = v; return; }
    if (k === 'toolBusy') { toolBusy = v; return; }
    if (k === 'toolSel') { toolSel = v; return; }
    if (k === 'casOpen') { casOpen = v; return; }
  }
  var _panels = window.GGB_PANELS.create({ get: _panelStateGet, set: _panelStateSet });
  function t() { return _panels.t.apply(null, arguments); }
  function esc() { return _panels.esc.apply(null, arguments); }
  function fmtNum() { return _panels.fmtNum.apply(null, arguments); }
  // 画布滑块（线段 + 滑钮）：命中与取值（与对象列表里的 range 控件共用 /api/drag 语义）
  function sliderAt(sx, sy) {
    // 命中框是**矩形**：横滑块的矩形会罩住同锚点竖滑块的轨道/滑钮（反之亦然）→
    // 若只取"第一个命中"，拖竖滑块的滑钮会抓到横滑块（"竖直滑块拖不动"的根因之一）。
    // 改为按**到各自轨道的垂距**取最近者：竖滑块比 |sx-轨道x|、横滑块比 |sy-轨道y|。
    var best = null, bestD = Infinity;
    for (var k in widgetBoxes) {
      if (!Object.prototype.hasOwnProperty.call(widgetBoxes, k)) continue;
      var b = widgetBoxes[k];
      if (!b || b.kind !== 'slider') continue;
      if (!(sx >= b.x0 && sx <= b.x1 && sy >= b.y0 && sy <= b.y1)) continue;
      var d = (b.axis === 'y') ? Math.abs(sx - (b.x0 + b.x1) / 2) : Math.abs(sy - (b.y0 + b.y1) / 2);
      if (d < bestD) { bestD = d; best = k; }
    }
    return best;
  }
  function sliderPlayAt(sx, sy) {
    for (var k in widgetBoxes) {
      if (!Object.prototype.hasOwnProperty.call(widgetBoxes, k)) continue;
      var b = widgetBoxes[k];
      if (b && b.kind === 'slider' && typeof b.playX0 === 'number'
          && sx >= b.playX0 && sx <= b.playX1 && sy >= b.playY0 && sy <= b.playY1) return k;
    }
    return null;
  }
  // 取值用**屏幕坐标**换算（轨道长度按 px → 世界换算不再适用）；sx/sy 为画布局部坐标
  function sliderValueAt(label, sx, sy) {
    var b = widgetBoxes[label];
    var el = findEl(label);
    if (!b || !el || el.min === null || el.min === undefined) return 0;
    var _p = (b.axis === 'y') ? sy : sx;
    var f = (_p - b.s0) / ((b.s1 - b.s0) || 1);
    f = Math.max(0, Math.min(1, f));
    var v = el.min + f * ((el.max - el.min) || 0);
    var st = el.step && el.step > 0 ? el.step : 0;
    if (st > 0) v = Math.round(v / st) * st;
    return Math.max(el.min, Math.min(el.max, v));
  }

  function findEl() { return _panels.findEl.apply(null, arguments); }
  function findEl3d() { return _panels.findEl3d.apply(null, arguments); }
  function solidLabelName() { return _panels.solidLabelName.apply(null, arguments); }
  function applyLang() { return _panels.applyLang.apply(null, arguments); }
  // 列表渲染会重建行 DOM：若正处于行内定义编辑，渲染后为对应行重新打开输入框
  function reopenDefnEdit() {
    if (!defnEdit) return;
    var row = listEl.querySelector('.obj[data-label="' + defnEdit.label + '"]');
    var df = row && row.querySelector('.df');
    if (df && !df.querySelector('input')) startDefnEdit(df);
  }
  function renderList() { return _panels.renderList.apply(null, arguments); }
  // 行 DOM 由 panels 重建（薄包装不得改动）：用 MutationObserver 在重建后重开行内定义输入框
  if (window.MutationObserver) {
    new MutationObserver(function () { reopenDefnEdit(); }).observe(listEl, { childList: true, subtree: true });
  }
  function renderList3d() { return _panels.renderList3d.apply(null, arguments); }
  function renderToolsPanel() { return _panels.renderToolsPanel.apply(null, arguments); }
  function renderCas() { return _panels.renderCas.apply(null, arguments); }
  function renderCatbar() { return _panels.renderCatbar.apply(null, arguments); }
  function showCat() { return _panels.showCat.apply(null, arguments); }
  function populateEditBar() { return _panels.populateEditBar.apply(null, arguments); }
  function populateEditBar3d() { return _panels.populateEditBar3d.apply(null, arguments); }
  function updateToolButtons() { return _panels.updateToolButtons.apply(null, arguments); }
  function updateToolButtons3d() { return _panels.updateToolButtons3d.apply(null, arguments); }

  // 二维画布绘制基元（网格/坐标轴/线段/多边形/箭头） 已抽到 static/draw2d.js（P2 前端拆分）；同名薄包装保持调用点不变
  var _draw2d = window.GGB_D2.create({ get: _panelStateGet, fmtNum: fmtNum });
  function sxp() { return _draw2d.sxp.apply(null, arguments); }
  function syp() { return _draw2d.syp.apply(null, arguments); }
  function niceStep() { return _draw2d.niceStep.apply(null, arguments); }
  function drawGrid() { return _draw2d.drawGrid.apply(null, arguments); }
  function strokeSeg() { return _draw2d.strokeSeg.apply(null, arguments); }
  function strokePoly() { return _draw2d.strokePoly.apply(null, arguments); }
  function drawArrow() { return _draw2d.drawArrow.apply(null, arguments); }

  // 统计图渲染（六类二维统计图的画布绘制与命中框，P2 前端拆分） 已抽到 static/charts.js（P2 前端拆分）；同名薄包装保持调用点不变
  var _charts = window.GGB_CHARTS.create({ get: _panelStateGet, sxp: sxp, syp: syp });
  function usableCanvasRect() { return _charts.usableCanvasRect.apply(null, arguments); }
  function chartOff() { return _charts.chartOff.apply(null, arguments); }
  function chartBoxPut() { return _charts.chartBoxPut.apply(null, arguments); }
  function chartAt() { return _charts.chartAt.apply(null, arguments); }
  function drawBarChart() { return _charts.drawBarChart.apply(null, arguments); }
  function drawBoxPlot() { return _charts.drawBoxPlot.apply(null, arguments); }
  function drawPieChart() { return _charts.drawPieChart.apply(null, arguments); }
  function drawLineChart() { return _charts.drawLineChart.apply(null, arguments); }
  function drawScatterPlot() { return _charts.drawScatterPlot.apply(null, arguments); }
  function drawDotPlot() { return _charts.drawDotPlot.apply(null, arguments); }
  function drawStemPlot() { return _charts.drawStemPlot.apply(null, arguments); }

  // 三维投影与屏幕空间命中判定（P2 前端拆分：render3d 第一步） 已抽到 static/proj3d.js（P2 前端拆分）；同名薄包装保持调用点不变
  var _proj3d = window.GGB_P3.create({ get: _panelStateGet, set: _panelStateSet, sxp: sxp, syp: syp });
  function is3DEl() { return _proj3d.is3DEl.apply(null, arguments); }
  function camBasis3() { return _proj3d.camBasis3.apply(null, arguments); }
  function proj3() { return _proj3d.proj3.apply(null, arguments); }
  function line3() { return _proj3d.line3.apply(null, arguments); }
  function pointInScreenPoly() { return _proj3d.pointInScreenPoly.apply(null, arguments); }
  function snapAxis3d() { return _proj3d.snapAxis3d.apply(null, arguments); }
  function wptIn() { return _proj3d.wptIn.apply(null, arguments); }
  function wsegHit() { return _proj3d.wsegHit.apply(null, arguments); }
  function pointInPoly() { return _proj3d.pointInPoly.apply(null, arguments); }
  function distToSeg() { return _proj3d.distToSeg.apply(null, arguments); }

  // 三维坐标轴与刻度绘制（P2 前端拆分：render3d 第二步） 已抽到 static/axes3d.js（P2 前端拆分）；同名薄包装保持调用点不变
  var _axes3d = window.GGB_AX3.create({ get: _panelStateGet, fmtNum: fmtNum, proj3: proj3, line3: line3 });
  function saveAxisTicks3d() { return _axes3d.saveAxisTicks3d.apply(null, arguments); }
  function niceStep3d() { return _axes3d.niceStep3d.apply(null, arguments); }
  function drawAxes3d() { return _axes3d.drawAxes3d.apply(null, arguments); }
  function arrowHead3() { return _axes3d.arrowHead3.apply(null, arguments); }
  function drawMiniAxes3d() { return _axes3d.drawMiniAxes3d.apply(null, arguments); }

  // 三维工具点击交互（P2 前端拆分：3D 工具族） 已抽到 static/tools3d.js（P2 前端拆分）；同名薄包装保持调用点不变
  var _tools3d = window.GGB_T3D.create({ get: _panelStateGet, set: _panelStateSet, api: api, camBasis3: camBasis3, distToSeg: distToSeg, drawAxes3d: drawAxes3d, drawMiniAxes3d: drawMiniAxes3d, fmtW: fmtW, hitPoint3d: hitPoint3d, load3d: load3d, proj3: proj3, render3d: render3d, renderList3d: renderList3d, resetTool3d: resetTool3d, setMsg: setMsg, setToolStatus3d: setToolStatus3d, snapAxis3d: snapAxis3d, unproj3: unproj3, updateToolButtons3d: updateToolButtons3d, updateUndoBtns: updateUndoBtns });
  function translateMsg() { return _tools3d.translateMsg.apply(null, arguments); }
  function hitObject3dKind() { return _tools3d.hitObject3dKind.apply(null, arguments); }
  function tool3dPointAt() { return _tools3d.tool3dPointAt.apply(null, arguments); }
  function tool3dClick() { return _tools3d.tool3dClick.apply(null, arguments); }
  function postInput3d() { return _tools3d.postInput3d.apply(null, arguments); }

  // 二维元素绘制层（元素/圆锥曲线/不等式/叠加层/图片，P2 前端拆分） 已抽到 static/render2d.js（P2 前端拆分）；同名薄包装保持调用点不变
  var _render2d = window.GGB_R2D.create({ get: _panelStateGet, angleUnit: angleUnit, findEl: findEl, drawArrow: drawArrow, drawBarChart: drawBarChart, drawBoxPlot: drawBoxPlot, drawDotPlot: drawDotPlot, drawStemPlot: drawStemPlot, drawGrid: drawGrid, drawLineChart: drawLineChart, drawPieChart: drawPieChart, drawScatterPlot: drawScatterPlot, fmtNum: fmtNum, is3DEl: is3DEl, populateEditBar: populateEditBar, render: render, renderList: renderList, strokeSeg: strokeSeg, sxp: sxp, syp: syp, tipText: tipText, usableCanvasRect: usableCanvasRect });
  function gcdInt() { return _render2d.gcdInt.apply(null, arguments); }
  function fmtAngleDeg() { return _render2d.fmtAngleDeg.apply(null, arguments); }
  function drawSelectionOverlay() { return _render2d.drawSelectionOverlay.apply(null, arguments); }
  function drawOverlay() { return _render2d.drawOverlay.apply(null, arguments); }
  function colorOf() { return _render2d.colorOf.apply(null, arguments); }
  function getImage() { return _render2d.getImage.apply(null, arguments); }
  function drawImageEl() { return _render2d.drawImageEl.apply(null, arguments); }
  function drawElement() { return _render2d.drawElement.apply(null, arguments); }
  function conicPathPts() { return _render2d.conicPathPts.apply(null, arguments); }
  function drawConic() { return _render2d.drawConic.apply(null, arguments); }
  function drawInequality() { return _render2d.drawInequality.apply(null, arguments); }

  // 二维工具点击交互（P2 前端拆分：2D 工具族） 已抽到 static/tools2d.js（P2 前端拆分）；同名薄包装保持调用点不变
  var _tools2d = window.GGB_T2D.create({ get: _panelStateGet, set: _panelStateSet, api: api, cancelTool: cancelTool, chartToolPrompt: chartToolPrompt, conicPathPts: conicPathPts, distToSeg: distToSeg, drawAxes3d: drawAxes3d, drawElement: drawElement, drawGrid: drawGrid, drawMiniAxes3d: drawMiniAxes3d, drawOverlay: drawOverlay, drawSelectionOverlay: drawSelectionOverlay, finishPolygon: finishPolygon, finishPolyline: finishPolyline, fmtNum: fmtNum, fmtW: fmtW, hitAnyPoint: hitAnyPoint, hitObject: hitObject, is3DEl: is3DEl, load3d: load3d, loadState: loadState, niceStep: niceStep, pointInPoly: pointInPoly, populateEditBar: populateEditBar, populateEditBar3d: populateEditBar3d, postInput: postInput, render: render, render3d: render3d, renderList: renderList, renderList3d: renderList3d, setMsg: setMsg, setToolStatus: setToolStatus, snapPoint: snapPoint, sxp: sxp, syp: syp, t: t, tipText: tipText, toolHintText: toolHintText, translateMsg: translateMsg, updateToolButtons: updateToolButtons, updateUndoBtns: updateUndoBtns, usableCanvasRect: usableCanvasRect, wxp: wxp, wyp: wyp });
  function viewParams() { return _tools2d.viewParams.apply(null, arguments); }
  function chartDataPrompt() { return _tools2d.chartDataPrompt.apply(null, arguments); }
  function resetTool() { return _tools2d.resetTool.apply(null, arguments); }
  function snapHitLabel() { return _tools2d.snapHitLabel.apply(null, arguments); }
  function toolPointAt() { return _tools2d.toolPointAt.apply(null, arguments); }
  function toolCanvasClick() { return _tools2d.toolCanvasClick.apply(null, arguments); }
  function widgetClick() { return _tools2d.widgetClick.apply(null, arguments); }
  function widgetHit() { return _tools2d.widgetHit.apply(null, arguments); }
  function widgetAct() { return _tools2d.widgetAct.apply(null, arguments); }

  // 三维对象位移与拖动（P2 前端拆分） 已抽到 static/drag3d.js（P2 前端拆分）；同名薄包装保持调用点不变
  var _drag3d = window.GGB_DRAG3.create({ get: _panelStateGet, api: api, drawAxes3d: drawAxes3d, drawElement: drawElement, drawGrid: drawGrid, drawMiniAxes3d: drawMiniAxes3d, drawOverlay: drawOverlay, drawSelectionOverlay: drawSelectionOverlay, findEl3d: findEl3d, fmtNum: fmtNum, is3DEl: is3DEl, load3d: load3d, populateEditBar: populateEditBar, render: render, render3d: render3d, renderList: renderList, renderList3d: renderList3d, setMsg: setMsg, sxp: sxp, syp: syp, tipText: tipText, translateMsg: translateMsg, updateUndoBtns: updateUndoBtns, usableCanvasRect: usableCanvasRect });
  function localShift3dEl() { return _drag3d.localShift3dEl.apply(null, arguments); }
  function flushObjShift3d() { return _drag3d.flushObjShift3d.apply(null, arguments); }
  function shiftLocal() { return _drag3d.shiftLocal.apply(null, arguments); }

  // 命中测试与逆投影（2D/3D 命中、屏幕→世界逆投影、路径参数） 已抽到 static/hit.js（P2 前端拆分）；同名薄包装保持调用点不变
  var _hit = window.GGB_HIT.create({ get: _panelStateGet, camBasis3: camBasis3, conicPathPts: conicPathPts, distToSeg: distToSeg, pointInPoly: pointInPoly, proj3: proj3, sxp: sxp, syp: syp });
  function unproj3() { return _hit.unproj3.apply(null, arguments); }
  function hitObject3d() { return _hit.hitObject3d.apply(null, arguments); }
  function nearestPathParam() { return _hit.nearestPathParam.apply(null, arguments); }
  function hitObject() { return _hit.hitObject.apply(null, arguments); }

  // 工具预览计算（2D 工具预览几何，P2 前端拆分） 已抽到 static/preview.js（P2 前端拆分）；同名薄包装保持调用点不变
  var _preview = window.GGB_PREV.create({ get: _panelStateGet, findEl: findEl, hitObject: hitObject, niceStep: niceStep, snapPoint: snapPoint, wxp: wxp, wyp: wyp });
  function conicCoeffs() { return _preview.conicCoeffs.apply(null, arguments); }
  function conicPreviewSegs() { return _preview.conicPreviewSegs.apply(null, arguments); }
  function computeToolPreview() { return _preview.computeToolPreview.apply(null, arguments); }

  // LaTeX 序列化（表达式/几何对象 → LaTeX，P2 前端拆分） 已抽到 static/latex.js（P2 前端拆分）；同名薄包装保持调用点不变
  var _latex = window.GGB_LATEX.create({ get: _panelStateGet });
  function toLatex() { return _latex.toLatex.apply(null, arguments); }

  // 界面弹窗与提示（帮助弹窗等，P2 前端拆分） 已抽到 static/ui.js（P2 前端拆分）；同名薄包装保持调用点不变
  var _ui = window.GGB_UI.create({ get: _panelStateGet, set: _panelStateSet, api: api, casInsert: casInsert, esc: esc, renderCas: renderCas, setMsg: setMsg, translateMsg: translateMsg, updateUndoBtns: updateUndoBtns });
  function showHelpModal() { return _ui.showHelpModal.apply(null, arguments); }

  function setMsg(msg, isErr) {
    msgEl.textContent = translateMsg(msg);
    msgEl.className = isErr ? 'err' : '';
  }

  // ---------- 绘制 ----------


  var showGrid = true;
  var showAxes = true;
  btn('btn-grid', function () { showGrid = !showGrid; this.classList.toggle('active', showGrid); render(); });
  btn('btn-axes', function () { showAxes = !showAxes; this.classList.toggle('active', showAxes); render(); });


  // 选中对象 XOR 高亮（橙色虚线轮廓）

  // 坐标轴覆盖层：箭头、x/y 标签（原点不标记，保持坐标系干净）



  // ---- 图片对象：缓存 + 按两基点仿射绘制 ----
  var imgCache = {};   // imgid -> HTMLImageElement



  function render() {
    chartBoxes = {};
    ctx.clearRect(0, 0, cssW, cssH);
    drawGrid();
    // 先画非点对象，点最后画（不被线覆盖）；跳过 3D 元素
    for (var i = 0; i < elements.length; i++) {
      if (elements[i].kind !== 'point' && !is3DEl(elements[i])) drawElement(elements[i]);
    }
    for (var j = 0; j < elements.length; j++) {
      if (elements[j].kind === 'point' && !is3DEl(elements[j])) drawElement(elements[j]);
    }
    drawOverlay();
    if (selected || selectedMulti.length) {
      // 选中对象 XOR 高亮（橙色虚线轮廓，支持多选）
      for (var si2 = 0; si2 < elements.length; si2++) {
        if (elements[si2].label === selected || selectedMulti.indexOf(elements[si2].label) !== -1) {
          drawSelectionOverlay(elements[si2]);
        }
      }
    }
    if (activeTool && toolSel.length) {
      // 工具进行中：已选中的对象同样显示橙色虚线高亮（点在下层绘制时已加圈）
      for (var tsi = 0; tsi < elements.length; tsi++) {
        var tsel = elements[tsi];
        if (tsel.kind === 'point') continue;
        if (toolSel.indexOf(tsel.label) !== -1) drawSelectionOverlay(tsel);
      }
    }
    if (toolPreview) {
      // 工具动态预览（虚线半透明，随鼠标）
      ctx.save();
      ctx.globalAlpha = 0.55;
      ctx.setLineDash([6, 4]);
      ctx.strokeStyle = '#2563eb';
      ctx.lineWidth = 2;
      ctx.beginPath();
      if (toolPreview.type === 'seg') {
        ctx.moveTo(sxp(toolPreview.x1), syp(toolPreview.y1));
        ctx.lineTo(sxp(toolPreview.x2), syp(toolPreview.y2));
      } else if (toolPreview.type === 'circle') {
        ctx.arc(sxp(toolPreview.cx), syp(toolPreview.cy), Math.max(2, toolPreview.r * scale), 0, Math.PI * 2);
      } else if (toolPreview.type === 'poly' && toolPreview.pts.length >= 2) {
        ctx.moveTo(sxp(toolPreview.pts[0][0]), syp(toolPreview.pts[0][1]));
        for (var pvi = 1; pvi < toolPreview.pts.length; pvi++) ctx.lineTo(sxp(toolPreview.pts[pvi][0]), syp(toolPreview.pts[pvi][1]));
      } else if (toolPreview.type === 'conic') {
        var pv = toolPreview;
        if (pv.ctype === 'ellipse') {
          var eca = Math.cos(pv.angle || 0), esa2 = Math.sin(pv.angle || 0);
          for (var eti = 0; eti <= 128; eti++) {
            var et = eti * Math.PI * 2 / 128;
            var ex = pv.cx + pv.semi_a * Math.cos(et) * eca - pv.semi_b * Math.sin(et) * esa2;
            var ey = pv.cy + pv.semi_a * Math.cos(et) * esa2 + pv.semi_b * Math.sin(et) * eca;
            if (eti === 0) ctx.moveTo(sxp(ex), syp(ey)); else ctx.lineTo(sxp(ex), syp(ey));
          }
        } else if (pv.ctype === 'hyperbola') {
          var hca = Math.cos(pv.angle || 0), hsa2 = Math.sin(pv.angle || 0);
          var hb = function (sgn) {
            ctx.moveTo(sxp(pv.cx + sgn * pv.semi_a * Math.cosh(-2.2) * hca - pv.semi_b * Math.sinh(-2.2) * hsa2),
                       syp(pv.cy + sgn * pv.semi_a * Math.cosh(-2.2) * hsa2 + pv.semi_b * Math.sinh(-2.2) * hca));
            for (var hti = -43; hti <= 43; hti++) {
              var ht = hti * 0.05;
              var hx2 = pv.cx + sgn * pv.semi_a * Math.cosh(ht) * hca - pv.semi_b * Math.sinh(ht) * hsa2;
              var hy2 = pv.cy + sgn * pv.semi_a * Math.cosh(ht) * hsa2 + pv.semi_b * Math.sinh(ht) * hca;
              ctx.lineTo(sxp(hx2), syp(hy2));
            }
          };
          hb(1); hb(-1);
        } else if (pv.ctype === 'parabola') {
          var pp2 = pv.semi_a || 1, pa2 = pv.angle || 0;
          var pux = Math.cos(pa2), puy = Math.sin(pa2);
          var pvx = -puy, pvy = pux;
          var pspan = Math.max(Math.abs(view.xmax - view.xmin), Math.abs(view.ymax - view.ymin));
          var ptm = Math.sqrt(pspan * pp2 * 4) * 1.6;
          for (var pti = -120; pti <= 120; pti++) {
            var pt = pti * ptm / 120;
            var pxx = pv.cx + pt * pvx + pt * pt / (4 * pp2) * pux;
            var pyy = pv.cy + pt * pvy + pt * pt / (4 * pp2) * puy;
            if (pti === -120) ctx.moveTo(sxp(pxx), syp(pyy)); else ctx.lineTo(sxp(pxx), syp(pyy));
          }
        }
      } else if (toolPreview.type === 'conic5' && toolPreview.preSegs && toolPreview.preSegs.length) {
        for (var cv = 0; cv < toolPreview.preSegs.length; cv++) {
          var cvS = toolPreview.preSegs[cv];
          ctx.moveTo(sxp(cvS[0]), syp(cvS[1]));
          ctx.lineTo(sxp(cvS[2]), syp(cvS[3]));
        }
      }
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.restore();
    }
    if (marquee) {
      // 框选矩形预览
      var mx = Math.min(marquee.x0, marquee.x1), my = Math.min(marquee.y0, marquee.y1);
      var mw = Math.abs(marquee.x1 - marquee.x0), mh = Math.abs(marquee.y1 - marquee.y0);
      ctx.fillStyle = 'rgba(37,99,235,.12)';
      ctx.fillRect(mx, my, mw, mh);
      ctx.strokeStyle = '#2563eb';
      ctx.lineWidth = 1;
      ctx.strokeRect(mx, my, mw, mh);
    }
    if (hoverTip) {
      var hx = sxp(hoverTip.x), hy = syp(hoverTip.y);
      var htxt = tipText(hoverTip);
      // 关键：提示文本必须自己设定 textAlign/textBaseline。画布上其它元素绘制后会残留
      // 文本状态（如 'top'/'bottom'），沿用它的结果就是文字偏出提示框一半（看起来"只露一半"）。
      ctx.save();
      ctx.font = '12px sans-serif';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'alphabetic';
      var hMet = ctx.measureText(htxt);
      // 用实测 ascent/descent 让"文字墨迹"垂直居中（含 () , 等下伸部），而不是靠 em 框中线
      var hAsc = hMet.actualBoundingBoxAscent || 9;
      var hDesc = hMet.actualBoundingBoxDescent || 3;
      var hw = Math.ceil(hMet.width) + 16;
      var hh = Math.ceil(hAsc + hDesc) + 6;   // 框高 = 墨迹高度 + 上下各 3px 留白 → 文字填满提示框
      var hBase = 0;                          // 基线位置在定位后按框计算
      var gap = 14;
      // 优先放在光标上方（避免遮住对象本身），并始终夹在"可见可用区"内：
      // 顶部放不下 → 翻到下方；下方也放不下（含被面板遮挡）→ 向上顶到可见区上沿
      var area = usableCanvasRect();
      var tx = hx + gap;
      var ty = hy - gap - hh;
      if (tx + hw > area.right) tx = hx - gap - hw;           // 右侧放不下 → 移到左侧
      if (ty < area.top) ty = hy + gap;                        // 上方放不下 → 移到下方
      if (ty + hh > area.bottom) ty = hy - gap - hh;           // 下方放不下 → 回到上方
      tx = Math.max(area.left, Math.min(tx, Math.max(area.left, area.right - hw)));
      ty = Math.max(area.top, Math.min(ty, Math.max(area.top, area.bottom - hh)));
      ctx.fillStyle = C.tipBg;
      ctx.fillRect(tx, ty, hw, hh);
      ctx.fillStyle = C.tipFg;
      hBase = ty + (hh - (hAsc + hDesc)) / 2 + hAsc;          // 墨迹垂直居中（原固定 ty+14，偏低半框）
      ctx.fillText(htxt, tx + 8, hBase);
      dbgTipRect = { x: Math.round(tx), y: Math.round(ty), w: Math.round(hw), h: hh };
      ctx.restore();
    } else {
      dbgTipRect = null;
    }
    renderList();
    populateEditBar();
  }

  // ---------- 统计图绘制（统一 offset 平移 + 拖拽命中盒） ----------
  // 每张统计图都可作为一个整体在平面上移动：offset 是它的世界坐标偏移，
  // 绘制时整体平移（ctx.translate），拖动时只改 offset（与图内数据无关）。
  var chartBoxes = {};
  var widgetBoxes = {};      // 交互控件（按钮/复选框/输入框）的屏幕命中框                    // label → 屏幕包围盒（整体拖动命中用）
  var PIE_PAL = ['#ef4444', '#3b82f6', '#f59e0b', '#10b981', '#8b5cf6', '#06b6d4', '#f97316', '#ec4899', '#84cc16', '#64748b'];




  // ---------- 统计图工具：点击画布 → 输入数据 → 生成图 ----------
  function isChartTool(name) {
    return !!CHART_TOOL_CMD[name] || name === 'histogram' || name === 'scatterplot' ||
           name === 'scatterplot3d' || name === 'surfacechart3d';
  }

  var CHART_TOOL_CMD = {
    barchart: 'BarChart', boxplot: 'BoxPlot', piechart: 'PieChart',
    linechart: 'LineChart', dotplot: 'DotPlot', stemplot: 'StemPlot', barchart3d: 'BarChart3D'
  };


  function chartToolPrompt(tool) {
    var zhTitle = {
      barchart: '数据（逗号分隔，如 1,2,2,3,3）：', histogram: '数据（逗号分隔）：',
      boxplot: '数据（逗号分隔）：', piechart: '各部分数值（逗号分隔，如 3,5,2）：',
      linechart: '数据（逗号分隔，按顺序连线）：', dotplot: '数据（逗号分隔，相同值叠点）：',
      stemplot: '数据（非负，逗号分隔，如 12,15,23）：',
      scatterplot: '点（如 1,2; 3,4; 5,3）：', barchart3d: '数据（逗号分隔）→ 三维柱状图：',
      scatterplot3d: '三维点（如 1,2,3; 4,5,6）：', surfacechart3d: '数值（逗号分隔）：'
    }[tool] || '数据（逗号分隔）：';
    var enTitle = {
      barchart: 'Data (comma separated, e.g. 1,2,2,3,3):', histogram: 'Data (comma separated):',
      boxplot: 'Data (comma separated):', piechart: 'Part values (comma separated, e.g. 3,5,2):',
      linechart: 'Data (comma separated, connected in order):', dotplot: 'Data (comma separated, repeats stack):',
      stemplot: 'Data (non-negative, comma separated, e.g. 12,15,23):',
      scatterplot: 'Points (e.g. 1,2; 3,4; 5,3):', barchart3d: 'Data (comma separated) → 3D bar chart:',
      scatterplot3d: '3D points (e.g. 1,2,3; 4,5,6):', surfacechart3d: 'Values (comma separated):'
    }[tool] || 'Data (comma separated):';
    var title = lang === 'en' ? enTitle : zhTitle;
    var msgInvalid = lang === 'en' ? 'Invalid data' : '无效数据';

    // 散点图 / 三维散点图：按分号分组
    if (tool === 'scatterplot' || tool === 'scatterplot3d') {
      var raw = prompt(title, '');
      if (raw === null || !raw.trim()) { resetTool(); return; }
      var dim = tool === 'scatterplot' ? 2 : 3;
      var groups = raw.replace(/\(/g, '').replace(/\)/g, '').split(/[;；\n]+/)
                      .map(function (g) { return g.trim(); }).filter(Boolean);
      var pts = [];
      for (var gi = 0; gi < groups.length; gi++) {
        var nums = groups[gi].split(/[,，\s]+/).map(function (v) { return parseFloat(v); });
        if (nums.length < dim || nums.slice(0, dim).some(function (v) { return isNaN(v); })) { pts = null; break; }
        pts.push('(' + nums.slice(0, dim).join(',') + ')');
      }
      if (!pts || !pts.length) { setMsg(msgInvalid, true); resetTool(); return; }
      var scCmd = (tool === 'scatterplot' ? 'ScatterPlot[{' : 'ScatterPlot3D[{') + pts.join(',') + '}]';
      postInput(scCmd, function (ok) { if (ok) resetTool(); });
      return;
    }

    var data = chartDataPrompt(title, '');
    if (data === null) { resetTool(); return; }
    if (data === '') { setMsg(msgInvalid, true); resetTool(); return; }

    var cmd = null;
    if (tool === 'histogram') {
      var binsTxt = prompt(lang === 'en' ? 'Bins (blank = auto):' : '组数（留空自动）：', '');
      var bins = binsTxt === null ? 0 : parseInt(binsTxt, 10);
      cmd = 'Histogram[{' + data.join(',') + '}' + (bins > 1 ? ',' + bins : '') + ']';
    } else if (tool === 'surfacechart3d') {
      var colTxt = prompt(lang === 'en' ? 'Column count:' : '列数：', '3');
      var cols = colTxt === null ? 3 : parseInt(colTxt, 10);
      if (!(cols >= 2)) { setMsg(msgInvalid, true); resetTool(); return; }
      cmd = 'SurfaceChart3D[{' + data.join(',') + '},' + cols + ']';
    } else {
      cmd = CHART_TOOL_CMD[tool] + '[{' + data.join(',') + '}]';
    }
    postInput(cmd, function (ok) { if (ok) resetTool(); });
  }









  // 圆锥曲线的世界坐标折线（命中测试用；与 drawConic 参数化一致）




  // 滑块播放动画（点击 ▶ 自动递增参数，依赖曲线实时联动）
  var playState = null;
  var anim = { ms: 90, dir: 'up' };     // 动画设置：步间隔(ms)、方向 up / down / bounce
  // 播放状态：多个滑块**共用一个定时器** → 真正同步；labels[label] 记录各自当前方向
  function isPlaying(label) { return !!(playState && playState.labels[label]); }
  function playingLabels() { return playState ? Object.keys(playState.labels) : []; }
  function sliderLabels() {
    var out = [];
    for (var i = 0; i < elements.length; i++) {
      var e = elements[i];
      if (e.kind === 'number' && e.min !== null && e.min !== undefined) out.push(e.label);
    }
    return out;
  }
  function stopPlay() {
    if (playState) { clearInterval(playState.timer); playState = null; }
  }
  function startPlay(labels) {
    var map = {};
    for (var i = 0; i < labels.length; i++) map[labels[i]] = (anim.dir === 'bounce') ? 'up' : anim.dir;
    if (!Object.keys(map).length) return;
    stopPlay();
    playState = { labels: map, timer: setInterval(animTick, anim.ms) };
  }
  function animTick() {
    if (!playState) return;
    var labs = Object.keys(playState.labels), alive = 0;
    for (var i = 0; i < labs.length; i++) {
      var L = labs[i], el = null;
      for (var j = 0; j < elements.length; j++) {
        if (elements[j].label === L && elements[j].min !== undefined) el = elements[j];
      }
      if (!el) { delete playState.labels[L]; continue; }     // 对象已删除 → 退出该滑块
      alive++;
      var step = el.step > 0 ? el.step : 0;
      var v = el.val + (playState.labels[L] === 'down' ? -step : step);
      if (v > el.max + COORD) {
        if (anim.dir === 'bounce') { playState.labels[L] = 'down'; v = el.max - step; }
        else v = el.min;
      } else if (v < el.min - COORD) {
        if (anim.dir === 'bounce') { playState.labels[L] = 'up'; v = el.min + step; }
        else v = el.max;
      }
      api('POST', '/api/drag', { label: L, x: v, y: 0, push: false }, function (d) {
        if (d && d.elements) { elements = d.elements; render(); }
      });
    }
    if (!alive) { stopPlay(); render(); }
  }
  function playToggle(label) {                    // 在播则退出，未播则加入（与在播的同步）
    if (!playState) { startPlay([label]); return; }
    if (playState.labels[label]) {
      delete playState.labels[label];
      if (!Object.keys(playState.labels).length) stopPlay();
    } else {
      playState.labels[label] = (anim.dir === 'bounce') ? 'up' : anim.dir;
      clearInterval(playState.timer);
      playState.timer = setInterval(animTick, anim.ms);
    }
  }
  function sliderPlay(label) { playToggle(label); render(); }


  // 对象列表行拖拽重排（Z 叠放顺序）：仅通过行首 ⠿ 手柄拖拽
  var dragLabel = null;
  function clearDragCls() {
    var rows = listEl.querySelectorAll('.obj');
    for (var di = 0; di < rows.length; di++) rows[di].classList.remove('drag-src', 'drag-over');
  }
  listEl.addEventListener('dragstart', function (ev) {
    var dh = ev.target.closest('.dh');
    var row = dh ? ev.target.closest('.obj') : null;
    if (!row) return;
    dragLabel = row.getAttribute('data-label');
    if (ev.dataTransfer) ev.dataTransfer.setData('text/plain', dragLabel);
    row.classList.add('drag-src');
  });
  listEl.addEventListener('dragover', function (ev) {
    var row = ev.target.closest('.obj');
    if (dragLabel && row && row.getAttribute('data-label') !== dragLabel) ev.preventDefault();
  });
  listEl.addEventListener('drop', function (ev) {
    ev.preventDefault();
    clearDragCls();
    var target = ev.target.closest('.obj');
    if (!dragLabel || !target) { dragLabel = null; return; }
    var tl = target.getAttribute('data-label');
    var src = dragLabel;
    dragLabel = null;
    if (src === tl) return;
    var cur = elements.map(function (e2) { return e2.label; });
    var from = cur.indexOf(src), to = cur.indexOf(tl);
    if (from === -1 || to === -1 || from === to) return;
    cur.splice(from, 1);
    cur.splice(to, 0, src);
    api('POST', '/api/reorder', { order: cur, xmin: view.xmin, xmax: view.xmax, ymin: view.ymin, ymax: view.ymax }, function (d) {
      if (d && d.elements) { elements = d.elements; render(); renderList(); }
      else setMsg((d && d.message) || '调整顺序失败', true);
    });
  });
  listEl.addEventListener('dragend', function () { dragLabel = null; clearDragCls(); });
  listEl.addEventListener('dragleave', function (ev) {
    var row = ev.target.closest('.obj');
    if (row) row.classList.remove('drag-over');
  });

  // ---------- 命中检测 ----------
  function hitFreePoint(sx, sy) {
    for (var i = 0; i < elements.length; i++) {
      var e = elements[i];
      if (e.kind !== 'point' || !e.free) continue;
      var dx = sxp(e.x) - sx, dy = syp(e.y) - sy;
      if (dx * dx + dy * dy <= 64) return e.label;
    }
    return null;
  }

  // 悬停提示：检测最近的点/圆
  // 提示文案：点 → 名称 = (x, y)；圆/圆弧 → 名称 r=半径；其它对象属性太多 → 只显示名称
  function tipText(t) {
    if (t.nameOnly) return t.label;
    if (t.r != null) return t.label + ' r=' + fmtNum(t.r);
    return t.label + ' = (' + fmtNum(t.x) + ', ' + fmtNum(t.y) + ')';
  }

  // 会显示"仅名称"提示的对象类型（复用已有的 hitObject 命中检测）
  var CHART_KINDS = ['barchart', 'histogram', 'boxplot', 'piechart', 'linechart', 'scatterplot', 'dotplot', 'stemplot'];
  var TIP_NAME_KINDS = ['segment', 'line', 'ray', 'vector', 'polygon', 'polyline', 'function',
                        'parametric', 'polar', 'implicit', 'conic', 'image'].concat(CHART_KINDS);

  function hitForTip(sx, sy) {
    for (var i = 0; i < elements.length; i++) {
      var e = elements[i];
      if (e.kind !== 'point' || e.z !== undefined) continue;
      var dx = sxp(e.x) - sx, dy = syp(e.y) - sy;
      if (dx * dx + dy * dy <= 81) return { label: e.label, x: e.x, y: e.y, r: null };
    }
    for (var j = 0; j < elements.length; j++) {
      var e2 = elements[j];
      if (e2.kind !== 'circle' && e2.kind !== 'arc') continue;
      var dx2 = sxp(e2.cx) - sx, dy2 = syp(e2.cy) - sy;
      var d = Math.sqrt(dx2 * dx2 + dy2 * dy2) || 1;
      var rr = Math.max(2, e2.r * scale);
      if (Math.abs(d - rr) <= 6) {
        // dx2/dy2 是「圆心→光标」的屏幕向量：换算回世界坐标时 x 取负、y 取正（屏幕 y 轴向下），
        // 这样提示锚点才落在圆上离光标最近的一侧（此前两个符号都反了 → 提示跑到对侧、看起来偏低）
        return { label: e2.label, x: e2.cx - e2.r * (dx2 / d), y: e2.cy + e2.r * (dy2 / d), r: e2.r };
      }
    }
    // 其它几何对象（直线/线段/多边形/函数/圆锥曲线/图片…）：属性太多，只提示名称
    var other = hitObject(sx, sy, TIP_NAME_KINDS);
    if (other) return { label: other, nameOnly: true, x: wxp(sx), y: wyp(sy) };
    return null;
  }

  // ---------- 交互 ----------
  canvas.addEventListener('pointerdown', function (ev) {
    ev.preventDefault();
    // 画布交互自动停止播放；但点在滑块右侧 ▶/⏸ 上时不先停（否则切换会变成「先停再启」）
    if (playState && !sliderPlayAt(ev.offsetX, ev.offsetY)) { clearInterval(playState.timer); playState = null; render(); }
    // 控件优先：按下先记录，抬起时若未移动才执行动作（移动则视为拖动位置）
    var _wEl = widgetHit(ev.offsetX, ev.offsetY);
    if (_wEl) {
      drag = { label: _wEl.label, widget: true, moved: false, downX: ev.offsetX, downY: ev.offsetY,
               grabX: wxp(ev.offsetX), grabY: wyp(ev.offsetY), pos0: [_wEl.x || 0, _wEl.y || 0] };
      dragPending = false;
      canvas.style.cursor = 'move';
      capturePointer(ev);
      return;
    }
    if (activeTool) { toolPreview = null; toolCanvasClick(ev.offsetX, ev.offsetY); return; }
    hoverTip = null;
    touches[ev.pointerId] = { x: ev.offsetX, y: ev.offsetY };
    if (Object.keys(touches).length >= 2) {
      // 第二指落下：取消拖拽/平移，进入双指捏合缩放
      drag = null; pan = null; canvas.style.cursor = 'default';
      var tids = Object.keys(touches);
      var a = touches[tids[0]], b = touches[tids[1]];
      pinch = {
        d0: Math.max(1, Math.hypot(a.x - b.x, a.y - b.y)),
        s0: scale,
        cx: wxp((a.x + b.x) / 2),
        cy: wyp((a.y + b.y) / 2)
      };
      capturePointer(ev);
      return;
    }
    var sx = ev.offsetX, sy = ev.offsetY;
    // 宏点选模式：点击画布对象 → 加入输入/输出框
    if (macroPickMode) {
      var pkHit = hitAnyPoint(sx, sy) || hitObject(sx, sy, ['segment', 'circle', 'line', 'polygon', 'arc', 'text', 'vector', 'ray', 'conic', 'function']);
      if (pkHit) handleMacroPick(pkHit);
      return;
    }
    var playHit = sliderPlayAt(sx, sy);          // 滑块右侧 ▶/⏸：点击切换播放
    if (playHit && !selectMode) {
      ev.preventDefault();
      sliderPlay(playHit);
      return;
    }
    var sldHit = sliderAt(sx, sy);
    if (sldHit && !selectMode && !addSelModifier(ev)) {
      var _sb = widgetBoxes[sldHit] || {};
      // 是否抓在滑钮上必须**按轴判断**：竖直滑块轨道是竖线，用 x 距离会把轨道上任何一点
      // 都判成滑钮 → 整条滑块永远移不动（用户报告「竖直 slider 不能移动」的根因）
      var _onKnob = (_sb.axis === 'y')
        ? (typeof _sb.knobY === 'number' && Math.abs(sy - _sb.knobY) <= 12)
        : (typeof _sb.knobX === 'number' && Math.abs(sx - _sb.knobX) <= 12);
      if (_onKnob) {
        drag = { label: sldHit, slider: true };
        canvas.style.cursor = 'ew-resize';
        api('POST', '/api/drag', { label: sldHit, x: sliderValueAt(sldHit, sx, sy), y: 0, push: true }, function () {});
      } else {
        // 拖轨道 = 移动整条滑块（锚点）
        drag = { label: sldHit, sliderPos: true, grabX: wxp(sx), grabY: wyp(sy),
                 pos0: [_sb.wx0 || 0, _sb.wy0 || 0] };
        canvas.style.cursor = 'move';
      }
      dragPending = false;
      capturePointer(ev);
      return;
    }
    var label = hitFreePoint(sx, sy);
    var chartHit = label ? null : chartAt(sx, sy);
    if (chartHit && !selectMode && !addSelModifier(ev)) {
      // 统计图：整张图作为一个对象拖动 —— 记录起手时的世界坐标与当前 offset
      var chEl = null;
      for (var ci = 0; ci < elements.length; ci++) if (elements[ci].label === chartHit) { chEl = elements[ci]; break; }
      var chOff = (chEl && chEl.offset) || [0, 0];
      drag = { label: chartHit, chart: true, off0: [chOff[0] || 0, chOff[1] || 0],
               grab: [wxp(sx), wyp(sy)] };
      dragPending = false;
      canvas.style.cursor = 'grabbing';
      return;
    }
    if (label && !selectMode && !addSelModifier(ev)) {
      drag = { label: label };
      dragPending = false;
      canvas.style.cursor = 'grabbing';
    } else {
      var selHit = hitAnyPoint(sx, sy) || hitObject(sx, sy, ['segment', 'circle', 'line', 'polygon', 'arc', 'text', 'vector', 'ray', 'image'].concat(CHART_KINDS));
      if (selHit && (selHit === selected || selectedMulti.indexOf(selHit) !== -1) && !addSelModifier(ev)) {
        // 选中对象整体拖动；动点（PointOnPath/PointOnCircle）改为沿母体移动
        var _selEl = null;
        for (var _si = 0; _si < elements.length; _si++) if (elements[_si].label === selHit) { _selEl = elements[_si]; break; }
        var _isPath = _selEl && _selEl.kind === 'point' && /PointOn(?:Path|Circle)\[/.test(_selEl.defn || '');
        shiftDrag = { label: selHit, sx: sx, sy: sy, pushed: false, moved: false, downX: sx, downY: sy, pathPoint: _isPath };
        shiftAccum.dx = 0; shiftAccum.dy = 0;
        canvas.style.cursor = 'grabbing';
        capturePointer(ev);
        return;
      }
      if (selHit) {
        // 点击未选中对象：不平移，交给选择 handler 选中
        canvas.style.cursor = 'default';
        return;
      }
      if (selectMode) {
        // 选择模式下空白按下：进入框选（marquee），松开批量选中与框相交的对象
        if (marquee) return;
        marquee = { x0: sx, y0: sy, x1: sx, y1: sy, add: addSelModifier(ev) };
        canvas.style.cursor = 'crosshair';
        capturePointer(ev);
        return;
      }
      pan = { sx: sx, sy: sy, xmin: view.xmin, ymin: view.ymin };
      canvas.style.cursor = 'grabbing';
    }
    capturePointer(ev);
  });

  var snapOn = false;
  var shiftKeyPressed = false;   // 工具点击时的临时 Shift 吸附（与拖拽路径的 ev.shiftKey 一致）
  document.addEventListener('keydown', function (ev) { if (ev.key === 'Shift') shiftKeyPressed = true; });
  document.addEventListener('keyup', function (ev) { if (ev.key === 'Shift') shiftKeyPressed = false; });
  btn('btn-snap', function () {
    snapOn = !snapOn;
    this.classList.toggle('active', snapOn);
    setMsg(snapOn ? t('snapOn') : t('snapOff'), false);
  });

  // 智能吸附：优先吸附到已有点（对象吸附，12px 阈值），否则吸附到网格交点
  function snapPoint(wx, wy, step, sx, sy) {
    if (sx !== undefined && sy !== undefined) {
      var best = null, bestD = 12 / scale;   // 12px -> 世界单位
      for (var si = 0; si < elements.length; si++) {
        var se = elements[si];
        if (se.kind !== 'point' || se.visible === false) continue;
        var d = Math.hypot(se.x - wx, se.y - wy);
        if (d < bestD) { bestD = d; best = [se.x, se.y]; }
      }
      if (best) return best;
    }
    return [Math.round(wx / step) * step, Math.round(wy / step) * step];
  }

  canvas.addEventListener('pointermove', function (ev) {
    if (touches[ev.pointerId]) touches[ev.pointerId] = { x: ev.offsetX, y: ev.offsetY };
    if (marquee) {
      marquee.x1 = ev.offsetX; marquee.y1 = ev.offsetY;
      render();
      return;
    }
    if (shiftDrag) {
      if (!shiftDrag.moved && (Math.abs(ev.offsetX - shiftDrag.downX) > 3 || Math.abs(ev.offsetY - shiftDrag.downY) > 3)) {
        shiftDrag.moved = true;
      }
      if (!shiftDrag.moved) return;
      if (shiftDrag.pathPoint) {
        // 动点：拖动 → 沿母体对象移动（更新参数滑块）
        var pwx = wxp(ev.offsetX), pwy = wyp(ev.offsetY);
        dragPathPoint(shiftDrag.label, pwx, pwy);
        return;
      }
      var ddx = ev.offsetX - shiftDrag.sx, ddy = ev.offsetY - shiftDrag.sy;
      shiftDrag.sx = ev.offsetX; shiftDrag.sy = ev.offsetY;
      var wdx = ddx / scale, wdy = -ddy / scale;
      shiftAccum.dx += wdx; shiftAccum.dy += wdy;
      shiftLocal(shiftDrag.label, wdx, wdy);
      if (!shiftPending) {
        shiftPending = true;
        var sentDx = shiftAccum.dx, sentDy = shiftAccum.dy;
        api('POST', '/api/shift', {
          label: shiftDrag.label, dx: sentDx, dy: sentDy,
          push: !shiftDrag.pushed,
          xmin: view.xmin, xmax: view.xmax, ymin: view.ymin, ymax: view.ymax
        }, function (d) {
          shiftPending = false;
          shiftDrag.pushed = true;
          shiftAccum.dx -= sentDx; shiftAccum.dy -= sentDy;
          if (d && d.elements) {
            elements = d.elements;
            // 重新应用提交期间累积的新位移，避免回跳
            if (shiftAccum.dx || shiftAccum.dy) shiftLocal(shiftDrag.label, shiftAccum.dx, shiftAccum.dy);
            else render();
          }
        });
      }
      return;
    }
    if (pinch) {
      var tids = Object.keys(touches);
      if (tids.length >= 2) {
        var a = touches[tids[0]], b = touches[tids[1]];
        var d = Math.max(1, Math.hypot(a.x - b.x, a.y - b.y));
        scale = Math.max(2, Math.min(200000, pinch.s0 * (d / pinch.d0)));
        var mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
        view.xmin = pinch.cx - mx / scale;
        view.xmax = view.xmin + cssW / scale;
        view.ymin = pinch.cy - (cssH - my) / scale;
        view.ymax = view.ymin + cssH / scale;
        render();
      }
      return;
    }
    if (drag && (drag.sliderPos || drag.widget)) {
      if (drag.widget && !drag.moved
          && Math.abs(ev.offsetX - drag.downX) < 4 && Math.abs(ev.offsetY - drag.downY) < 4) return;
      drag.moved = true;
      var _dEl = findEl(drag.label);
      if (_dEl) {
        var _nx = drag.pos0[0] + (wxp(ev.offsetX) - drag.grabX);
        var _ny = drag.pos0[1] + (wyp(ev.offsetY) - drag.grabY);
        if (drag.sliderPos) { _dEl.slider_x = _nx; _dEl.slider_y = _ny; }
        else { _dEl.x = _nx; _dEl.y = _ny; }
        render();
      }
      return;
    }
    if (drag && drag.slider) {
      var _sv = sliderValueAt(drag.label, ev.offsetX, ev.offsetY);
      api('POST', '/api/drag', { label: drag.label, x: _sv, y: 0, push: false }, function (d) {
        if (d && d.elements) { elements = d.elements; render(); }
      });
      return;
    }
    if (drag) {
      var first = !drag.started;
      drag.started = true;
      var wx = wxp(ev.offsetX), wy = wyp(ev.offsetY);
      if (snapOn || ev.shiftKey) {
        var snapped = snapPoint(wx, wy, niceStep(), ev.offsetX, ev.offsetY);
        wx = snapped[0];
        wy = snapped[1];
      }
      if (drag.chart) {
        // 图表整体平移：新 offset = 起手 offset + 光标位移（世界坐标）
        wx = drag.off0[0] + (wx - drag.grab[0]);
        wy = drag.off0[1] + (wy - drag.grab[1]);
        for (var ci2 = 0; ci2 < elements.length; ci2++) {
          if (elements[ci2].label === drag.label) { elements[ci2].offset = [wx, wy]; break; }
        }
        render();
        if (!dragPending) {
          dragPending = true;
          api('POST', '/api/drag', {
            label: drag.label, x: wx, y: wy,
            xmin: view.xmin, xmax: view.xmax, ymin: view.ymin, ymax: view.ymax,
            push: first
          }, function (d) {
            dragPending = false;
            if (d && d.elements) { elements = d.elements; render(); }
            if (d && d.message && !d.ok) setMsg(d.message, true);
          });
        }
        return;
      }
      // 本地乐观更新
      for (var i = 0; i < elements.length; i++) {
        if (elements[i].label === drag.label && elements[i].kind === 'point') {
          elements[i].x = wx;
          elements[i].y = wy;
        }
      }
      render();
      if (!dragPending) {
        dragPending = true;
        lastDrag = { label: drag.label, x: wx, y: wy };
        api('POST', '/api/drag', {
          label: drag.label, x: wx, y: wy,
          xmin: view.xmin, xmax: view.xmax, ymin: view.ymin, ymax: view.ymax,
          push: first
        }, function (d) {
          dragPending = false;
          if (d && d.elements) { elements = d.elements; render(); }
          if (d && d.message && !d.ok) setMsg(d.message, true);
        });
      }
    } else if (pan) {
      var dx = ev.offsetX - pan.sx, dy = ev.offsetY - pan.sy;
      view.xmin = pan.xmin - dx / scale;
      view.xmax = view.xmin + cssW / scale;
      view.ymin = pan.ymin + dy / scale;
      view.ymax = view.ymin + cssH / scale;
      render();
    } else {
      // 悬停坐标提示 + 工具动态预览（无拖拽/平移/捏合时）
      var tip = hitForTip(ev.offsetX, ev.offsetY);
      if (tip !== hoverTip) { hoverTip = tip; render(); }
      if (activeTool) {
        var prev2 = computeToolPreview(toolSel, ev.offsetX, ev.offsetY);
        var prevKey = prev2 ? JSON.stringify(prev2) : null;
        var curKey = toolPreview ? JSON.stringify(toolPreview) : null;
        if (prevKey !== curKey) { toolPreview = prev2; render(); }
      }
    }
  });

  // 双击控件：就地编辑说明（按钮再编辑脚本）——对象列表的「重定义」栏是另一条路径
  // 滑块范围编辑器（⚙ 按钮与双击共用）：SetSlider 会保留当前值、越界夹紧、按步长吸附
  function editSliderRange(label) {
    var el = findEl(label);
    if (!el || el.min === null || el.min === undefined) return;
    var sv = prompt(t('widgetEditSlider'), el.min + ',' + el.max + ',' + el.step);
    if (sv === null) return;
    var sp = String(sv).split(',');
    if (sp.length < 2 || !String(sp[0]).trim() || !String(sp[1]).trim()) {
      setMsg(t('widgetEditSliderBad'), true);
      return;
    }
    postInput('SetSlider[' + el.label + ',' + sp[0].trim() + ',' + sp[1].trim()
              + (sp[2] && String(sp[2]).trim() ? ',' + sp[2].trim() : '') + ']',
              function () { loadState(); });
  }

  function editWidget(el) {
    if (!el) return;
    if (el.kind === 'number' && el.min !== null && el.min !== undefined) {
      editSliderRange(el.label);
      return;
    }
    var cap = prompt(t('widgetEditCaption'), el.caption || '');
    if (cap === null) return;
    postInput('SetCaption[' + el.label + ',"' + String(cap).replace(/"/g, "'") + '"]', function (ok) {
      if (!ok || el.kind !== 'button') { loadState(); return; }
      var sc = prompt(t('widgetEditScript'), el.script || '');
      if (sc === null) { loadState(); return; }
      postInput('SetScript[' + el.label + ',"' + String(sc).replace(/"/g, "'") + '"]',
                function () { loadState(); });
    });
  }
  canvas.addEventListener('dblclick', function (ev) {
    var el = widgetHit(ev.offsetX, ev.offsetY);          // 按钮/复选框/输入框
    if (!el) {
      var sLabel = sliderAt(ev.offsetX, ev.offsetY);     // 滑动条（改范围/步长）
      if (sLabel) el = findEl(sLabel);
    }
    if (el) editWidget(el);
  });

  // 指针被取消（系统手势/掌拒/切窗）时必须清理，否则 touches 残留 → 之后单指操作会被误判为双指捏合
  // 指针捕获是**尽力而为**：真实指针能成功；合成事件或已失活指针会抛 DOMException，
  // 若任其抛出会中断整个 pointerdown 处理函数（历史上导致"拖动无反应"且难定位）。
  function capturePointer(ev) {
    // 注意：这里必须调 canvas.setPointerCapture —— 曾误写成自递归 capturePointer(ev)，
    // 递归到栈溢出被自身 try 吞掉 → 指针捕获**静默失效**（拖动出画布就丢事件）✗
    try { canvas.setPointerCapture(ev.pointerId); } catch (e) { /* 捕获失败不致命：继续处理 */ }
  }

  function dropPointer(ev) {
    delete touches[ev.pointerId];
    if (pinch && Object.keys(touches).length < 2) { pinch = null; loadState(); }
    if (pan) { pan = null; canvas.style.cursor = 'default'; }
  }
  canvas.addEventListener('pointercancel', dropPointer);
  canvas.addEventListener('lostpointercapture', function (ev) { if (!touches[ev.pointerId]) return; dropPointer(ev); });

  canvas.addEventListener('pointerup', function (ev) {
    delete touches[ev.pointerId];
    if (pinch) {
      if (Object.keys(touches).length < 2) { pinch = null; loadState(); }
      return;
    }
    if (pan) {
      pan = null;
      canvas.style.cursor = 'default';
      loadState();
    } else if (drag) {
      var _d = drag;
      drag = null;
      dragPending = false;
      canvas.style.cursor = 'default';
      if (_d.widget && !_d.moved) {
        widgetAct(_d.label);                 // 未移动 → 执行控件动作
      } else if (_d.widget || _d.sliderPos) {
        var _pEl = findEl(_d.label);
        var _px = _d.sliderPos ? _pEl && _pEl.slider_x : _pEl && _pEl.x;
        var _py = _d.sliderPos ? _pEl && _pEl.slider_y : _pEl && _pEl.y;
        if (_pEl && _px !== undefined) {
          postInput('SetWidgetPos[' + _d.label + ',(' + Number(_px).toFixed(4) + ',' + Number(_py).toFixed(4) + ')]',
                    function () { loadState(); });
        } else {
          loadState();
        }
      } else {
        // 最后一次落点已随 move 提交
        loadState();
      }
    }
    if (marquee) {
      // 框选：与框接触的对象全部选中
      var mx0 = Math.min(marquee.x0, marquee.x1), mx1 = Math.max(marquee.x0, marquee.x1);
      var my0 = Math.min(marquee.y0, marquee.y1), my1 = Math.max(marquee.y0, marquee.y1);
      var boxLabels = [];
      var wm = wrect(mx0, my0, mx1, my1);
      for (var mi = 0; mi < elements.length; mi++) {
        if (boxHitEl(elements[mi], wm)) boxLabels.push(elements[mi].label);
      }
      var addMarquee = !!marquee.add;
      marquee = null;
      if (addMarquee) unionSelection(boxLabels);   // Ctrl+框选：并入现有选择
      else setManySelection(boxLabels);
      canvas.style.cursor = 'default';
      return;
    }
    if (shiftDrag) {
      var wasMoved = shiftDrag.moved;
      var sdLabel = shiftDrag.label;
      shiftDrag = null;
      shiftAccum.dx = 0; shiftAccum.dy = 0;
      canvas.style.cursor = 'default';
      if (!wasMoved) {
        if (selected) setSelected(null);                    // 单击已选单对象 → XOR 取消
        else if (selectedMulti.length) setSelected(sdLabel); // 多选中单击其一 → 塌缩为只选它
      }
      // 移动过的对象：elements 已随每次 /api/shift 提交同步，无需 loadState（避免异步期间点击用旧位置）
    }
    hoverTip = null;
  });
  canvas.addEventListener('pointercancel', function (ev) {
    delete touches[ev.pointerId];
    if (Object.keys(touches).length < 2) pinch = null;
    pan = null; drag = null; dragPending = false;
    marquee = null; shiftDrag = null;
    canvas.style.cursor = 'default';
    loadState();
  });

  canvas.addEventListener('wheel', function (ev) {
    ev.preventDefault();
    var factor = ev.deltaY < 0 ? 1.15 : 1 / 1.15;
    var sx = ev.offsetX, sy = ev.offsetY;
    var wx = wxp(sx), wy = wyp(sy);
    scale *= factor;
    scale = Math.max(2, Math.min(200000, scale));
    view.xmin = wx - sx / scale;
    view.xmax = view.xmin + cssW / scale;
    view.ymin = wy - (cssH - sy) / scale;
    view.ymax = view.ymin + cssH / scale;
    render();
    clearTimeout(canvas._zw);
    canvas._zw = setTimeout(loadState, 180);
  });

  // ---------- CAS 视图 ----------
  var casPanel = document.getElementById('cas-panel');
  var casCellsEl = document.getElementById('cas-cells');
  var casCmdEl = document.getElementById('cas-cmd');
  var casOpen = false;

  // CAS 支持的命令（界面命令面板：点击插入模板，光标停在括号内）
  var CAS_COMMANDS = GGB_DATA.CAS_COMMANDS || [];

  // 在 CAS 输入框光标处插入文本；caretBack 为从末尾回退的字符数
  function casInsert(text, caretBack) {
    if (!casCmdEl) return;
    var st = (casCmdEl.selectionStart != null) ? casCmdEl.selectionStart : casCmdEl.value.length;
    var en = (casCmdEl.selectionEnd != null) ? casCmdEl.selectionEnd : casCmdEl.value.length;
    var v = casCmdEl.value;
    casCmdEl.value = v.slice(0, st) + text + v.slice(en);
    var caret = st + text.length - (caretBack || 0);
    casCmdEl.focus();
    try { casCmdEl.setSelectionRange(caret, caret); } catch (e) {}
  }

  (function buildCasPalette() {
    var box = document.getElementById('cas-cmds');
    if (!box) return;
    var html = '';
    for (var i = 0; i < CAS_COMMANDS.length; i++) {
      var c = CAS_COMMANDS[i];
      html += '<button type="button" data-cas="' + c.name + '" title="' + esc(c.zh) + ' / ' + esc(c.en) + '">' + c.name + '</button>';
    }
    box.innerHTML = html;
    box.addEventListener('click', function (ev) {
      var b = ev.target.closest ? ev.target.closest('button[data-cas]') : null;
      if (!b) return;
      casInsert(b.getAttribute('data-cas') + '[]', 1);
    });
  })();


  function casEval() {
    var text = casCmdEl.value.trim();
    if (!text) return;
    api('POST', '/api/cas/eval', {
      text: text,
      xmin: view.xmin, xmax: view.xmax, ymin: view.ymin, ymax: view.ymax
    }, function (d) {
      renderCas(d.cells);
      if (d.state) { elements = d.state; render(); }
      setMsg(d.ok ? 'CAS: ' + text : 'CAS 错误', !d.ok);
      casCmdEl.value = '';
      if (d.ok && d.cell && d.cell.output) setMsg('CAS #' + d.cell.id + ' = ' + d.cell.output, false);
    });
  }

  casCmdEl.addEventListener('keydown', function (ev) {
    if (ev.key === 'Enter') casEval();
  });
  casCellsEl.addEventListener('click', function (ev) {
    var t = ev.target.closest ? ev.target.closest('.cid') : null;
    if (!t) return;
    casInsert('#' + t.getAttribute('data-ref'), 0);   // 点击 #N → 插入结果引用
  });
  document.getElementById('cas-go').addEventListener('click', casEval);
  btn('btn-cas', function () {
    casOpen = !casOpen;
    casPanel.style.display = casOpen ? 'flex' : 'none';
    if (casOpen) {
      api('GET', '/api/cas', null, function (d) { renderCas(d.cells); });
      casCmdEl.focus();
    }
  });

  // ---------- 3D 视图（自研透视投影 + 轨道控制） ----------
  var cv3d = document.getElementById('cv3d');
  var ctx3 = cv3d.getContext('2d');
  var mode3d = false;
  var els3d = [];
  var cam = { r: 14, theta: -0.55, phi: 0.6, tx: 0, ty: 0, tz: 0 };  // 右手系：x 右下、y 右上（纵深）、z 上（GeoGebra 视角）
  var view3dMode = 'oblique';   // oblique=标准3D(斜二测) | free=自由正交旋转 | top=俯视 | front=前视 | right=右视 | iso=透视等距
  var ortho3d = true;       // 正交投影标志（斜二测/free/俯/前/右 = 平行投影）
  var camDrag = null;
  var planeZ = 0;            // 3D 基准平面高度（三维取点 z）
  var tool3d = null;         // 3D 模式激活的工具
  var toolSel3d = [];        // 3D 工具已选点标签
  var drag3d = null;         // 3D 自由点拖动状态 { label, x0, y0, z0 }
  var drag3dObj = null;          // 3D 选中对象平移状态 { label, mode, zRef, lastX, lastY, lastSY, pushed }
  var objShift3d = { dx: 0, dy: 0, dz: 0, pending: false, pushed: false };
  var dragZHandle = null;    // z 控制柄拖动状态 { label, sy0, z0, handleScreenY }
  var selected3d = null;     // 3D 模式选中的对象标签
  // 3D 坐标轴刻度属性（可修改，localStorage 持久化）
  var axisTicks3d = { show: true, color: '#64748b', tickLen: 5, font: '10px sans-serif', labelColor: '#64748b' };
  try { var _at = JSON.parse(localStorage.getItem('ggb_axisticks3d') || '{}'); for (var _k in _at) axisTicks3d[_k] = _at[_k]; } catch (e) {}
  // 3D 轴刻度步长：随缩放（cam.r）实时匹配，目标 ~55px 一格

  function resize3d() {
    cv3d.width = Math.round(cssW * dpr);
    cv3d.height = Math.round(cssH * dpr);
    ctx3.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (mode3d) render3d();
  }

  // 3D 模式下任何构造变更后同步刷新 3D 视图与对象列表
  var dbgRefreshN = 0, dbgLoadN = 0, dbgLoadSkip = 0;
  function refresh3dIfNeeded() {
    dbgRefreshN++;
    if (mode3d) load3d();
  }

  // 3D 状态增量拉取：服务端按 rev 只回变化项，未变则跳过重绘（大网格 1–2 MB → 几十字节）
  var lastRev3d = -1;
  function load3d() {
    dbgLoadN++;
    fetch('/api/state3d?since=' + lastRev3d).then(function (r) { return r.json(); }).then(function (d) {
      if (!d) return;
      if (typeof d.rev === 'number') lastRev3d = d.rev;
      if (d.unchanged) return;
      if (d.elements) {
        els3d = d.elements;                       // 全量兜底（首次或 rev 过期）
      } else {
        var map = {}, order = [];
        for (var i = 0; i < els3d.length; i++) { map[els3d[i].label] = els3d[i]; order.push(els3d[i].label); }
        var ch = d.changed || [];
        for (var c = 0; c < ch.length; c++) {
          if (!(ch[c].label in map)) order.push(ch[c].label);
          map[ch[c].label] = ch[c];
        }
        var rm = d.removed || [];
        for (var r = 0; r < rm.length; r++) {
          delete map[rm[r]];
          order = order.filter(function (x) { return x !== rm[r]; });
        }
        els3d = order.filter(function (lab) { return map[lab]; }).map(function (lab) { return map[lab]; });
      }
      render3d();
      renderList3d();
    }).catch(function () {});
  }
  // 3D 对象类型名：优先 solid（具体立体：球/圆锥/圆柱/正十二面体…），回退 objtype

  // 3D 模式对象列表（点击选中 → 编辑栏可改色/显隐/锁定/删除）

  // GeoGebra 标准坐标系（右手系）：z 轴向上，x 右、y 纵深。
  // 使用 lookAt 相机（up = 世界 +z）：right = normalize(f×up)，up' = right×f，dir = -f。
  // 相机坐标 x_cam=d·right, y_cam=d·up', z_cam=d·dir（正=前方）；透视 s=F/(F+r+z_cam)
  // 视图基：iso 用 lookAt（右手，z 上）；top/front/right 用固定正交基（工程制图约定）
  // 斜二测（oblique）：高中数学标准画法——x 水平、y 右上 45° 且长度减半、z 竖直（正交投影，proj3 内特殊处理）

  // 逆投影：屏幕 (sx,sy) → 世界坐标，落在平面 z=z0 上（用于 3D 工具取点）
  // 透视：平面 z=z0 → y_cam·up[2]+z_cam·dir[2]=z0-tz；y_cam=v/s, z_cam=F/s-F-r → s=(v·cp+F·sp)/(z0-tz+(F+r)·sp)
  // 正交：s=1，由 z 约束直接解 z_cam


  // 3D 坐标轴：带箭头的彩色轴 + x/y/z 标签（原点不标记）；左下角微缩坐标轴指示器
  // 箭头：屏幕空间画法——方向 = base→tip 投影方向（保证朝外），尖在 tip，两翼向后张开
  // 左下角微缩坐标轴：用当前相机的旋转方向画三条短轴 + 标签（屏幕固定位置）
  // 大网格渲染预算：面数超限时只画面积最大的面（LOD，保轮廓），
  // 并跳过 O(边×面) 的 hidden-line 遮挡测试，避免等值面/参数曲面卡死。
  var dbgProjCalls = 0, dbgOccTests = 0, dbgLastFaces = 0, dbgLastSegs = 0, dbgProjReuse = 0;
  var MESH_FACE_BUDGET = 2000;
  var MESH_EDGE_BUDGET = 4000;
  var OCCLUSION_BUDGET = 150000;
  var meshFaceCache = {};
  function selectMeshFaces(el, verts, cfaces) {
    if (cfaces.length <= MESH_FACE_BUDGET) return cfaces;
    var key = el.label + '|' + cfaces.length + '|' + verts.length;
    if (meshFaceCache[key]) return meshFaceCache[key];
    var scored = [];
    for (var i = 0; i < cfaces.length; i++) {
      var f = cfaces[i];
      var a0 = verts[f[0]], A = 0;
      for (var k = 1; k < f.length - 1; k++) {
        var b = verts[f[k]], c2 = verts[f[k + 1]];
        var ux = b[0] - a0[0], uy = b[1] - a0[1], uz = b[2] - a0[2];
        var vx = c2[0] - a0[0], vy = c2[1] - a0[1], vz = c2[2] - a0[2];
        var nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
        A += 0.5 * Math.sqrt(nx * nx + ny * ny + nz * nz);
      }
      scored.push([A, i]);
    }
    scored.sort(function (p, q) { return q[0] - p[0]; });
    var sel = [];
    for (var m = 0; m < MESH_FACE_BUDGET && m < scored.length; m++) sel.push(cfaces[scored[m][1]]);
    meshFaceCache[key] = sel;
    return sel;
  }
  // 供检测脚本计时/取内部状态（只读，不影响交互）
  window.__ggbpyDebug = {
    render3d: function () { render3d(); },
    // 世界坐标 → 画布屏幕坐标（供检测/诊断定位悬停与标注位置）
    toScreen: function (x, y) { return { x: sxp(x), y: syp(y), scale: scale, cssW: cssW, cssH: cssH }; },
    hoverTip: function () {
      return hoverTip ? { label: hoverTip.label, x: hoverTip.x, y: hoverTip.y,
                          r: hoverTip.r == null ? null : hoverTip.r, nameOnly: !!hoverTip.nameOnly,
                          text: tipText(hoverTip) } : null;
    },
    tipRect: function () { return dbgTipRect; },
    tipArea: function () { return usableCanvasRect(); },
    tipColors: function () { return { bg: C.tipBg, fg: C.tipFg }; },
    chartBox: function (label) { return chartBoxes[label] || null; },
    selectMode: function () { return !!selectMode; },
    chartBoxes: function () { return chartBoxes; },
    widgetBoxes: function () { return widgetBoxes; },
    playLabel: function () { return playingLabels()[0] || null; },
    playingLabels: function () { return playingLabels(); },
    touchState: function () { return { count: Object.keys(touches).length, ids: Object.keys(touches), pinch: !!pinch, pan: !!pan }; },
    animState: function () {
      var dirs = {};
      if (playState) { var ks = Object.keys(playState.labels); for (var i = 0; i < ks.length; i++) dirs[ks[i]] = playState.labels[ks[i]]; }
      return { ms: anim.ms, dir: anim.dir, dirs: dirs };
    },
    playAt: function (sx, sy) { return sliderPlayAt(sx, sy); },
    sliderAt: function (sx, sy) { return sliderAt(sx, sy); },
    dragState: function () { return drag ? { label: drag.label, slider: !!drag.slider, chart: !!drag.chart } : null; },
    sliderValue: function (label, wx) { return sliderValueAt(label, wx); },
    faceBudget: function () { return MESH_FACE_BUDGET; },
    cacheSize: function () { return Object.keys(meshFaceCache).length; },
    projCalls: function () { return dbgProjCalls; },
    projReuse: function () { return dbgProjReuse; },
    occTests: function () { return dbgOccTests; },
    lastFaces: function () { return dbgLastFaces; },
    lastSegs: function () { return dbgLastSegs; },
    resetCounters: function () { dbgProjCalls = 0; dbgOccTests = 0; dbgProjReuse = 0; },
    toolState: function () {
      return { activeTool: activeTool, pending: !!pendingImage, sel: (toolSel || []).length };
    },
    snapState: function () { return { on: !!snapOn, shift: !!shiftKeyPressed }; },
    gridStep: function () { return niceStep(); },
    camState: function () { return { r: cam.r, theta: cam.theta, phi: cam.phi, tx: cam.tx, ty: cam.ty, tz: cam.tz }; },
    proj3At: function (p) { return proj3([p[0], p[1], p[2]]); },   // 3D 世界坐标 → 画布屏幕坐标（检测用）
    // pointerdown 早退点集中快照（定位「画布点击/拖动无反应」这类问题的唯一入口）
    panelState: function () {
      return { activeTool: activeTool, toolBusy: !!toolBusy, queue: (toolPointQueue || []).length,
               selectMode: !!selectMode, snapOn: !!snapOn, shift: !!shiftKeyPressed,
               pending: !!pendingImage, touches: Object.keys(touches).length,
               drag: !!drag, pan: !!pan, pinch: !!pinch, macroPick: !!macroPickMode };
    },
    els3dCount: function () { return (typeof els3d !== 'undefined' && els3d) ? els3d.length : -1; },
    mode3d: function () { return typeof mode3d !== 'undefined' ? !!mode3d : null; },
    load3d: function () { load3d(); },
    rev3d: function () { return typeof lastRev3d !== 'undefined' ? lastRev3d : -1; },
    refreshCount: function () { return dbgRefreshN; },
    loadCount: function () { return dbgLoadN; }
  };

  function render3d() {
    ctx3.clearRect(0, 0, cssW, cssH);
    // 坐标轴（带箭头 + 标签；原点不标记）
    drawAxes3d();
    // 工作平面网格画在坐标轴之下（已在上方画箭头，这里只画基准平面网格）
    _overlay.drawBasePlane();
    // 三维场景绘制（几何收集/遮挡/顶点）已抽到 static/scene3d.js（P2 前端拆分）
    _scene.drawScene();
    _overlay.drawSelection3d();
    _overlay.drawZHandle();
    // 左下角微缩坐标轴（最后画，置顶）
    drawMiniAxes3d();
  }

  // 3D 模式：工具激活时点击建对象；否则自由点拖动 / 轨道旋转
  function hitPoint3d(sx, sy) {
    for (var i = 0; i < els3d.length; i++) {
      var e = els3d[i];
      if (e.kind !== 'point') continue;
      var pr = proj3([e.x, e.y, e.z]);
      if (Math.hypot(pr.x - sx, pr.y - sy) <= 12) return e;
    }
    return null;
  }
  // z 控制柄命中：选中自由 3D 点的 z 箭头线段附近（屏幕距离 < 14px）
  function hitZHandle3d(sx, sy) {
    if (!selected3d) return null;
    var e = findEl3d(selected3d);
    if (!e || e.kind !== 'point' || !e.free) return null;
    var zp = proj3([e.x, e.y, e.z]);
    var zUp3 = proj3([e.x, e.y, e.z + 1]);
    var zdx = zUp3.x - zp.x, zdy = zUp3.y - zp.y;
    var zln = Math.hypot(zdx, zdy) || 1;
    zdx /= zln; zdy /= zln;
    var hx = zp.x + zdx * 42, hy = zp.y + zdy * 42;
    var tH = (sx - zp.x) * zdx + (sy - zp.y) * zdy;   // 沿 z 柄方向的距离（>10 才算命中柄，避免与点本身冲突）
    if (tH > 10 && distToSeg(sx, sy, zp.x, zp.y, hx, hy) <= 14) return e;
    return null;
  }
  // 3D 对象拾取：点 / 多面体边 / 平面边框 / 球线框 / 线段（屏幕距离阈值 10px）
  // 屏幕坐标点在多边形内（用于 3D 实体面命中）
  // 选中对象拖动平移：命中边线或实体面内部
  function hitObjectForDrag3d(sx, sy) {
    var e = hitObject3d(sx, sy);
    if (e) return e;
    for (var i = 0; i < els3d.length; i++) {
      var o = els3d[i];
      if (o.visible === false) continue;
      if (o.objtype !== 'cube' && o.objtype !== 'polyhedron') continue;
      var dt = o.data || {};
      var vs = dt.verts || [], faces = dt.faces || [];
      for (var fi = 0; fi < faces.length; fi++) {
        var poly = [];
        for (var vi = 0; vi < faces[fi].length; vi++) {
          var pr = proj3(vs[faces[fi][vi]]);
          poly.push([pr.x, pr.y]);
        }
        if (pointInScreenPoly(sx, sy, poly)) return o;
      }
    }
    return null;
  }
  // 对象所在参考高度 z（平移时保持该平面）
  function objZRef3d(el) {
    if (!el) return planeZ;
    var dt = el.data || {};
    if (el.objtype === 'cube' || el.objtype === 'polyhedron') {
      var vs = dt.verts || [];
      if (!vs.length) return planeZ;
      var s = 0;
      for (var i = 0; i < vs.length; i++) s += vs[i][2];
      return s / vs.length;
    }
    if (el.objtype === 'segment' || el.objtype === 'line2d' || el.objtype === 'line3d') {
      return ((dt.z1 != null ? dt.z1 : 0) + (dt.z2 != null ? dt.z2 : 0)) / 2;
    }
    if (el.objtype === 'plane') return dt.az || 0;
    if (el.objtype === 'sphere') return dt.cz || 0;
    if (el.objtype === 'circle3d') return dt.cz || 0;
    if (el.objtype === 'curve3d') {
      var sgs = dt.segs || [];
      if (!sgs.length) return planeZ;
      var zc = 0, n4 = 0;
      for (var si4 = 0; si4 < sgs.length; si4++) { zc += sgs[si4][0][2]; n4++; }
      return n4 ? zc / n4 : planeZ;
    }
    if (el.objtype === 'section') {
      var sp = dt.pts || [];
      if (!sp.length) return planeZ;
      var sz = 0;
      for (var si = 0; si < sp.length; si++) sz += sp[si][2];
      return sz / sp.length;
    }
    if (el.kind === 'point') return (el.z != null ? el.z : 0);
    return planeZ;
  }

  // 按 objtype 命中 3D 对象（用于立方体工具的"点击线段/正方形"）
  function setSelected3d(label) {
    selected3d = label;
    populateEditBar3d();
    render3d();
    if (label) {
      var se3 = findEl3d(label);
      if (se3 && se3.kind === 'point' && se3.free) {
        var esc3 = label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        var re3 = new RegExp('(^|[^A-Za-z0-9_])' + esc3 + '([^A-Za-z0-9_]|$)');
        var drives = false;
        for (var di = 0; di < els3d.length; di++) {
          var oe = els3d[di];
          if ((oe.objtype === 'cube' || oe.objtype === 'polyhedron') && oe.defn && re3.test(oe.defn)) { drives = true; break; }
        }
        if (drives) {
          setMsg(lang === 'en' ? ('Control point ' + label + ' selected — drag to resize')
                               : ('已选中控制点 ' + label + ' — 拖动可改变立体大小'), false);
        } else {
          setMsg(lang === 'en' ? ('Free point ' + label + ' selected — drag to move')
                               : ('已选中自由点 ' + label + ' — 拖动可移动'), false);
        }
      }
    }
  }
  // 轴吸附：点击靠近某坐标轴（x/y/z 屏幕投影）时，把点吸附到该轴上（得到轴上的三维点）
  function setToolStatus3d() {
    var T = TOOLS[tool3d];
    var arr = lang === 'en' ? T.en : T.hints;
    var msg = arr[Math.min(toolSel3d.length, arr.length - 1)];
    var st = document.getElementById('tool-status');
    if (st) st.textContent = msg;
  }
  function resetTool3d() {
    tool3d = null;
    toolSel3d = [];
    updateToolButtons3d();
    var st = document.getElementById('tool-status');
    if (st) st.textContent = '';
  }
  // 指针捕获是**尽力而为**：合成事件/已失活指针会让 setPointerCapture 抛 DOMException，
  // 任其抛出会中断整个 pointerdown 处理函数（3D 侧同样处理；**绝不能写成自递归** ✗）
  function capturePointer3d(ev) {
    try { cv3d.setPointerCapture(ev.pointerId); } catch (e) { /* 捕获失败不致命：继续处理 */ }
  }
  cv3d.addEventListener('pointerdown', function (ev) {
    ev.preventDefault();
    if (tool3d) { tool3dClick(ev.offsetX, ev.offsetY); return; }
    // 宏点选模式：点击 3D 对象 → 加入输入/输出框
    if (macroPickMode && ev.button !== 2) {
      var pk3 = hitPoint3d(ev.offsetX, ev.offsetY) || hitObject3d(ev.offsetX, ev.offsetY);
      if (pk3) handleMacroPick(pk3.label);
      return;
    }
    // 右键：直接进入视图旋转（不受对象/点拾取影响）
    if (ev.button === 2) {
      camDrag = { x: ev.offsetX, y: ev.offsetY, shift: ev.shiftKey };
      capturePointer3d(ev);
      return;
    }
    // 优先：点击 z 控制柄 → 拖动改 z（直观改高度）
    var zh = hitZHandle3d(ev.offsetX, ev.offsetY);
    if (zh) {
      var zpe = proj3([zh.x, zh.y, zh.z]);
      dragZHandle = { label: zh.label, sy0: ev.offsetY, z0: (zh.z != null ? zh.z : 0), handleScreenY: zpe.y };
      capturePointer3d(ev);
      return;
    }
    // 点击 3D 自由点 → 拖动（普通=沿基准平面 x/y；Shift=仅改 z 垂直移动）
    var hp = hitPoint3d(ev.offsetX, ev.offsetY);
    if (hp && hp.free) {
      var wasSelPt = (selected3d === hp.label);
      setSelected3d(hp.label);   // 点击控制点即选中（橙色菱形 + 光环）
      drag3d = { label: hp.label, sx: ev.offsetX, sy: ev.offsetY, z0: (hp.z != null ? hp.z : 0),
                 mode: ev.shiftKey ? 'z' : 'xy', moved: false, wasSelected: wasSelPt };
      capturePointer3d(ev);
      return;
    }
    // 点击 3D 对象 → 选中并可直接拖动平移（普通=水平面 x/y；Shift=仅改 z 高度）
    var hitObj = hitObjectForDrag3d(ev.offsetX, ev.offsetY);
    if (hitObj) {
      var wasSel3 = (selected3d === hitObj.label);   // 必须在 setSelected3d 之前取（否则恒 true）
      setSelected3d(hitObj.label);
      var zRef3 = objZRef3d(hitObj);
      var w03 = unproj3(ev.offsetX, ev.offsetY, zRef3);
      drag3dObj = { label: hitObj.label, mode: ev.shiftKey ? 'z' : 'xy', zRef: zRef3,
                    lastX: w03[0], lastY: w03[1], lastSY: ev.offsetY, pushed: false,
                    moved: false, wasSelected: wasSel3 };
      objShift3d.dx = 0; objShift3d.dy = 0; objShift3d.dz = 0; objShift3d.pushed = false;
      setMsg(lang === 'en' ? 'Selected — drag to translate (Shift+drag: height)' : '已选中 — 拖动平移（Shift+拖动改高度）', false);
      capturePointer3d(ev);
      ev.preventDefault();
      return;
    }
    camDrag = { x: ev.offsetX, y: ev.offsetY, shift: ev.shiftKey };
    capturePointer3d(ev);
  });
  // 阻止 3D 画布右键弹出浏览器菜单
  cv3d.addEventListener('contextmenu', function (ev) { ev.preventDefault(); });
  // 本地乐观平移（拖动期间即时反馈；服务器返回后 load3d 校正）
  // 累积位移合并提交（避免异步竞态）

  cv3d.addEventListener('pointermove', function (ev) {
    if (dragZHandle) {
      // 拖 z 控制柄：鼠标竖直位移 → z 增量（z 轴屏幕方向近似竖直）
      var pxScaleZH = Math.min(cssW, cssH) * 0.42 / cam.r;
      var dzPx = (dragZHandle.handleScreenY - ev.offsetY);   // 向上为正
      var newZ = dragZHandle.z0 + dzPx / pxScaleZH;
      var cur = findEl3d(dragZHandle.label);
      api('POST', '/api/drag', { label: dragZHandle.label, x: cur ? cur.x : 0, y: cur ? cur.y : 0, z: newZ, push: false, xmin: view.xmin, xmax: view.xmax, ymin: view.ymin, ymax: view.ymax }, function (d) {
        if (d && d.ok) load3d();
      });
      return;
    }
    if (drag3d) {
      if (drag3d.mode === 'z') {
        drag3d.moved = true;
        // Shift 拖动：仅改 z（垂直移动），x/y 不变。屏幕竖直位移 → z 增量（z 轴在屏幕上近似竖直）
        var pxScale3 = Math.min(cssW, cssH) * 0.42 / cam.r;
        var dyPx = ev.offsetY - drag3d.sy;
        var newZ = drag3d.z0 + (-dyPx) / pxScale3;
        // 找当前点 x/y
        var cur3d = findEl3d(drag3d.label);
        api('POST', '/api/drag', { label: drag3d.label, x: cur3d ? cur3d.x : 0, y: cur3d ? cur3d.y : 0, z: newZ, push: false, xmin: view.xmin, xmax: view.xmax, ymin: view.ymin, ymax: view.ymax }, function (d) {
          if (d && d.ok) load3d();
        });
        return;
      }
      // 自由 3D 点：拖到基准平面上反投影位置（保持 z=planeZ 投影后取平面坐标）
      drag3d.moved = true;
      var w = unproj3(ev.offsetX, ev.offsetY, planeZ);
      var CLAMP = 10;
      w[0] = Math.max(-CLAMP, Math.min(CLAMP, w[0]));
      w[1] = Math.max(-CLAMP, Math.min(CLAMP, w[1]));
      api('POST', '/api/drag', { label: drag3d.label, x: w[0], y: w[1], z: planeZ, push: false, xmin: view.xmin, xmax: view.xmax, ymin: view.ymin, ymax: view.ymax }, function (d) {
        if (d && d.ok) load3d();
      });
      return;
    }
    if (drag3dObj) {
      if (drag3dObj.mode === 'z') {
        var pxScaleO = Math.min(cssW, cssH) * 0.42 / cam.r;
        var dzO = (-(ev.offsetY - drag3dObj.lastSY)) / pxScaleO;
        drag3dObj.lastSY = ev.offsetY;
        if (dzO) drag3dObj.moved = true;
        objShift3d.dz += dzO;
        localShift3dEl(drag3dObj.label, 0, 0, dzO);
        render3d();
        flushObjShift3d();
        return;
      }
      var wO = unproj3(ev.offsetX, ev.offsetY, drag3dObj.zRef);
      var dxO = wO[0] - drag3dObj.lastX, dyO = wO[1] - drag3dObj.lastY;
      drag3dObj.lastX = wO[0]; drag3dObj.lastY = wO[1];
      if (!dxO && !dyO) return;
      drag3dObj.moved = true;
      objShift3d.dx += dxO; objShift3d.dy += dyO;
      localShift3dEl(drag3dObj.label, dxO, dyO, 0);
      render3d();
      flushObjShift3d();
      return;
    }
    if (!camDrag) return;
    var dx = ev.offsetX - camDrag.x, dy = ev.offsetY - camDrag.y;
    if (camDrag.shift) {
      cam.tx -= dx / cam.r * 2;
      cam.ty += dy / cam.r * 2;
    } else {
      // 斜二测是固定角度画法：一旦开始拖拽旋转，自动切换到自由正交视角（theta/phi 生效）
      if (view3dMode === 'oblique') {
        view3dMode = 'free';
        var vbs = document.querySelectorAll('.view3d-btn');
        for (var vi = 0; vi < vbs.length; vi++) vbs[vi].classList.remove('active');
      }
      cam.theta += dx * 0.01;
      cam.phi += dy * 0.01;
      cam.phi = Math.max(-1.5, Math.min(1.5, cam.phi));
    }
    camDrag.x = ev.offsetX; camDrag.y = ev.offsetY;
    render3d();
  });
  cv3d.addEventListener('pointerup', function () {
    if (drag3dObj && !drag3dObj.moved && drag3dObj.wasSelected) setSelected3d(null);  // 单击已选对象 → 取消选中
    if (drag3d && !drag3d.moved && drag3d.wasSelected) setSelected3d(null);            // 单击已选控制点 → 取消选中
    camDrag = null; drag3d = null; dragZHandle = null; drag3dObj = null;
  });
  cv3d.addEventListener('wheel', function (ev) {
    ev.preventDefault();
    cam.r *= (ev.deltaY < 0 ? 1 / 1.12 : 1.12);
    cam.r = Math.max(3, Math.min(200, cam.r));
    render3d();
  });

  var zplaneBox = document.getElementById('zplane-box');
  var zplaneInput = document.getElementById('zplane-input');
  if (zplaneInput) {
    zplaneInput.addEventListener('change', function () {
      var v = parseFloat(zplaneInput.value);
      if (!isNaN(v)) { planeZ = v; render3d(); }
    });
  }
  // 3D 轴刻度属性控制（显示/颜色），localStorage 持久化
  var tickToggle = document.getElementById('axisticks-toggle');
  var tickColor = document.getElementById('tick-color');
  if (tickToggle) {
    tickToggle.checked = axisTicks3d.show;
    tickToggle.addEventListener('change', function () { axisTicks3d.show = tickToggle.checked; saveAxisTicks3d(); render3d(); });
  }
  if (tickColor) {
    tickColor.value = axisTicks3d.color;
    tickColor.addEventListener('input', function () { axisTicks3d.color = tickColor.value; axisTicks3d.labelColor = tickColor.value; saveAxisTicks3d(); render3d(); });
  }
  
  // 3D 模式下：工具面板的类别按钮点击也要能激活 3D 工具
  var catToolsEl = document.getElementById('cat-tools');
  if (catToolsEl) {
    catToolsEl.addEventListener('click', function (ev) {
      var b = ev.target.closest ? ev.target.closest('.tool-btn') : null;
      if (!b || !mode3d) return;
      var name = b.getAttribute('data-tool');
      if (name && TOOLS[name] && ['pt3d', 'seg3d', 'line3d', 'plane3d', 'sphere3d', 'cube3d', 'cone3d', 'cylinder3d', 'prism3d', 'pyramid3d', 'tetra3d', 'octa3d', 'hexa3d', 'icosa3d', 'dodeca3d'].indexOf(name) !== -1) {
        if (tool3d === name) { resetTool3d(); return; }
        tool3d = name;
        toolSel3d = [];
        updateToolButtons3d();
        setToolStatus3d();
      }
    });
  }
  // 3D 视图切换：标准3D(斜二测正交)/俯视/前视/右视/free(自由正交旋转)
  function setView3d(mode) {
    view3dMode = mode;
    ortho3d = mode !== 'iso' && mode !== 'persp';   // 斜二测/俯/前/右/free 为正交，iso/persp 透视
    if (mode === 'iso' || mode === 'oblique' || mode === 'free') {
      cam.r = 14; cam.tx = 0; cam.ty = 0; cam.tz = 0;
    } else if (mode === 'top') {
      cam.r = 14; cam.tx = 0; cam.ty = 0; cam.tz = 0;
    } else if (mode === 'front') {
      cam.r = 14; cam.tx = 0; cam.ty = 0; cam.tz = 0;
    } else if (mode === 'right') {
      cam.r = 14; cam.tx = 0; cam.ty = 0; cam.tz = 0;
    }
    // 更新视图按钮高亮
    var vbs = document.querySelectorAll('.view3d-btn');
    for (var vi = 0; vi < vbs.length; vi++) vbs[vi].classList.toggle('active', vbs[vi].getAttribute('data-view') === mode);
    render3d();
  }
  var viewBtns = document.querySelectorAll('.view3d-btn');
  for (var vbi = 0; vbi < viewBtns.length; vbi++) {
    viewBtns[vbi].addEventListener('click', function () {
      setView3d(this.getAttribute('data-view'));
    });
  }
  btn('btn-3d', function () {
    mode3d = !mode3d;
    canvas.style.display = mode3d ? 'none' : 'block';
    cv3d.style.display = mode3d ? 'block' : 'none';
    zplaneBox.style.display = mode3d ? 'flex' : 'none';
    if (mode3d) {
      if (zplaneInput) zplaneInput.value = planeZ;
      resize3d();
      load3d();
      // 切 3D 时自动显示 3D 类别
      showCat('d3');
    } else {
      if (tool3d) resetTool3d();
      selected3d = null;
      populateEditBar3d();
      loadState();
    }
  });

  // ---------- 输入与按钮 ----------
  function submitInput() {
    var text = cmdEl.value.trim();
    if (!text) return;
    api('POST', '/api/input', {
      text: text,
      xmin: view.xmin, xmax: view.xmax, ymin: view.ymin, ymax: view.ymax
    }, function (d) {
      setMsg(d.message, !d.ok);
      if (d.elements) { elements = d.elements; render(); }
      refresh3dIfNeeded();          // 3D 模式下同步刷新 3D 视图与列表
      if (d.ok) { cmdEl.value = ''; cmdHintUpdate('input'); }   // 清空后同步收起提示（程序改 value 不触发 input 事件）
    });
  }

  // 输入历史（↑↓）与命令补全
  var cmdHistory = [];
  var histIdx = -1;
  // 数学输入预览：命令文本 → LaTeX → KaTeX 渲染（所见即所得）；无 KaTeX 时回退 Unicode
  var previewEl = document.getElementById('math-preview');
  var SUPS = { '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴', '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹' };
  function mathFallback(s) {
    s = s.replace(/pi/g, 'π').replace(/theta/g, 'θ');
    s = s.replace(/sqrt\(/g, '√(').replace(/abs\(/g, '|').replace(/\)/g, ')');
    s = s.replace(/\^(\d+)/g, function (m, d) {
      return d.split('').map(function (c) { return SUPS[c]; }).join('');
    });
    s = s.replace(/>\s*=/g, '≥').replace(/<\s*=/g, '≤').replace(/\*/g, '·');
    return s;
  }
  var GREEK_W = ['pi', 'theta', 'alpha', 'beta', 'gamma', 'delta', 'lambda', 'omega', 'phi', 'sigma', 'mu', 'tau', 'xi', 'rho', 'eta', 'kappa'];
  var GREEK_T = { pi: '\\pi', theta: '\\theta', alpha: '\\alpha', beta: '\\beta', gamma: '\\gamma', delta: '\\delta', lambda: '\\lambda', omega: '\\omega', phi: '\\phi', sigma: '\\sigma', mu: '\\mu', tau: '\\tau', xi: '\\xi', rho: '\\rho', eta: '\\eta', kappa: '\\kappa' };
  var FN_W = ['sin', 'cos', 'tan', 'asin', 'acos', 'atan', 'ln', 'log10', 'log', 'exp', 'sinh', 'cosh', 'tanh', 'floor', 'ceil', 'min', 'max', 'gcd', 'lcm', 'sqrt', 'abs'];
  var FN_T = { sin: '\\sin', cos: '\\cos', tan: '\\tan', asin: '\\arcsin', acos: '\\arccos', atan: '\\arctan', ln: '\\ln', log10: '\\log_{10}', log: '\\log', exp: '\\exp', sinh: '\\sinh', cosh: '\\cosh', tanh: '\\tanh', floor: '\\lfloor', ceil: '\\lceil', min: '\\min', max: '\\max', gcd: '\\gcd', lcm: '\\operatorname{lcm}', sqrt: '\\sqrt', abs: '\\left|' };
  var CMD_W = ['Midpoint', 'Circle', 'Line', 'Segment', 'Ray', 'Polygon', 'Polyline', 'Intersect', 'Distance', 'Slope', 'Angle', 'Length', 'Translate', 'Rotate', 'Reflect', 'Dilate', 'Vector', 'PointOnCircle', 'Parametric', 'Polar', 'Implicit', 'Slider', 'Sequence', 'Sum', 'Mean', 'Median', 'Mode', 'Variance', 'Stdev', 'Sort', 'FitLine', 'FitPoly', 'FitExp', 'NormalDist', 'BarChart', 'SolveIneq', 'Solve', 'Factor', 'Expand', 'Limit', 'Derivative', 'Integral', 'Root', 'Extremum', 'Tangent', 'Focus', 'Conic', 'Ellipse', 'Hyperbola', 'Parabola', 'Incircle', 'Incenter', 'Centroid', 'Area', 'Perimeter', 'Circumference', 'Arc', 'Sector', 'Text', 'Locus', 'Matrix', 'Det', 'Transpose', 'Inverse', 'Prove', 'SetCoords', 'SetValue', 'SetColor', 'SetVisible', 'SetLocked', 'SetWire', 'ShowGrid', 'ShowAxes', 'Delete', 'Rename', 'Redefine'];
  function renderPreview() {
    var v = cmdEl.value.trim();
    if (!v) { previewEl.style.display = 'none'; return; }
    previewEl.style.display = 'block';
    if (window.katex) {
      try {
        previewEl.innerHTML = window.katex.renderToString(toLatex(v), { throwOnError: false, displayMode: false, output: 'html' });
        return;
      } catch (e) {}
    }
    previewEl.textContent = mathFallback(v);
  }
  cmdEl.addEventListener('input', renderPreview);
  cmdEl.addEventListener('keydown', function (ev) {
    if (ev.key === 'Enter') previewEl.style.display = 'none';
  });
  cmdEl.addEventListener('keydown', function (ev) {
    if (ev.key === 'Enter') {
      // 模板内（光标落在某个参数上）→ 依次跳参，不提交；到最后一个参数才交回提交逻辑
      if (cmdParamJump(1, false, false)) { ev.preventDefault(); return; }
      var v = cmdEl.value.trim();
      if (v) { cmdHistory.push(v); if (cmdHistory.length > 100) cmdHistory.shift(); }
      histIdx = -1;
      submitInput();
    } else if (ev.key === 'ArrowUp') {
      ev.preventDefault();
      if (cmdHistory.length) {
        histIdx = (histIdx === -1) ? cmdHistory.length - 1 : Math.max(0, histIdx - 1);
        cmdEl.value = cmdHistory[histIdx];
      }
    } else if (ev.key === 'ArrowDown') {
      ev.preventDefault();
      if (histIdx !== -1) {
        histIdx++;
        cmdEl.value = histIdx < cmdHistory.length ? cmdHistory[histIdx] : '';
        if (histIdx >= cmdHistory.length) histIdx = -1;
      }
    }
  });
  // 命令补全 datalist（value=名字[ ，label=完整签名 → 下拉里能直接看到参数）
  var cmdSigs = {}, cmdDisp = {};     // key → 签名 / 显示名
  var cmdKeyByName = {};              // 小写显示名 → 内部 key（模板态判断用）
  fetch('/api/commands').then(function (r) { return r.json(); }).then(function (d) {
    var dl = document.getElementById('cmd-list');
    var s = '';
    var dsp = d.display || {};
    cmdSigs = d.sigs || {};
    cmdDisp = dsp;
    cmdKeyByName = {};
    for (var i = 0; i < d.commands.length; i++) {
      var k = d.commands[i], nm = dsp[k] || k;
      cmdKeyByName[String(nm).toLowerCase()] = k;
      s += '<option value="' + nm + '[" label="' + (cmdSigs[k] || (nm + '[…]')).replace(/"/g, '') + '"></option>';
    }
    dl.innerHTML = s;
  }).catch(function () {});

  // 命令栏候选列表：**只要前缀有匹配就列出**（最多 5 条，每条带完整参数签名），
  // Tab 补全当前选中项；↑/↓ 切换选中；Esc 收起。不再要求"前缀唯一"（那样大多数输入都没提示 ✗）
  var cmdCands = [], cmdSel = 0;
  function cmdHintRender(keepSel) {
    var el = document.getElementById('cmd'), hint = document.getElementById('cmd-hint');
    if (!el || !hint) return;
    var pre = String(el.value).split('[')[0].trim().toLowerCase();
    cmdCands = [];
    if (!keepSel) cmdSel = 0;      // ↑↓ 切换时保留选中，否则重置
    if (pre.length >= 1) {
      var keys = Object.keys(cmdSigs), exact = null, starts = [];
      for (var i2 = 0; i2 < keys.length; i2++) {
        var k = keys[i2], nm = (cmdDisp[k] || k).toLowerCase();
        if (nm === pre) exact = k;
        else if (nm.indexOf(pre) === 0) starts.push(k);
      }
      starts.sort();
      if (exact) { cmdCands.push(exact); }
      for (var j2 = 0; j2 < starts.length && cmdCands.length < 5; j2++) cmdCands.push(starts[j2]);
    }
    if (cmdSel >= cmdCands.length) cmdSel = 0;
    if (!cmdCands.length) { hint.style.display = 'none'; hint.innerHTML = ''; return; }
    var html = '';
    for (var m = 0; m < cmdCands.length; m++) {
      var kk = cmdCands[m];
      html += '<div class="cmd-cand' + (m === cmdSel ? ' cur' : '') + '" data-k="' + kk + '">'
            + esc(cmdSigs[kk] || cmdDisp[kk] || kk) + '</div>';
    }
    hint.innerHTML = html;
    hint.style.display = 'block';
    for (var n = 0; n < hint.children.length; n++) {
      hint.children[n].addEventListener('mousedown', function (ev) {
        ev.preventDefault();
        cmdComplete(ev.currentTarget.getAttribute('data-k'));
      });
    }
  }
  // 首个 `[...]` 的配对 `]` 位置（按深度配对；签名里可能有第二组，如 `BarChart[{值…}] 或 BarChart[…, …]`）
  function cmdBracketEnd(s) {
    var open = String(s).indexOf('[');
    if (open < 0) return -1;
    var depth = 0;
    for (var i = open; i < s.length; i++) {
      var c = s.charAt(i);
      if (c === '[') depth++;
      else if (c === ']') { depth--; if (depth === 0) return i; }
    }
    return -1;
  }
  function cmdComplete(key) {
    var el = document.getElementById('cmd'), hint = document.getElementById('cmd-hint');
    if (!el || !key) return;
    var sig = cmdSigs[key] || ((cmdDisp[key] || key) + '[');
    // 签名里的「或」备选形式（`Midpoint[点, 点] 或 Midpoint[线段]`）不是可提交文本 → 只留首个 `[...]` 形式
    var close = cmdBracketEnd(sig);
    if (close >= 0) {
      var alt = sig.indexOf(' 或 ', close);
      if (alt >= 0) sig = sig.slice(0, alt);
    }
    el.value = sig;
    cmdCands = [];
    if (hint) { hint.style.display = 'none'; hint.innerHTML = ''; }
    var spans = cmdParamRanges(el);
    if (spans && spans.length) { cmdParamSelect(spans, 0); return; }   // 选中首个参数 → 可直接键入覆盖
    var cut = el.value.lastIndexOf(']');
    try { el.setSelectionRange(cut < 0 ? el.value.length : cut, cut < 0 ? el.value.length : cut); } catch (e) { /* 光标设置失败忽略 */ }
  }

  // ---------- 命令模板态：参数区间 / 跳参 / 高亮 ----------
  // 取「首个 [...]」里按**顶层逗号**切出的参数区间（括号内的逗号不算，如 `(x,y)`、`{a,b}`）；非模板态返回 null
  function cmdParamRanges(el) {
    var v = String(el.value || '');
    var open = v.indexOf('[');
    if (open < 0) return null;
    var nm = v.slice(0, open).trim().toLowerCase();
    if (!nm || !Object.prototype.hasOwnProperty.call(cmdKeyByName, nm)) return null;
    var close = -1, depth = 0;
    for (var i = open; i < v.length; i++) {
      var c0 = v.charAt(i);
      if (c0 === '[') depth++;
      else if (c0 === ']') { depth--; if (depth === 0) { close = i; break; } }
    }
    if (close <= open) return null;                 // 还没闭合 → 不算模板态
    if (!v.slice(open + 1, close).trim()) return null;   // `名字[]` = 无参数命令（如 MacroList[]）→ 不进模板态
    var inner = v.slice(open + 1, close), parts = [], from = 0, d = 0;
    for (var j = 0; j < inner.length; j++) {
      var c = inner.charAt(j);
      if (c === '(' || c === '[' || c === '{') d++;
      else if (c === ')' || c === ']' || c === '}') d = Math.max(0, d - 1);
      else if (c === ',' && d === 0) { parts.push([from, j]); from = j + 1; }
    }
    parts.push([from, inner.length]);
    var spans = [];
    for (var p = 0; p < parts.length; p++) {
      var a = parts[p][0], b = parts[p][1];
      while (a < b && /\s/.test(inner.charAt(a))) a++;
      while (b > a && /\s/.test(inner.charAt(b - 1))) b--;
      spans.push({ start: open + 1 + a, end: open + 1 + b });
    }
    return spans;
  }
  function cmdParamIdxAt(el, spans) {           // 光标落在第几个参数上（末尾也算命中）
    var pos = el.selectionStart;
    if (typeof pos !== 'number' || pos < 0) return -1;
    for (var i = 0; i < spans.length; i++) if (pos >= spans[i].start && pos <= spans[i].end) return i;
    return -1;
  }
  function cmdParamSelect(spans, i) {
    var el = document.getElementById('cmd');
    if (!el || !spans || !spans.length) return;
    if (i < 0) i = 0;
    if (i >= spans.length) i = spans.length - 1;
    el.focus();
    try { el.setSelectionRange(spans[i].start, spans[i].end); } catch (e) { /* 选不中就算了 */ }
    cmdParamHint();
  }
  // step=+1 向后；wrap=Tab 循环；fromStart=光标不在任何参数上时是否选中首个（Tab 用；Enter 不用 → 保持提交）
  function cmdParamJump(step, wrap, fromStart) {
    var el = document.getElementById('cmd');
    if (!el) return false;
    var spans = cmdParamRanges(el);
    if (!spans || !spans.length) return false;
    var cur = cmdParamIdxAt(el, spans);
    if (cur < 0) {
      if (!fromStart) return false;
      cmdParamSelect(spans, 0);
      return true;
    }
    var n = spans.length, next = cur + step;
    if (next >= n || next < 0) {
      if (!wrap) return false;                      // Enter：到末参 → 交回提交逻辑
      next = ((next % n) + n) % n;
    }
    if (next === cur && n <= 1) return false;       // 只有一个参数 → 没有可跳的
    cmdParamSelect(spans, next);
    return true;
  }
  // 模板态提示：单行显示模板，**加粗高亮光标所在参数**；点参数可直接选中它。返回是否处于模板态
  function cmdParamHint() {
    var el = document.getElementById('cmd'), hint = document.getElementById('cmd-hint');
    if (!el || !hint) return false;
    var spans = cmdParamRanges(el);
    if (!spans || !spans.length) return false;
    var v = String(el.value), cur = cmdParamIdxAt(el, spans), html = '', last = 0;
    for (var i = 0; i < spans.length; i++) {
      var txt = v.slice(spans[i].start, spans[i].end);
      var opt = /\?\s*$/.test(txt);                  // 签名里以 `?` 结尾 = 可选参数（只做提示，不做校验）
      html += esc(v.slice(last, spans[i].start))
            + '<span class="cmd-param' + (i === cur ? ' cur' : '') + (opt ? ' cmd-opt' : '')
            + '" data-i="' + i + '">' + esc(txt) + '</span>';
      last = spans[i].end;
    }
    // 位序（纯数字，语言无关）：当前第几个 / 共几个参数
    var pos = (cur >= 0 ? (cur + 1) : '–') + '/' + spans.length;
    html += esc(v.slice(last)) + '<span class="cmd-pos">' + pos + '</span>';
    hint.innerHTML = html;
    hint.style.display = 'block';
    var ps = hint.querySelectorAll('.cmd-param');
    for (var k = 0; k < ps.length; k++) {
      ps[k].addEventListener('mousedown', function (ev) {
        ev.preventDefault();                        // 保住输入框焦点
        var idx = parseInt(ev.currentTarget.getAttribute('data-i'), 10) || 0;
        cmdParamSelect(cmdParamRanges(document.getElementById('cmd')), idx);
      });
    }
    return true;
  }
  // 统一入口：模板态 → 参数高亮；否则 → 候选列表（只有 `input` 才重置候选选中，避免 ↑↓ 后 keyup 把选中打回 0）
  function cmdHintUpdate(mode) {
    if (cmdParamHint()) { cmdCands = []; return; }
    if (mode === 'input') cmdHintRender();
  }
  var cmdElRef = document.getElementById('cmd');
  if (cmdElRef) {
    cmdElRef.addEventListener('input', function () { cmdHintUpdate('input'); });
    cmdElRef.addEventListener('focus', function () { cmdHintUpdate('input'); });
    cmdElRef.addEventListener('click', function () { cmdHintUpdate('sel'); });
    cmdElRef.addEventListener('keyup', function () { cmdHintUpdate('sel'); });
    cmdElRef.addEventListener('blur', function () { setTimeout(function () { var h = document.getElementById('cmd-hint'); if (h) h.style.display = 'none'; }, 150); });
    cmdElRef.addEventListener('keydown', function (ev) {
      var hint = document.getElementById('cmd-hint');
      if (ev.key === 'Tab') {
        if (cmdCands.length) { ev.preventDefault(); cmdComplete(cmdCands[cmdSel]); }
        // Shift+Tab = 反向跳参（同样循环）；不在模板内时行为不变
        else if (cmdParamJump(ev.shiftKey ? -1 : 1, true, true)) { ev.preventDefault(); }
      } else if ((ev.key === 'ArrowDown' || ev.key === 'ArrowUp') && cmdCands.length) {
        ev.preventDefault();
        cmdSel = (cmdSel + (ev.key === 'ArrowDown' ? 1 : cmdCands.length - 1)) % cmdCands.length;
        cmdHintRender(true);
      } else if (ev.key === 'Escape') {
        if (hint) { hint.style.display = 'none'; hint.innerHTML = ''; }
        cmdCands = [];
      }
    });
  }

  btn('btn-help', function () {
    fetch('/api/commands').then(function (r) { return r.json(); }).then(function (d) {
      showHelpModal(d.commands, d.display || {}, d.sigs || {});
    }).catch(function () { setMsg('加载命令失败', true); });
  });

  function btn(id, action) {
    document.getElementById(id).addEventListener('click', action);
  }

  btn('btn-undo', function () {
    api('POST', '/api/undo', null, function (d) { setMsg(d.message, !d.ok); if (d.elements) { elements = d.elements; render(); } refresh3dIfNeeded(); });
  });
  btn('btn-redo', function () {
    api('POST', '/api/redo', null, function (d) { setMsg(d.message, !d.ok); if (d.elements) { elements = d.elements; render(); } refresh3dIfNeeded(); });
  });
  btn('btn-clear', function () {
    if (!confirm('确定清空所有对象？')) return;
    api('POST', '/api/clear', null, function (d) { setMsg(d.message, !d.ok); if (d.elements) { elements = d.elements; render(); } refresh3dIfNeeded(); });
  });
  btn('btn-demo', function () {
    api('POST', '/api/demo', null, function (d) { setMsg(d.message, !d.ok); if (d.elements) { elements = d.elements; render(); } });
  });
  btn('btn-save', function () {
    var url = '/api/download?xmin=' + view.xmin + '&xmax=' + view.xmax + '&ymin=' + view.ymin + '&ymax=' + view.ymax;
    window.location.href = url;
  });
  btn('btn-share', function () {
    api('POST', '/api/share', { xmin: view.xmin, xmax: view.xmax, ymin: view.ymin, ymax: view.ymax }, function (d) {
      if (!d || !d.ok || !d.id) { setMsg('分享失败: ' + (d && d.message || ''), true); return; }
      var url = location.origin + location.pathname + '?s=' + d.id;
      var done = function () {
        setMsg((lang === 'en' ? 'Share link copied: ' : '分享链接已复制: ') + url, false);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url).then(done, done);
      } else done();
    });
  });
  btn('btn-svg', function () {
    window.location.href = '/api/export/svg?xmin=' + view.xmin + '&xmax=' + view.xmax + '&ymin=' + view.ymin + '&ymax=' + view.ymax;
  });
  btn('btn-obj', function () {
    window.location.href = '/api/export/obj';
  });
  btn('btn-stl', function () {
    window.location.href = '/api/export/stl';
  });
  btn('btn-gltf', function () {
    window.location.href = '/api/export/gltf';
  });
  btn('btn-png', function () {
    var a = document.createElement('a');
    a.download = 'ggbpy.png';
    a.href = canvas.toDataURL('image/png');
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  });
  btn('btn-svg3d', function () {
    window.location.href = '/api/export/svg?view3d=1';
  });
  btn('btn-objin', function () {
    document.getElementById('objfile').click();
  });
  document.getElementById('objfile').addEventListener('change', function (ev) {
    var f = ev.target.files[0];
    ev.target.value = '';
    if (!f) return;
    var rd = new FileReader();
    rd.onload = function () {
      fetch('/api/mesh', { method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: rd.result })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (!d || !d.ok) {
            setMsg((lang === 'en' ? 'OBJ import failed: ' : 'OBJ 导入失败: ') + ((d && d.message) || ''), true);
            return;
          }
          document.getElementById('cmd').value = 'Mesh[' + d.id + ']';
          submitInput();
          setMsg((lang === 'en' ? 'Mesh imported: ' : '已导入网格 ') + d.verts + ' v / ' + d.faces + ' f'
                 + (d.warnings && d.warnings.length ? ('（' + d.warnings.join('；') + '）') : ''), false);
        })
        .catch(function (e) { setMsg((lang === 'en' ? 'OBJ import error: ' : 'OBJ 导入出错: ') + e, true); });
    };
    rd.readAsArrayBuffer(f);
  });
  // 视图按钮（即时生效）：以**画布中心**为锚点缩放，锚点处的世界坐标保持不动
  function viewZoom(factor) {
    var cx = cssW / 2, cy = cssH / 2;
    var wx = wxp(cx), wy = wyp(cy);
    scale = Math.max(2, Math.min(200000, scale * factor));
    view.xmin = wx - cx / scale;
    view.xmax = view.xmin + cssW / scale;
    view.ymin = wy - (cssH - cy) / scale;
    view.ymax = view.ymin + cssH / scale;
    render();
  }
  function viewHome() {
    // 与启动视图一致：纵向恰好容纳 -8..8，横向按画布宽度铺满、原点居中
    // （旧实现把 xmax/ymax 写死为 ±8，与画布尺寸不一致 → 原点不居中）
    scale = Math.max(2, cssH / 16);
    view.ymin = -8;
    view.ymax = -8 + cssH / scale;
    view.xmin = -cssW / 2 / scale;
    view.xmax = view.xmin + cssW / scale;
    render();
  }
  btn('btn-anim-play', function () {
    var ls = sliderLabels();
    if (!ls.length) { setMsg(t('animNone'), true); return; }
    startPlay(ls);
    setMsg(t('animPlay') + ': ' + ls.length + ' · ' + anim.ms + 'ms / ' + anim.dir, false);
  });
  btn('btn-anim-stop', function () { stopPlay(); render(); setMsg(t('animStop'), false); });
  btn('btn-anim-set', function () {
    var v = prompt(t('animSettings'), anim.ms + ',' + anim.dir);
    if (v === null) return;
    var sp = String(v).split(',');
    var ms = parseFloat(sp[0]);
    if (ms >= 10 && ms <= 2000) anim.ms = ms;
    var d = (sp[1] || '').trim();
    if (d === 'up' || d === 'down' || d === 'bounce') anim.dir = d;
    if (playState) { var ls = playingLabels(); stopPlay(); startPlay(ls); }   // 立即生效
    setMsg(t('animSet') + ': ' + anim.ms + 'ms / ' + anim.dir, false);
  });

  btn('btn-zoomin', function () { viewZoom(1.3); setMsg(t('tool_zoomin'), false); });
  btn('btn-zoomout', function () { viewZoom(1 / 1.3); setMsg(t('tool_zoomout'), false); });
  btn('btn-home', function () { viewHome(); setMsg(t('tool_home'), false); });

  btn('btn-image', function () {
    document.getElementById('imgfile').click();
  });
  document.getElementById('imgfile').addEventListener('change', function (ev) {
    var f = ev.target.files[0];
    ev.target.value = '';
    if (!f) return;
    var rd = new FileReader();
    rd.onload = function () {
      var dataUrl = rd.result;
      var probe = new Image();
      probe.onload = function () {
        api('POST', '/api/image', { data: dataUrl, w: probe.naturalWidth, h: probe.naturalHeight }, function (d) {
          if (!d || !d.ok) {
            setMsg((lang === 'en' ? 'Image upload failed: ' : '图片上传失败: ') + ((d && d.message) || ''), true);
            return;
          }
          pendingImage = { id: d.id, ratio: probe.naturalHeight / probe.naturalWidth };
          if (selectMode) setSelectMode(false);
          startTool('image');
          setMsg(lang === 'en' ? 'Click the lower-left base point of the image' : '点击图片左下角基点', false);
        });
      };
      probe.onerror = function () { setMsg(lang === 'en' ? 'Cannot read image' : '无法读取图片', true); };
      probe.src = dataUrl;
    };
    rd.readAsDataURL(f);
  });
  btn('btn-load', function () {
    document.getElementById('file').click();
  });
  document.getElementById('file').addEventListener('change', function (ev) {
    var f = ev.target.files[0];
    if (!f) return;
    var rd = new FileReader();
    rd.onload = function () {
      fetch('/api/load', { method: 'POST', headers: { 'Content-Type': 'text/plain' }, body: rd.result })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          setMsg(d.message, !d.ok);
          if (d.view) {
            view.xmin = d.view[0]; view.xmax = d.view[1];
            view.ymin = d.view[2]; view.ymax = d.view[3];
            fitView();
          }
          if (d.elements) { elements = d.elements; render(); }
        });
    };
    rd.readAsText(f);
    ev.target.value = '';
  });

  listEl.addEventListener('pointerdown', function (ev) {
    var t = ev.target;
    if (t && t.classList && t.classList.contains('slider')) {
      api('POST', '/api/drag', { label: t.getAttribute('data-label'), x: parseFloat(t.value), y: 0, push: true }, function () {});
    }
  });
  // 对象列表行双击（控件行）→ 同一编辑器。
  // 注意：原生 dblclick 不可靠 —— 第一次点击会重渲染列表，第二次落在新节点上。
  // 因此按 data-label 手动计时检测（跨重渲染有效）；.df 单元格仍让给既有行内编辑。
  var rowClick = { label: null, t: 0 };
  var defnEdit = null;   // 行内定义编辑中的行 {label}（列表重渲染后需重开输入框）
  listEl.addEventListener('pointerdown', function (ev) {
    var t = ev.target;
    var row = t && t.closest ? t.closest('.obj') : null;
    if (!row) return;
    var lab = row.getAttribute('data-label');
    var df = t.closest('.df');
    var rEl = df ? null : findEl(lab);
    var isWidget = !!rEl && (rEl.kind === 'button' || rEl.kind === 'checkbox' || rEl.kind === 'inputbox'
                             || (rEl.kind === 'number' && rEl.min !== null && rEl.min !== undefined));
    if (!df && !isWidget) return;
    var now = new Date().getTime();
    if (rowClick.label === lab && now - rowClick.t < 450) {
      rowClick.label = null;
      rowClick.t = 0;
      ev.preventDefault();
      if (df) { defnEdit = { label: lab }; startDefnEdit(df); }
      else editWidget(rEl);
    } else {
      rowClick.label = lab;
      rowClick.t = now;
    }
  });

  listEl.addEventListener('input', function (ev) {
    var t = ev.target;
    if (t && t.classList && t.classList.contains('slider')) {
      api('POST', '/api/drag', { label: t.getAttribute('data-label'), x: parseFloat(t.value), y: 0, push: false }, function (d) {
        if (d && d.elements) { elements = d.elements; render(); }
      });
    }
  });

  // ---------- 对象面板位置：左/右/下切换 + 标题栏自由拖拽 ----------
  var panelEl = document.getElementById('panel');
  var panelTitleEl = document.getElementById('panel-title');
  var panelPos = localStorage.getItem('ggb_panel_pos') || 'bottom';
  var panelDrag = null;
  function updateTopH() {
    // 顶部区域高度（toolbar + catbar + cat-tools 的最下端）——侧边面板不遮挡顶部菜单
    var topH = 48;
    var ct = document.getElementById('cat-tools');
    if (ct && ct.offsetParent !== null) topH = Math.max(topH, ct.offsetTop + ct.offsetHeight);
    var cb = document.getElementById('catbar');
    if (cb && cb.offsetParent !== null) topH = Math.max(topH, cb.offsetTop + cb.offsetHeight);
    var tb = document.getElementById('toolbar');
    if (tb) topH = Math.max(topH, tb.offsetTop + tb.offsetHeight);
    document.documentElement.style.setProperty('--top-h', topH + 'px');
  }
  window.addEventListener('resize', updateTopH);
  function applyPanelPos(pos) {
    panelPos = pos;
    localStorage.setItem('ggb_panel_pos', pos);
    updateTopH();
    panelEl.className = pos === 'bottom' ? '' : 'ps-' + pos;
    // 清除自由拖拽产生的 inline 定位，让 CSS 类生效
    panelEl.style.left = ''; panelEl.style.top = ''; panelEl.style.right = '';
    panelEl.style.width = ''; panelEl.style.height = '';
    var btns = document.querySelectorAll('.panel-pos-btns .ppos');
    for (var bi = 0; bi < btns.length; bi++) btns[bi].classList.toggle('active', btns[bi].getAttribute('data-pos') === pos);
  }
  document.querySelectorAll('.panel-pos-btns .ppos').forEach(function (b) {
    b.addEventListener('click', function () { applyPanelPos(b.getAttribute('data-pos')); });
  });
  applyPanelPos(panelPos);
  // 标题栏拖拽：自由移动（window 级监听，兼容 headless/触摸）
  if (panelTitleEl) {
    panelTitleEl.addEventListener('pointerdown', function (ev) {
      if (ev.target.closest && ev.target.closest('.panel-pos-btns')) return;   // 不拦截位置按钮
      var r = panelEl.getBoundingClientRect();
      panelDrag = { sx: ev.clientX, sy: ev.clientY, rx: r.left, ry: r.top };
      ev.preventDefault();
    });
    window.addEventListener('pointermove', function (ev) {
      if (!panelDrag) return;
      panelEl.style.left = (panelDrag.rx + ev.clientX - panelDrag.sx) + 'px';
      panelEl.style.top = (panelDrag.ry + ev.clientY - panelDrag.sy) + 'px';
      panelEl.style.right = 'auto';
      panelEl.style.width = '300px';
      panelEl.style.height = 'auto';
      panelEl.classList.remove('ps-left', 'ps-right');
    });
    window.addEventListener('pointerup', function () {
      if (!panelDrag) return;
      panelDrag = null;
      // 吸附：靠近边缘自动贴边
      var r = panelEl.getBoundingClientRect();
      var snap = 60;
      if (r.left < snap) applyPanelPos('left');
      else if (window.innerWidth - r.right < snap) applyPanelPos('right');
      else if (window.innerHeight - r.top < snap) applyPanelPos('bottom');
    });
  }

  listEl.addEventListener('click', function (ev) {
    var sb = ev.target.closest ? ev.target.closest('[data-sb]') : null;
    if (sb) { editSliderRange(sb.getAttribute('data-sb')); return; }   // ⚙ 改滑块范围/步长
    var pb = ev.target.closest ? ev.target.closest('[data-pb]') : null;
    if (pb) { sliderPlay(pb.getAttribute('data-pb')); return; }
    var t = ev.target;
    while (t && t !== listEl && !t.getAttribute('data-label')) t = t.parentNode;
    if (t && t !== listEl) {
      var lbl = t.getAttribute('data-label');
      // 宏点选模式：点击列表行 → 加入输入/输出框
      if (macroPickMode) { handleMacroPick(lbl); return; }
      // 同步键盘光标到点击行
      var rows2 = listEl.querySelectorAll('.obj');
      for (var ri = 0; ri < rows2.length; ri++) if (rows2[ri].getAttribute('data-label') === lbl) { listCursor = ri; break; }
      // 轻量选中：只切 class，不重建 DOM（保留双击编辑能力）
      if (mode3d) setSelected3d((selected3d === lbl) ? null : lbl);
      else setSelected((selected === lbl) ? null : lbl);
    }
  });

  // 表达式列表行内编辑：双击定义文本直接修改（Enter 提交 / Esc 取消 / 失焦提交）
  function startDefnEdit(df) {
    if (!df || df.querySelector('input')) return;
    var row = df.closest('.obj');
    if (!row) return;
    var label = row.getAttribute('data-label');
    var original = df.textContent;
    df.textContent = '';
    var inp = document.createElement('input');
    inp.className = 'df-edit';
    inp.value = original;
    df.appendChild(inp);
    inp.focus();
    inp.select();
    var finish = function (commit) {
      defnEdit = null;
      if (inp.parentNode !== df) return;
      var val = inp.value.trim();
      try { inp.remove(); } catch (e) {}
      df.textContent = original;
      if (commit && val && val !== original) {
        postInput('Redefine[' + label + ', ' + val + ']');
      }
    };
    inp.addEventListener('keydown', function (e2) {
      if (e2.key === 'Enter') { e2.preventDefault(); finish(true); }
      else if (e2.key === 'Escape') { e2.preventDefault(); finish(false); }
    });
    inp.addEventListener('blur', function () { finish(false); });  // 失焦取消（Enter 才提交）
    inp.addEventListener('click', function (e2) { e2.stopPropagation(); });
    inp.addEventListener('pointerdown', function (e2) { e2.stopPropagation(); });
  }

  // 原生 dblclick 兜底（列表重渲染时通常不触发，见下方 pointerdown 计时判定）
  listEl.addEventListener('dblclick', function (ev) {
    var df = ev.target && ev.target.closest ? ev.target.closest('.df') : null;
    if (!df) return;
    var nRow = df.closest('.obj');
    defnEdit = { label: nRow ? nRow.getAttribute('data-label') : null };
    startDefnEdit(df);
  });

  // ---------- 编辑栏 ----------

  // 轻量选中更新（不重建对象列表 DOM）
  function setSelected(label) {
    selected = label;
    selectedMulti = [];
    updateSelectionUI();
  }
  // 框选多选：设 selectedMulti，清单选
  function setManySelection(labels) {
    selected = null;
    selectedMulti = labels.slice();
    updateSelectionUI();
  }
  // 当前选中集合（统一为数组）
  function currentSelList() {
    return selected ? [selected] : selectedMulti.slice();
  }
  // 应用选中集合（1 个 → 单选态；其它 → 多选态；空 → 清空）
  function applySelList(list) {
    var uniq = [];
    for (var ai = 0; ai < list.length; ai++) if (uniq.indexOf(list[ai]) === -1) uniq.push(list[ai]);
    if (uniq.length === 0) setSelected(null);
    else if (uniq.length === 1) setSelected(uniq[0]);
    else setManySelection(uniq);
  }
  // Ctrl/⌘ + 单击：追加（未选中）或取消（已选中）
  function toggleAddSelection(label) {
    var list = currentSelList();
    var idx = list.indexOf(label);
    if (idx >= 0) list.splice(idx, 1);
    else list.push(label);
    applySelList(list);
  }
  // Ctrl/⌘ + 框选：并入现有选择
  function unionSelection(labels) {
    var list = currentSelList();
    for (var ui = 0; ui < labels.length; ui++) if (list.indexOf(labels[ui]) === -1) list.push(labels[ui]);
    applySelList(list);
  }
  function addSelModifier(ev) {
    return !!(ev && (ev.ctrlKey || ev.metaKey));
  }
  function updateSelectionUI() {
    var rows = listEl.querySelectorAll('.obj');
    for (var ri = 0; ri < rows.length; ri++) {
      var lbl = rows[ri].getAttribute('data-label');
      rows[ri].classList.toggle('sel', lbl === selected || selectedMulti.indexOf(lbl) !== -1);
    }
    populateEditBar();
    render();
  }
  // 包围盒（屏幕坐标）
  // ---- 框选精确相交（世界坐标；线性仿射下屏幕/世界判定一致） ----
  function wrect(mx0, my0, mx1, my1) {
    // 屏幕 y 向下：转为世界后需归一化（wyp 随屏幕增减小）
    var wx0 = wxp(mx0), wx1 = wxp(mx1);
    var wy0 = wyp(my0), wy1 = wyp(my1);
    return { x0: Math.min(wx0, wx1), y0: Math.min(wy0, wy1), x1: Math.max(wx0, wx1), y1: Math.max(wy0, wy1) };
  }
  function boxHitEl(e, m) {
    if (e.kind === 'point') return wptIn(e.x, e.y, m);
    if (e.kind === 'segment') return wsegHit(e.x1, e.y1, e.x2, e.y2, m);
    if (e.kind === 'line' || e.kind === 'ray') { var s2 = e.seg; return s2 ? wsegHit(s2[0], s2[1], s2[2], s2[3], m) : false; }
    if (e.kind === 'circle') {
      var nx = Math.max(m.x0, Math.min(e.cx, m.x1)), ny = Math.max(m.y0, Math.min(e.cy, m.y1));
      var ddx = e.cx - nx, ddy = e.cy - ny;
      return ddx * ddx + ddy * ddy <= e.r * e.r;
    }
    if (e.kind === 'arc') {
      var an = 28, a0 = e.ang1, a1 = e.ang1 + e.rad;
      if (e.rad < 0) { var tv = a0; a0 = a1; a1 = tv; }
      for (var ak = 0; ak < an; ak++) {
        var ta = a0 + (a1 - a0) * ak / an, tb = a0 + (a1 - a0) * (ak + 1) / an;
        if (wsegHit(e.cx + e.r * Math.cos(ta), e.cy + e.r * Math.sin(ta),
                    e.cx + e.r * Math.cos(tb), e.cy + e.r * Math.sin(tb), m)) return true;
      }
      return false;
    }
    if (e.kind === 'polyline' && e.pts) {
      for (var pli = 0; pli < e.pts.length - 1; pli++) {
        if (wsegHit(e.pts[pli][0], e.pts[pli][1], e.pts[pli + 1][0], e.pts[pli + 1][1], m)) return true;
      }
      return false;
    }
    if (e.kind === 'polygon' && e.pts) {
      for (var pgi = 0; pgi < e.pts.length; pgi++) {
        if (wptIn(e.pts[pgi][0], e.pts[pgi][1], m)) return true;
        var nx2 = e.pts[(pgi + 1) % e.pts.length];
        if (wsegHit(e.pts[pgi][0], e.pts[pgi][1], nx2[0], nx2[1], m)) return true;
      }
      // 框中心落在多边形内部（框整体在多边形里也算接触）
      var cxm = (m.x0 + m.x1) / 2, cym = (m.y0 + m.y1) / 2;
      try { if (pointInPoly(cxm, cym, e.pts)) return true; } catch (err) {}
      return false;
    }
    return false;
  }

  function getAABB(e) {
    if (e.kind === 'point') { var x = sxp(e.x), y = syp(e.y); return [x, y, x, y]; }
    if (e.kind === 'segment') { return aabbOf(sxp(e.x1), syp(e.y1), sxp(e.x2), syp(e.y2)); }
    if (e.kind === 'circle' || e.kind === 'arc') { var cx = sxp(e.cx), cy = syp(e.cy), rr = Math.max(2, e.r * scale); return [cx - rr, cy - rr, cx + rr, cy + rr]; }
    if (e.kind === 'polygon' && e.pts) {
      var mxx = sxp(e.pts[0][0]), mnx = mxx, mxy = syp(e.pts[0][1]), mny = mxy;
      for (var ii = 1; ii < e.pts.length; ii++) {
        var xx = sxp(e.pts[ii][0]), yy = syp(e.pts[ii][1]);
        if (xx < mnx) mnx = xx; if (xx > mxx) mxx = xx;
        if (yy < mny) mny = yy; if (yy > mxy) mxy = yy;
      }
      return [mnx, mny, mxx, mxy];
    }
    if ((e.kind === 'line' || e.kind === 'ray') && e.seg) { return aabbOf(sxp(e.seg[0]), syp(e.seg[1]), sxp(e.seg[2]), syp(e.seg[3])); }
    return null;
  }
  function aabbOf(x1, y1, x2, y2) {
    return [Math.min(x1, x2), Math.min(y1, y2), Math.max(x1, x2), Math.max(y1, y2)];
  }
  function aabbHit(ab, mx0, my0, mx1, my1) {
    return ab[0] <= mx1 && ab[2] >= mx0 && ab[1] <= my1 && ab[3] >= my0;
  }


  // 3D 模式编辑栏：数据源为 els3d

  // 3D 点 x/y/z 输入 → SetCoords[label, x, y, z]
  function wireXyzInputs() {
    var xi = document.getElementById('eb-xyz-x');
    var yi = document.getElementById('eb-xyz-y');
    var zi = document.getElementById('eb-xyz-z');
    if (!xi || !yi || !zi) return;
    var apply = function () {
      if (!mode3d || !selected3d) return;
      var vx = parseFloat(xi.value), vy = parseFloat(yi.value), vz = parseFloat(zi.value);
      if (isNaN(vx) || isNaN(vy) || isNaN(vz)) return;
      postInput('SetCoords[' + selected3d + ', ' + fmtNum(vx) + ', ' + fmtNum(vy) + ', ' + fmtNum(vz) + ']');
    };
    [xi, yi, zi].forEach(function (inp) {
      inp.addEventListener('change', apply);
      inp.addEventListener('keydown', function (ev) { if (ev.key === 'Enter') { ev.preventDefault(); apply(); } });
    });
  }
  wireXyzInputs();

  function postInput(text, cb) {
    api('POST', '/api/input', {
      text: text,
      xmin: view.xmin, xmax: view.xmax, ymin: view.ymin, ymax: view.ymax
    }, function (d) {
      setMsg(d.message, !d.ok);
      if (d.elements) elements = d.elements;
      // 先回调（工具收集链依赖），再渲染；渲染异常不中断回调/后续点击
      if (cb) cb(d.ok);
      try {
        if (d.elements) render();
        if (mode3d) {
          load3d();
          if (selected3d) populateEditBar3d();
        }
      } catch (e) { /* 渲染容错 */ }
    });
  }

  function curSel() { return mode3d ? selected3d : selected; }
  var swatches = document.querySelectorAll('.sw');
  for (var si = 0; si < swatches.length; si++) {
    swatches[si].addEventListener('click', function () {
      if (!curSel()) return;
      postInput('SetColor[' + curSel() + ', ' + this.getAttribute('data-c') + ']');
    });
  }
  document.getElementById('eb-vis').addEventListener('change', function () {
    if (!curSel()) return;
    postInput('SetVisible[' + curSel() + ', ' + (this.checked ? 'true' : 'false') + ']');
  });
  document.getElementById('eb-lock').addEventListener('change', function () {
    if (!curSel()) return;
    postInput('SetLocked[' + curSel() + ', ' + (this.checked ? 'true' : 'false') + ']');
  });
  var ebWireIn = document.getElementById('eb-wire');
  if (ebWireIn) {
    ebWireIn.addEventListener('change', function () {
      if (!curSel()) return;
      postInput('SetWire[' + curSel() + ', ' + (this.checked ? 'true' : 'false') + ']');
    });
  }
  function doRedefine() {
    if (!curSel()) return;
    var defn = document.getElementById('eb-defn').value.trim();
    if (!defn) return;
    postInput('Redefine[' + curSel() + ', ' + defn + ']');
  }
  document.getElementById('eb-redef').addEventListener('click', doRedefine);
  document.getElementById('eb-defn').addEventListener('keydown', function (ev) {
    if (ev.key === 'Enter') doRedefine();
  });
  document.getElementById('eb-rename').addEventListener('click', function () {
    if (!curSel()) return;
    var name = document.getElementById('eb-name').value.trim();
    if (!name) { setMsg('请输入新标签', true); return; }
    postInput('Rename[' + curSel() + ', ' + name + ']', function (ok) {
      if (ok) {
        if (mode3d) { selected3d = name; populateEditBar3d(); }
        else selected = name;
        document.getElementById('eb-name').value = '';
      }
    });
  });
  function deleteSelection() {
    var labels = selected ? [selected] : (selectedMulti.length ? selectedMulti.slice() : []);
    if (!labels.length) return;
    var txt = labels.length === 1 ? '删除 ' + labels[0] + ' 及其依赖对象？' : '删除选中的 ' + labels.length + ' 个对象及其依赖？';
    if (!confirm(txt)) return;
    var q = labels.slice();
    (function delNext() {
      var lab = q.shift();
      if (!lab) { setSelected(null); return; }
      postInput('Delete[' + lab + ']', function () { delNext(); });
    })();
  }
  document.getElementById('eb-del').addEventListener('click', function () {
    if (mode3d) deleteSelection3d(); else deleteSelection();
  });
  document.addEventListener('keydown', function (ev) {
    var tag = document.activeElement ? document.activeElement.tagName : '';
    var inInput = tag === 'INPUT' || tag === 'TEXTAREA';
    // 对象列表键盘导航：↑/↓ 移动光标行，Enter 选择光标行（焦点不在输入框时）
    if (!inInput && (ev.key === 'ArrowUp' || ev.key === 'ArrowDown')) {
      ev.preventDefault();
      var total = mode3d ? els3d.length : elements.length;
      if (!total) return;
      if (listCursor < 0) listCursor = mode3d ? (els3d.findIndex ? Math.max(0, els3d.findIndex(function (x) { return x.visible !== false; })) : 0) : 0;
      if (ev.key === 'ArrowUp') listCursor = (listCursor <= 0) ? total - 1 : listCursor - 1;
      else listCursor = (listCursor >= total - 1) ? 0 : listCursor + 1;
      if (mode3d) renderList3d(); else renderList();
      // 光标行滚入视野
      var curRow = listEl.querySelector('.obj.cur');
      if (curRow) curRow.scrollIntoView({ block: 'nearest' });
      return;
    }
    if (!inInput && ev.key === 'Enter' && listCursor >= 0) {
      ev.preventDefault();
      var curEl = mode3d ? els3d[listCursor] : elements[listCursor];
      if (curEl) {
        if (mode3d) setSelected3d((selected3d === curEl.label) ? null : curEl.label);
        else setSelected((selected === curEl.label) ? null : curEl.label);
      }
      return;
    }
    if (ev.key === 'Delete' && !inInput) {
      if (mode3d && selected3d) deleteSelection3d();
      else if (!mode3d && (selected || selectedMulti.length)) deleteSelection();
    }
  });
  // 3D 模式删除选中的对象（Delete[标签]）
  function deleteSelection3d() {
    if (!selected3d) return;
    if (!confirm('删除 ' + selected3d + ' 及其依赖对象？')) return;
    postInput('Delete[' + selected3d + ']', function (ok) {
      if (ok) setSelected3d(null);
    });
  }

  // 画布点击：选中任意点（非自由点也可选）
  function hitAnyPoint(sx, sy) {
    for (var i = 0; i < elements.length; i++) {
      var e = elements[i];
      if (e.kind !== 'point' || e.z !== undefined) continue;
      var dx = sxp(e.x) - sx, dy = syp(e.y) - sy;
      if (dx * dx + dy * dy <= 100) return e.label;
    }
    return null;
  }
  canvas.addEventListener('pointerdown', function (ev) {
    // 在现有拖拽逻辑后：点击对象 → 选中（点含非自由点/线/线段/圆/多边形/圆弧/向量/文本/曲线）
    if (!drag && !pan && !pinch && !shiftDrag && !activeTool) {
      var hit = hitAnyPoint(ev.offsetX, ev.offsetY)
        || hitObject(ev.offsetX, ev.offsetY, ['line', 'segment', 'ray', 'circle', 'polygon', 'arc', 'vector', 'text', 'conic', 'function', 'parametric', 'polar', 'implicit', 'image']);
      if (hit) {
        // 非选择模式下自由点不拦截（走拖拽移动）；选择模式下自由点与其余对象均可点击选中（XOR）
        var isFreePoint = false;
        for (var i = 0; i < elements.length; i++) {
          if (elements[i].label === hit && elements[i].free && elements[i].kind === 'point') isFreePoint = true;
        }
        if (!isFreePoint || selectMode || addSelModifier(ev)) {
          if (addSelModifier(ev)) {
            toggleAddSelection(hit);   // Ctrl/⌘+单击：追加 / 再点取消
          } else {
            setSelected((selected === hit || selectedMulti.indexOf(hit) !== -1) ? null : hit);
          }
          ev.preventDefault();
        }
      }
    }
  });

  window.addEventListener('resize', resize);

  // ---------- 试卷导出（教师端） ----------
  var exam = {
    title: '数学测试卷', subtitle: '', school: '', klass: '', name: '', sid: '',
    total: 100, minutes: 45, instructions: '', showAnswers: false, questions: []
  };
  try {
    var savedExam = localStorage.getItem('ggb_exam');
    if (savedExam) { var parsedExam = JSON.parse(savedExam); for (var ek in parsedExam) exam[ek] = parsedExam[ek]; }
  } catch (e) {}
  function saveExam() { try { localStorage.setItem('ggb_exam', JSON.stringify(exam)); } catch (e) {} }
  var examPanel = document.getElementById('exam-panel');
  btn('btn-exam', function () {
    var show = examPanel.style.display === 'none';
    examPanel.style.display = show ? 'flex' : 'none';
    if (show) renderExam();
  });
  document.getElementById('exam-close').addEventListener('click', function () { examPanel.style.display = 'none'; });
  // 模板字段：标题/副标题/学校/班级/姓名/学号/总分/时长/说明（值变更即保存）
  var examFields = [
    ['exam-title', 'title'], ['exam-subtitle', 'subtitle'], ['exam-school', 'school'],
    ['exam-klass', 'klass'], ['exam-name', 'name'], ['exam-sid', 'sid'],
    ['exam-total', 'total'], ['exam-minutes', 'minutes'], ['exam-instructions', 'instructions']
  ];
  for (var efi = 0; efi < examFields.length; efi++) {
    (function (id, key) {
      var el = document.getElementById(id);
      el.value = exam[key];
      el.addEventListener('input', function () {
        var v = el.value;
        if (key === 'total' || key === 'minutes') { v = Math.max(1, parseInt(v, 10) || 1); el.value = v; }
        exam[key] = v; saveExam();
      });
    })(examFields[efi][0], examFields[efi][1]);
  }
  var examAnsBox = document.getElementById('exam-answers');
  examAnsBox.checked = exam.showAnswers;
  examAnsBox.addEventListener('change', function () { exam.showAnswers = examAnsBox.checked; saveExam(); });
  // 捕获当前画布为题目图（白底 + 降采样 JPEG，控制 localStorage 体积）
  function captureCanvas() {
    var c = mode3d ? cv3d : canvas;
    var maxW = 900;
    var tw = Math.min(c.width, maxW), th = Math.max(1, Math.round(c.height * tw / c.width));
    var t = document.createElement('canvas');
    t.width = tw; t.height = th;
    var tc = t.getContext('2d');
    tc.fillStyle = '#fff'; tc.fillRect(0, 0, tw, th);
    tc.drawImage(c, 0, 0, tw, th);
    try { return t.toDataURL('image/jpeg', 0.82); } catch (e) { return ''; }
  }
  document.getElementById('exam-add').addEventListener('click', function () {
    var img = captureCanvas();
    if (!img) { setMsg('错误: 画布导出失败', true); return; }
    exam.questions.push({ img: img, text: '', score: 5, answer: '' });
    saveExam(); renderExam();
  });
  var examQEl = document.getElementById('exam-questions');
  examQEl.addEventListener('click', function (ev) {
    var b2 = ev.target.closest('button[data-act]');
    if (!b2) return;
    var row = b2.closest('.eq');
    if (!row) return;
    var i = +row.getAttribute('data-i');
    var act = b2.getAttribute('data-act');
    if (act === 'del') { exam.questions.splice(i, 1); }
    else if (act === 'up' && i > 0) { var t2 = exam.questions[i]; exam.questions[i] = exam.questions[i - 1]; exam.questions[i - 1] = t2; }
    else if (act === 'down' && i < exam.questions.length - 1) { var t3 = exam.questions[i]; exam.questions[i] = exam.questions[i + 1]; exam.questions[i + 1] = t3; }
    else return;
    saveExam(); renderExam();
  });
  examQEl.addEventListener('input', function (ev) {
    var row = ev.target.closest('.eq');
    if (!row) return;
    var i = +row.getAttribute('data-i');
    var q = exam.questions[i];
    if (!q) return;
    if (ev.target.classList.contains('eq-text')) {
      if (ev.target.classList.contains('eq-ans')) q.answer = ev.target.value;
      else q.text = ev.target.value;
    } else if (ev.target.classList.contains('eq-score')) {
      q.score = Math.max(0, parseInt(ev.target.value, 10) || 0);
    }
    saveExam();
  });
  document.getElementById('exam-clear').addEventListener('click', function () {
    if (!exam.questions.length) return;
    if (!confirm(t('exam_confirm'))) return;
    exam.questions = [];
    saveExam(); renderExam();
  });
  document.getElementById('exam-export').addEventListener('click', exportExam);

  // ---------- 虚拟数学键盘（面板行为见 static/keyboard.js） ----------
  var kb = window.GGB_KB ? window.GGB_KB.init() : null;

  // ---------- 几何工具（画布交互创建） ----------
  var TOOLS = GGB_DATA.TOOLS || {};
  // 工具分类（按点/线/面/圆/圆锥曲线/变换/视图等分组，用类别图标可视化）
  var TOOL_CATS = GGB_DATA.TOOL_CATS || [];
  // ---------- 顶部下拉菜单（文件/导出/导入/视图/工具）----------
  (function initMenus() {
    var menus = document.querySelectorAll('#toolbar .menu');
    function closeAll(except) {
      for (var i = 0; i < menus.length; i++) if (menus[i] !== except) menus[i].classList.remove('open');
    }
    for (var i = 0; i < menus.length; i++) {
      (function (m) {
        var head = m.querySelector('.menu-btn');
        var list = m.querySelector('.menu-list');
        if (!head || !list) return;
        head.addEventListener('click', function (ev) {
          ev.stopPropagation();
          var willOpen = !m.classList.contains('open');
          closeAll(null);
          if (willOpen) m.classList.add('open');
        });
        // 点条目后收起菜单（具体动作由各按钮自己的 handler 完成）
        list.addEventListener('click', function () { m.classList.remove('open'); });
      })(menus[i]);
    }
    document.addEventListener('click', function () { closeAll(null); });
    document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') closeAll(null); });
  })();

  // 顶部横向分类图标工具栏（GeoGebra 式）
  var activeCat = null;


  var activeTool = null;
  var toolSel = [];
  var toolPanel = document.getElementById('tools-panel');
  var toolStatus = document.getElementById('tool-status');
  var hintEl = document.getElementById('hint');
  function toolHintText() {
    var T = TOOLS[activeTool];
    if (!T) return '';
    var arr = lang === 'en' ? T.en : T.hints;
    return arr[Math.min(toolSel.length, arr.length - 1)];
  }
  function setToolStatus() {
    toolStatus.textContent = toolHintText();
    render();   // 选中对象后立即显示高亮（工具进行中的已选反馈）
  }
  function startTool(name) {
    // 作图工具与选择模式互斥：激活工具时自动退出选择
    if (selectMode) setSelectMode(false);
    if (name !== 'image') pendingImage = null;   // 切换到其它工具时丢弃待插入图片
    if (name === 'image') { var _f = document.getElementById('imgfile'); if (_f) _f.click(); }
    activeTool = name;
    toolSel = [];
    updateToolButtons();
    setToolStatus();
    hintEl.textContent = toolHintText();
  }
  function setSelectMode(on) {
    selectMode = !!on;
    var sb = document.getElementById('btn-select');
    if (sb) sb.classList.toggle('active', selectMode);
    if (!selectMode) {
      if (activeTool) { activeTool = null; toolSel = []; updateToolButtons(); setToolStatus(); hintEl.textContent = t('hint'); }
      selected = null; selectedMulti = [];
      updateSelectionUI();
    } else {
      setMsg(lang === 'en'
        ? 'Select: click / drag a box; hold Ctrl and click to add to selection'
        : '选择：单击或框选；按住 Ctrl 单击可追加选中', false);
    }
  }
  function cancelTool() {
    activeTool = null;
    toolSel = [];
    updateToolButtons();
    toolStatus.textContent = '';
    hintEl.textContent = t('hint');
  }
  // 重置当前工具（创建成功后保持激活，支持连续操作；Esc/再点按钮退出）
  function closeOtherPanels(exceptId) {
    var ids = ['cas-panel', 'exam-panel', 'tools-panel', 'script-panel'];
    for (var pi = 0; pi < ids.length; pi++) {
      if (ids[pi] !== exceptId) document.getElementById(ids[pi]).style.display = 'none';
    }
  }
  btn('btn-tools', function () {
    var show = toolPanel.style.display === 'none';
    closeOtherPanels('tools-panel');
    toolPanel.style.display = show ? 'flex' : 'none';
    if (show) { renderToolsPanel(); updateToolButtons(); setToolStatus(); }
  });
  // 顶部横向分类图标工具栏交互
  function activateDefaultTool(cat) {
    // 点分类即激活该分类缺省常用工具（减少一次点击）：再点同分类 = 退出
    if (!cat || !cat.def) return;
    if (mode3d) {
      if (cat.id === 'd3') {
        var b3 = document.querySelector('#cat-tools .tool-btn[data-tool="' + cat.def + '"]');
        if (b3) { if (tool3d === cat.def) resetTool3d(); else b3.click(); }
      }
      return;
    }
    if (activeTool !== cat.def) startTool(cat.def);   // 已激活同工具则保持；startTool 会自动退出选择模式
  }
  document.getElementById('catbar').addEventListener('click', function (ev) {
    var ic = ev.target.closest('.cat-icon');
    if (ic) {
      var cid = ic.getAttribute('data-cat');
      showCat(cid);
      for (var ai = 0; ai < TOOL_CATS.length; ai++) if (TOOL_CATS[ai].id === cid) activateDefaultTool(TOOL_CATS[ai]);
    }
  });
  var catToolsBox = document.getElementById('cat-tools');
  catToolsBox.addEventListener('click', function (ev) {
    var b = ev.target.closest('.tool-btn[data-tool]');
    if (b) {
      var name = b.getAttribute('data-tool');
      // 3D 模式：3D 工具由 tool3d 系统接管（已在前面 handler 中激活）
      if (mode3d && ['pt3d', 'seg3d', 'line3d', 'plane3d', 'sphere3d', 'cube3d', 'cone3d', 'cylinder3d', 'prism3d', 'pyramid3d', 'tetra3d', 'octa3d', 'hexa3d', 'icosa3d', 'dodeca3d'].indexOf(name) !== -1) return;
      if (isChartTool(name)) { chartToolPrompt(name); return; }   // 统计图：点按钮即输入数据
      if (activeTool === name) cancelTool();
      else startTool(name);
      return;
    }
    if (ev.target.closest('#tool-done')) {
      if (activeTool === 'polyline') finishPolyline();
      else finishPolygon();
    }
  });
  renderCatbar();
  showCat(TOOL_CATS[0].id);  // 默认展示'点'类
  btn('btn-select', function () {
    var next = !selectMode;
    if (next) {
      // 进入选择：清除当前作图工具与 3D 工具，避免二者同时有效
      if (activeTool) cancelTool();
      if (tool3d) resetTool3d();
    }
    setSelectMode(next);
    if (next) render();
  });
  document.getElementById('tools-close').addEventListener('click', function () {
    toolPanel.style.display = 'none'; cancelTool();
  });
  toolPanel.addEventListener('click', function (ev) {
    var b = ev.target.closest('.tool-btn[data-tool]');
    if (b) {
      var name = b.getAttribute('data-tool');
      if (isChartTool(name)) { chartToolPrompt(name); return; }
      if (activeTool === name) cancelTool();
      else startTool(name);
      return;
    }
    if (ev.target.closest('#tool-done')) {
      if (activeTool === 'polyline') finishPolyline();
      else finishPolygon();
      return;
    }
  });
  document.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape' && activeTool) cancelTool();
    if (ev.key === 'Escape' && tool3d) resetTool3d();
    if (ev.key === 'Escape' && macroPickMode) {
      macroPickMode = null;
      var pi = document.getElementById('macro-pick-in'), po = document.getElementById('macro-pick-out');
      if (pi) pi.classList.remove('active');
      if (po) po.classList.remove('active');
    }
  });
  function fmtW(v) {
    var s = (+v).toFixed(4);
    return s.replace(/0+$/, '').replace(/\.$/, '');
  }
  // 点击画布：命中已有对象 → 用之；空白 → 创建自由点（自动命名）。
  // 请求队列：连续快击时若上一次建点未返回，排队处理，保证点标签与顺序稳定。
  var toolBusy = false, toolPointQueue = [];
  // 吸附命中：命中已有点返回其 label，空白返回 null
  // 选中对象整体拖动：本地乐观平移

  // 屏幕坐标射线法：点是否在多边形内

  // 动点在其母体对象上的最近参数 t（PointOnPath/PointOnCircle 的驱动滑块值）
  // 拖动动点：把其驱动参数滑块更新为母体上最近点对应的 t
  function dragPathPoint(pLabel, wx, wy) {
    var el = null;
    for (var i = 0; i < elements.length; i++) if (elements[i].label === pLabel) { el = elements[i]; break; }
    if (!el) return false;
    var m = (el.defn || '').match(/PointOn(?:Path|Circle)\[([^,]+),([^\]]+)\]/);
    if (!m) return false;
    var objLabel = m[1].trim(), tLabel = m[2].trim();
    var obj = null;
    for (var j = 0; j < elements.length; j++) if (elements[j].label === objLabel) { obj = elements[j]; break; }
    var t = nearestPathParam(obj, wx, wy);
    if (t === null) return false;
    api('POST', '/api/drag', { label: tLabel, x: t, y: 0, push: false, xmin: view.xmin, xmax: view.xmax, ymin: view.ymin, ymax: view.ymax }, function (d) {
      if (d && d.elements) { elements = d.elements; render(); }
    });
    return true;
  }

  function findEl(label) {
    for (var i = 0; i < elements.length; i++) if (elements[i].label === label) return elements[i];
    return null;
  }
  // ---- 五点圆锥曲线预览：6 元齐次 nullspace + marching 三角形 ----
  // 工具绘制中的预览形状（部分参数完成 → 随鼠标临时图形）

  function finishPolygon() {
    if (toolSel.length < 3) return;
    var fCmd = activeTool === 'rigidpolygon' ? 'RigidPolygon' : 'Polygon';
    postInput(fCmd + '[' + toolSel.join(',') + ']', function (ok) { if (ok) resetTool(); });
  }
  function finishPolyline() {
    if (toolSel.length < 2) return;
    postInput('Polyline[' + toolSel.join(',') + ']', function (ok) { if (ok) resetTool(); });
  }

  // ---------- 命令脚本（批量执行） ----------
  var scriptPanel = document.getElementById('script-panel');
  btn('btn-script', function () {
    var show = scriptPanel.style.display === 'none';
    closeOtherPanels('script-panel');
    scriptPanel.style.display = show ? 'flex' : 'none';
  });
  document.getElementById('script-close').addEventListener('click', function () { scriptPanel.style.display = 'none'; });
  document.getElementById('script-file').addEventListener('click', function () {
    document.getElementById('script-file-input').click();
  });
  document.getElementById('script-file-input').addEventListener('change', function (ev) {
    var f = ev.target.files[0];
    if (!f) return;
    var rd = new FileReader();
    rd.onload = function () { document.getElementById('script-ta').value = rd.result; };
    rd.readAsText(f);
  });
  function runScript() {
    var text = document.getElementById('script-ta').value;
    if (!text.trim()) return;
    api('POST', '/api/batch', {
      script: text, xmin: view.xmin, xmax: view.xmax, ymin: view.ymin, ymax: view.ymax
    }, function (d) {
      if (!d) return;
      if (d.elements) { elements = d.elements; render(); }
      var s = '';
      for (var i = 0; i < d.results.length; i++) {
        var r = d.results[i];
        s += '<div class="sres ' + (r.ok ? 'ok' : 'fail') + '"><span class="sno">' + r.no + '</span>'
          + esc(r.line) + ' → ' + esc(r.message || '—') + '</div>';
      }
      document.getElementById('script-results').innerHTML = s;
      setMsg((lang === 'en' ? 'Script done: ' : '脚本执行完成：') + (d.script_ok || 0) + ' 条成功', !d.ok);
    });
  }
  document.getElementById('script-run').addEventListener('click', runScript);
  document.getElementById('script-ta').addEventListener('keydown', function (ev) {
    if (ev.key === 'Enter' && (ev.ctrlKey || ev.metaKey)) { ev.preventDefault(); runScript(); }
  });

  // ---------- 自定义宏（Macro） ----------
  var macroPanel = document.getElementById('macro-panel');
  var macroPickMode = null;   // 'input' | 'output' | null：画布点选宏输入/输出对象
  // 画布点击 → 点选模式：把命中对象标签加入输入/输出框
  function handleMacroPick(label) {
    if (!macroPickMode) return;
    var input = document.getElementById(macroPickMode === 'input' ? 'macro-inputs' : 'macro-outputs');
    if (!input) return;
    var list = input.value.split(',').map(function (s) { return s.trim(); }).filter(Boolean);
    if (list.indexOf(label) === -1) list.push(label);
    input.value = list.join(', ');
    // 保持点选模式：可连续选多个对象；再点「点选」按钮或 Esc 退出
    setMsg((lang === 'en' ? 'Picked ' : '已选 ') + label + (lang === 'en' ? ' (click more or Esc to finish)' : '（可继续点选，Esc 结束）'));
  }
  function wireMacroPick(btnId, mode) {
    document.getElementById(btnId).addEventListener('click', function () {
      macroPickMode = (macroPickMode === mode) ? null : mode;
      document.getElementById('macro-pick-in').classList.toggle('active', macroPickMode === 'input');
      document.getElementById('macro-pick-out').classList.toggle('active', macroPickMode === 'output');
      setMsg(macroPickMode ? (lang === 'en' ? 'Click an object on canvas to pick' : '点击画布对象进行点选') : '');
    });
  }
  wireMacroPick('macro-pick-in', 'input');
  wireMacroPick('macro-pick-out', 'output');
  function refreshMacroList() {
    fetch('/api/macro').then(function (r) { return r.json(); }).then(function (d) {
      var box = document.getElementById('macro-list');
      var ms = (d && d.macros) || [];
      if (!ms.length) { box.innerHTML = '<div class="macro-empty" data-i18n="macro_empty">暂无宏</div>'; return; }
      var s = '<div class="macro-item-head">' + t('macro_list') + '</div>';
      for (var i = 0; i < ms.length; i++) {
        var m = ms[i];
        s += '<div class="macro-item" data-macro="' + esc(m.name) + '"><b>' + esc(m.name) + '</b>'
          + '<span class="macro-params">(' + esc(m.params.join(', ')) + ')</span>'
          + '<span class="macro-outs">' + t('macro_outs') + ' ' + m.n_outputs + '</span>'
          + '<button class="macro-del" data-del="' + esc(m.name) + '" title="删除">✕</button></div>';
      }
      box.innerHTML = s;
      box.querySelectorAll('.macro-del').forEach(function (b2) {
        b2.addEventListener('click', function (ev) {
          ev.stopPropagation();
          api('POST', '/api/macro/delete', { name: b2.getAttribute('data-del') }, function (d2) {
            setMsg(d2.message, !d2.ok); refreshMacroList();
          });
        });
      });
    }).catch(function () {});
  }
  btn('btn-macro', function () {
    var show = macroPanel.style.display === 'none';
    closeOtherPanels('macro-panel');
    macroPanel.style.display = show ? 'flex' : 'none';
    if (show) { refreshMacroList(); }
  });
  document.getElementById('macro-close').addEventListener('click', function () { macroPanel.style.display = 'none'; });
  document.getElementById('macro-create').addEventListener('click', function () {
    var name = document.getElementById('macro-name').value.trim();
    var inputs = document.getElementById('macro-inputs').value.split(',').map(function (s) { return s.trim(); }).filter(Boolean);
    var outputs = document.getElementById('macro-outputs').value.split(',').map(function (s) { return s.trim(); }).filter(Boolean);
    if (!name || !outputs.length) { setMsg(t('macro_err_empty'), true); return; }
    api('POST', '/api/macro/create', { name: name, inputs: inputs, outputs: outputs }, function (d) {
      setMsg(d.message, !d.ok);
      document.getElementById('macro-msg').innerHTML = '<div class="macro-defns">' + esc(JSON.stringify((d.macro||{}).defns || [])) + '</div>';
      if (d.ok) { refreshMacroList(); }
    });
  });
  document.getElementById('macro-run').addEventListener('click', function () {
    var name = document.getElementById('macro-use-name').value.trim();
    var args = document.getElementById('macro-use-args').value.split(',').map(function (s) { return s.trim(); }).filter(Boolean);
    if (!name) { setMsg(t('macro_err_name'), true); return; }
    api('POST', '/api/macro/run', { name: name, args: args }, function (d) {
      setMsg(d.message, !d.ok);
      if (d.ok && d.elements) { elements = d.elements; render(); }
      refreshMacroList();
    });
  });

  // ---------- 分享链接加载（?s=ID） ----------
  (function () {
    var s = new URLSearchParams(location.search).get('s');
    if (!s) return;
    fetch('/api/shared/' + encodeURIComponent(s)).then(function (r) { return r.json(); }).then(function (d) {
      if (!d || !d.ok || !d.content) { setMsg('分享内容无效或已过期', true); return; }
      return fetch('/api/load', { method: 'POST', headers: { 'Content-Type': 'text/plain' }, body: d.content })
        .then(function (r) { return r.json(); });
    }).then(function (ld) {
      if (!ld) return;
      if (ld.view) { view.xmin = ld.view[0]; view.xmax = ld.view[1]; view.ymin = ld.view[2]; view.ymax = ld.view[3]; }
      if (ld.elements) elements = ld.elements;
      render();
      history.replaceState(null, '', location.pathname);
      setMsg(ld.message || '已加载', !ld.ok);
    }).catch(function () { setMsg('无法加载分享内容', true); });
  })();

  applyLang();
  resize();
})();
