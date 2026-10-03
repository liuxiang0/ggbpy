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
  function translateMsg(m) {
    if (lang !== 'en' || !m) return m;
    var body = m, prefix = '';
    if (m.indexOf('OK:已创建') === 0) { prefix = 'Created: '; body = m.slice(6); }
    else if (m.indexOf('错误: ') === 0) { prefix = 'Error: '; body = m.slice(4); }
    else if (m.indexOf('CAS: ') === 0) { prefix = 'CAS: '; body = m.slice(5); }
    else if (m.indexOf('CAS 错误') === 0) return 'CAS error';
    else if (m.indexOf('网络错误: ') === 0) { prefix = 'Network error: '; body = m.slice(6); }
    else if (m.indexOf('加载失败: ') === 0) { prefix = 'Load failed: '; body = m.slice(6); }
    else if (m.indexOf('已创建 ') === 0) { prefix = 'Created: '; body = m.slice(4); }
    else {
      for (var k in MSG_MAP_EN) {
        if (m.indexOf(k) === 0) return MSG_MAP_EN[k] + m.slice(k.length);
      }
    }
    for (var i = 0; i < RE_MAP_EN.length; i++) {
      if (RE_MAP_EN[i][0].test(body)) { body = body.replace(RE_MAP_EN[i][0], RE_MAP_EN[i][1]); break; }
    }
    return prefix + body;
  }

  btn('btn-lang', function () {
    lang = (lang === 'zh') ? 'en' : 'zh';
    localStorage.setItem('ggb_lang', lang);
    applyLang();
    renderCatbar();
    if (activeCat) showCat(activeCat);
    render();
  });
  function gcdInt(a, b) { a = Math.abs(a); b = Math.abs(b); while (b) { var t = a % b; a = b; b = t; } return a || 1; }
  function angleUnit() { return localStorage.getItem('ggb_angle_unit') === 'rad' ? 'rad' : 'deg'; }
  function fmtAngleDeg(deg) {
    var v = ((deg % 360) + 360) % 360;
    if (angleUnit() !== 'rad') return Math.round(v) + '°';
    var rad = v * Math.PI / 180;
    for (var dd = 1; dd <= 24; dd++) {
      var nn = rad * dd / Math.PI;
      var rr = Math.round(nn);
      if (Math.abs(nn - rr) < COARSE) {
        var gg = gcdInt(rr, dd);
        var n2 = rr / gg, d2 = dd / gg;
        var s = n2 === 1 ? '' : (n2 === -1 ? '-' : String(n2));
        return s + 'π' + (d2 === 1 ? '' : '/' + d2);
      }
    }
    return (Math.round(rad * 1000) / 1000) + ' rad';
  }
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

  function viewParams() {
    return '?xmin=' + view.xmin.toFixed(4) + '&xmax=' + view.xmax.toFixed(4) +
           '&ymin=' + view.ymin.toFixed(4) + '&ymax=' + view.ymax.toFixed(4);
  }

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
      case 'C': return C;
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
      case 'selected': return selected;
      case 'selected3d': return selected3d;
      case 'selectedMulti': return selectedMulti;
      case 'tool3d': return tool3d;
      case 'toolSel': return toolSel;
      default: return undefined;
    }
  }
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
  }
  var _panels = window.GGB_PANELS.create({ get: _panelStateGet, set: _panelStateSet });
  function t() { return _panels.t.apply(null, arguments); }
  function esc() { return _panels.esc.apply(null, arguments); }
  function fmtNum() { return _panels.fmtNum.apply(null, arguments); }
  function findEl() { return _panels.findEl.apply(null, arguments); }
  function findEl3d() { return _panels.findEl3d.apply(null, arguments); }
  function solidLabelName() { return _panels.solidLabelName.apply(null, arguments); }
  function applyLang() { return _panels.applyLang.apply(null, arguments); }
  function renderList() { return _panels.renderList.apply(null, arguments); }
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
  function drawSelectionOverlay(e) {
    if (!e || e.visible === false) return;
    ctx.save();
    ctx.strokeStyle = '#f59e0b';
    ctx.lineWidth = 3;
    ctx.setLineDash([6, 4]);
    ctx.beginPath();
    var poly = null, polys = null, i3;
    if (e.kind === 'segment') {
      ctx.moveTo(sxp(e.x1), syp(e.y1)); ctx.lineTo(sxp(e.x2), syp(e.y2));
    } else if ((e.kind === 'line' || e.kind === 'ray') && e.seg) {
      ctx.moveTo(sxp(e.seg[0]), syp(e.seg[1])); ctx.lineTo(sxp(e.seg[2]), syp(e.seg[3]));
    } else if (e.kind === 'circle') {
      ctx.arc(sxp(e.cx), syp(e.cy), Math.max(2, e.r * scale), 0, Math.PI * 2);
    } else if (e.kind === 'arc') {
      var acx2 = sxp(e.cx), acy2 = syp(e.cy), ar2 = Math.max(2, e.r * scale);
      ctx.arc(acx2, acy2, ar2, -e.ang1, -e.ang2, true);
    } else if (e.kind === 'polygon' && e.pts && e.pts.length >= 2) {
      ctx.moveTo(sxp(e.pts[0][0]), syp(e.pts[0][1]));
      for (i3 = 1; i3 < e.pts.length; i3++) ctx.lineTo(sxp(e.pts[i3][0]), syp(e.pts[i3][1]));
      ctx.closePath();
    } else if (e.kind === 'image' && e.corners && e.corners.length === 4) {
      ctx.moveTo(sxp(e.corners[0][0]), syp(e.corners[0][1]));
      for (i3 = 1; i3 < 4; i3++) ctx.lineTo(sxp(e.corners[i3][0]), syp(e.corners[i3][1]));
      ctx.closePath();
    } else if (e.kind === 'point') {
      ctx.arc(sxp(e.x), syp(e.y), 8.5, 0, Math.PI * 2);
    } else if (e.kind === 'polyline' || e.kind === 'locus') {
      poly = e.pts || [];
      if (poly.length < 2) { ctx.restore(); return; }
      ctx.moveTo(sxp(poly[0][0]), syp(poly[0][1]));
      for (i3 = 1; i3 < poly.length; i3++) ctx.lineTo(sxp(poly[i3][0]), syp(poly[i3][1]));
    } else if (e.kind === 'vector') {
      ctx.moveTo(sxp(e.sx || 0), syp(e.sy || 0));
      ctx.lineTo(sxp((e.sx || 0) + e.dx), syp((e.sy || 0) + e.dy));
    } else if (e.kind === 'function' && e.samples) {
      var startedF = false;
      for (i3 = 0; i3 < e.samples.length; i3++) {
        var sy3 = e.samples[i3][1];
        if (sy3 === null || !isFinite(sy3)) { startedF = false; continue; }
        if (!startedF) { ctx.moveTo(sxp(e.samples[i3][0]), syp(sy3)); startedF = true; }
        else ctx.lineTo(sxp(e.samples[i3][0]), syp(sy3));
      }
    } else if ((e.kind === 'parametric' || e.kind === 'polar') && e.pts && e.pts.length >= 2) {
      ctx.moveTo(sxp(e.pts[0][0]), syp(e.pts[0][1]));
      for (i3 = 1; i3 < e.pts.length; i3++) ctx.lineTo(sxp(e.pts[i3][0]), syp(e.pts[i3][1]));
    } else if (e.kind === 'implicit' && e.segs) {
      for (i3 = 0; i3 < e.segs.length; i3++) {
        ctx.moveTo(sxp(e.segs[i3][0]), syp(e.segs[i3][1]));
        ctx.lineTo(sxp(e.segs[i3][2]), syp(e.segs[i3][3]));
      }
    } else if (e.kind === 'conic') {
      if (e.segs) {
        for (i3 = 0; i3 < e.segs.length; i3++) {
          ctx.moveTo(sxp(e.segs[i3][0]), syp(e.segs[i3][1]));
          ctx.lineTo(sxp(e.segs[i3][2]), syp(e.segs[i3][3]));
        }
      } else {
        polys = conicPathPts(e);
        for (var cp3 = 0; cp3 < polys.length; cp3++) {
          var pp3 = polys[cp3];
          if (pp3.length < 2) continue;
          ctx.moveTo(sxp(pp3[0][0]), syp(pp3[0][1]));
          for (i3 = 1; i3 < pp3.length; i3++) ctx.lineTo(sxp(pp3[i3][0]), syp(pp3[i3][1]));
        }
      }
    } else {
      ctx.restore();
      return;
    }
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.restore();
  }

  // 坐标轴覆盖层：箭头、x/y 标签、原点 O（在元素之上绘制）
  function drawOverlay() {
    if (!showAxes) return;
    var oy = syp(0), ox = sxp(0);
    var axIn = ox >= -50 && ox <= cssW + 50;
    var ayIn = oy >= -50 && oy <= cssH + 50;
    if (!axIn && !ayIn) return;

    // x 轴箭头（右端）+ 标签 x
    if (ayIn && view.xmin < 0 && view.xmax > 0) {
      var ax = cssW - 16;
      ctx.fillStyle = C.axis;
      ctx.beginPath();
      ctx.moveTo(ax - 4, oy - 5);
      ctx.lineTo(ax + 6, oy);
      ctx.lineTo(ax - 4, oy + 5);
      ctx.closePath();
      ctx.fill();
      ctx.fillStyle = C.axis;
      ctx.font = 'italic 15px serif';
      ctx.textAlign = 'right';
      ctx.textBaseline = 'bottom';
      ctx.fillText('x', ax - 8, oy - 6);   // 左移进画布 + 上移到 x 轴上方
    }
    // y 轴箭头（顶端）+ 标签 y
    if (axIn && view.ymin < 0 && view.ymax > 0) {
      var ay = 16;
      ctx.fillStyle = C.axis;
      ctx.beginPath();
      ctx.moveTo(ox - 5, ay + 4);
      ctx.lineTo(ox, ay - 6);
      ctx.lineTo(ox + 5, ay + 4);
      ctx.closePath();
      ctx.fill();
      ctx.fillStyle = C.axis;
      ctx.font = 'italic 15px serif';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'bottom';
      ctx.fillText('y', ox + 10, ay + 22);  // 下移且右偏：原 ay-12 超出画布顶；与轴线错开避免重叠
    }
    // 原点 O：特有的标记点（灰点 + 深色圆环 + 标签）
    if (axIn && ayIn && view.xmin <= 0 && view.xmax >= 0 && view.ymin <= 0 && view.ymax >= 0) {
      ctx.fillStyle = C.tick;
      ctx.beginPath();
      ctx.arc(ox, oy, 4.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = C.axis;
      ctx.lineWidth = 1.6;
      ctx.beginPath();
      ctx.arc(ox, oy, 4.5, 0, Math.PI * 2);
      ctx.stroke();
      ctx.fillStyle = C.axis;
      ctx.font = '13px sans-serif';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'top';
      ctx.fillText('O', ox + 7, oy + 4);
    }
  }

  function colorOf(e) {
    // 锁定对象：统一灰色，表示不可移动/编辑
    if (e.locked) return '#9ca3af';
    var m = { line: '#2563eb', segment: '#059669', ray: '#0d9488', circle: '#7c3aed',
              polygon: '#3b82f6', polyline: '#0d9488', function: '#0f766e', point: '#dc2626', vector: '#b45309',
              conic: '#7c3aed', inequality: '#3b82f6', arc: '#7c3aed' };
    return m[e.kind] || C.text;
  }


  // ---- 图片对象：缓存 + 按两基点仿射绘制 ----
  var imgCache = {};   // imgid -> HTMLImageElement
  function getImage(iid) {
    if (!iid) return null;
    if (imgCache[iid]) return imgCache[iid];
    var im = new Image();
    im._ready = false;
    im.onload = function () { im._ready = true; render(); };
    im.onerror = function () { im._error = true; };
    im.src = '/api/image/' + encodeURIComponent(iid);
    imgCache[iid] = im;
    return im;
  }
  function drawImageEl(e) {
    var cs = e.corners || [];
    if (cs.length < 4) return;
    var sBL = [sxp(cs[0][0]), syp(cs[0][1])];   // 左下
    var sBR = [sxp(cs[1][0]), syp(cs[1][1])];   // 右下
    var sTR = [sxp(cs[2][0]), syp(cs[2][1])];   // 右上
    var sTL = [sxp(cs[3][0]), syp(cs[3][1])];   // 左上
    var im = getImage(e.imgid);
    if (im && im._ready && im.naturalWidth > 0) {
      var wpx = im.naturalWidth, hpx = im.naturalHeight;
      ctx.save();
      // 图像像素坐标 → 屏幕： (0,0)=TL, (wpx,0)=TR, (0,hpx)=BL
      var m11 = (sTR[0] - sTL[0]) / wpx, m12 = (sTR[1] - sTL[1]) / wpx;
      var m21 = (sBL[0] - sTL[0]) / hpx, m22 = (sBL[1] - sTL[1]) / hpx;
      ctx.transform(m11, m12, m21, m22, sTL[0], sTL[1]);
      try { ctx.drawImage(im, 0, 0, wpx, hpx); } catch (err) {}
      ctx.restore();
    } else {
      // 加载中/失败：浅色占位框
      ctx.fillStyle = 'rgba(148,163,184,.22)';
      ctx.beginPath();
      ctx.moveTo(sBL[0], sBL[1]); ctx.lineTo(sBR[0], sBR[1]);
      ctx.lineTo(sTR[0], sTR[1]); ctx.lineTo(sTL[0], sTL[1]);
      ctx.closePath(); ctx.fill();
    }
    ctx.strokeStyle = 'rgba(100,116,139,.85)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(sBL[0], sBL[1]); ctx.lineTo(sBR[0], sBR[1]);
    ctx.lineTo(sTR[0], sTR[1]); ctx.lineTo(sTL[0], sTL[1]);
    ctx.closePath(); ctx.stroke();
  }

  function drawElement(e) {
    if (e.visible === false) return;   // 隐藏对象（如刚性多边形的非手柄顶点）不渲染
    var i, j;
    if (e.kind === 'polygon' && e.pts && e.pts.length >= 2) {
      ctx.fillStyle = 'rgba(59,130,246,.10)';
      ctx.strokeStyle = colorOf(e);
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(sxp(e.pts[0][0]), syp(e.pts[0][1]));
      for (i = 1; i < e.pts.length; i++) ctx.lineTo(sxp(e.pts[i][0]), syp(e.pts[i][1]));
      ctx.closePath();
      ctx.fill(); ctx.stroke();
    }
    if (e.kind === 'circle') {
      ctx.strokeStyle = colorOf(e);
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(sxp(e.cx), syp(e.cy), Math.max(0.5, e.r * scale), 0, Math.PI * 2);
      ctx.stroke();
    }
    if (e.kind === 'line' && e.seg) strokeSeg(e.seg[0], e.seg[1], e.seg[2], e.seg[3], colorOf(e));
    if (e.kind === 'segment') strokeSeg(e.x1, e.y1, e.x2, e.y2, colorOf(e));
    if (e.kind === 'ray' && e.seg) strokeSeg(e.seg[0], e.seg[1], e.seg[2], e.seg[3], colorOf(e));
    if (e.kind === 'function' && e.samples) {
      ctx.strokeStyle = colorOf(e);
      ctx.lineWidth = 2.2;
      ctx.beginPath();
      var started = false;
      for (j = 0; j < e.samples.length; j++) {
        var x = e.samples[j][0], y = e.samples[j][1];
        if (y === null || !isFinite(y) || Math.abs(y) > 1e9) { started = false; continue; }
        if (!started) { ctx.moveTo(sxp(x), syp(y)); started = true; }
        else ctx.lineTo(sxp(x), syp(y));
      }
      ctx.stroke();
    }
    if (e.kind === 'image') drawImageEl(e);
    if (e.kind === 'conic') drawConic(e);
    if (e.kind === 'inequality') drawInequality(e);
    if (e.kind === 'angle') {
      var cx2 = sxp(e.cx), cy2 = syp(e.cy);
      var r2 = Math.max(12, e.arc_r * scale);
      ctx.strokeStyle = '#7c3aed';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(cx2, cy2, r2, -e.ang1, -e.ang1 - e.rad, true);   // y-down 映射：世界 CCW → 视觉仍 CCW
      ctx.stroke();
      var mid = e.ang1 + e.rad / 2;
      var lx = cx2 + r2 * 1.45 * Math.cos(mid);
      var ly = cy2 - r2 * 1.45 * Math.sin(mid);
      ctx.fillStyle = '#7c3aed';
      ctx.font = '12px sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(fmtAngleDeg(e.deg), lx, ly);
    }
    if (e.kind === 'text') {
      var tx = sxp(e.x), ty = syp(e.y);
      ctx.font = '15px sans-serif';
      ctx.fillStyle = C.label;
      ctx.textAlign = 'left';
      ctx.textBaseline = 'bottom';
      ctx.fillText(e.content, tx, ty);
    }
    if (e.kind === 'barchart') drawBarChart(e);
    if (e.kind === 'boxplot' && e.five) drawBoxPlot(e);
    if (e.kind === 'sumrect' && e.rects && e.rects.length) {
      // 黎曼和条带（矩形/梯形）；函数曲线另由 function 分支绘制
      ctx.fillStyle = 'rgba(15,118,110,.20)';
      ctx.strokeStyle = '#0f766e';
      ctx.lineWidth = 1.2;
      for (var sri = 0; sri < e.rects.length; sri++) {
        var rc = e.rects[sri];
        var rx0p = sxp(rc[0]), rx1p = sxp(rc[1]);
        var yHi, yLo;
        if (rc.length >= 4) { yHi = Math.max(rc[2], rc[3]); yLo = Math.min(rc[2], rc[3]); }
        else { yHi = Math.max(rc[2], 0); yLo = Math.min(rc[2], 0); }
        var rtp = syp(yHi), rbp = syp(yLo);
        var rw = Math.max(1, rx1p - rx0p), rh = Math.max(1, rbp - rtp);
        ctx.fillRect(rx0p, rtp, rw, rh);
        ctx.strokeRect(rx0p + 0.5, rtp + 0.5, rw - 1, rh - 1);
      }
    }
    if (e.kind === 'piechart' && e.items && e.items.length) drawPieChart(e);
    if (e.kind === 'linechart' && e.xs && e.xs.length) drawLineChart(e);
    if (e.kind === 'scatterplot' && e.pts && e.pts.length) drawScatterPlot(e);
    if (e.kind === 'dotplot' && e.stacks && e.stacks.length) drawDotPlot(e);
    if (e.kind === 'list' && e.itemkind === 'point' && e.items && e.items.length) {
      // 点列表 → 散点（如 Sequence[(i, i^2), i, 1, 10] 或 {(1,2),(3,4)}）
      ctx.fillStyle = '#dc2626';
      for (var spi = 0; spi < e.items.length; spi++) {
        var spx = sxp(e.items[spi][0]), spy = syp(e.items[spi][1]);
        ctx.beginPath();
        ctx.arc(spx, spy, 3.2, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    if (e.kind === 'locus' && e.pts && e.pts.length >= 2) {
      ctx.strokeStyle = '#dc2626';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(sxp(e.pts[0][0]), syp(e.pts[0][1]));
      for (var li2 = 1; li2 < e.pts.length; li2++) ctx.lineTo(sxp(e.pts[li2][0]), syp(e.pts[li2][1]));
      ctx.stroke();
    }
    if ((e.kind === 'parametric' || e.kind === 'polar') && e.pts && e.pts.length >= 2) {
      ctx.strokeStyle = colorOf(e);
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(sxp(e.pts[0][0]), syp(e.pts[0][1]));
      for (var ci = 1; ci < e.pts.length; ci++) ctx.lineTo(sxp(e.pts[ci][0]), syp(e.pts[ci][1]));
      ctx.stroke();
    }
    if (e.kind === 'implicit' && e.segs) {
      ctx.strokeStyle = colorOf(e);
      ctx.lineWidth = 2;
      ctx.beginPath();
      for (var isi = 0; isi < e.segs.length; isi++) {
        ctx.moveTo(sxp(e.segs[isi][0]), syp(e.segs[isi][1]));
        ctx.lineTo(sxp(e.segs[isi][2]), syp(e.segs[isi][3]));
      }
      ctx.stroke();
    }
    if (e.kind === 'arc') {
      var acx = sxp(e.cx), acy = syp(e.cy);
      var ar = Math.max(2, e.r * scale);
      if (e.sector) {
        ctx.fillStyle = 'rgba(124,58,237,.12)';
        ctx.strokeStyle = '#7c3aed';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(acx, acy);
        ctx.arc(acx, acy, ar, -e.ang1, -e.ang2, true);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
      } else {
        ctx.strokeStyle = '#7c3aed';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(acx, acy, ar, -e.ang1, -e.ang2, true);
        ctx.stroke();
      }
    }
    if (e.kind === 'polyline' && e.pts && e.pts.length >= 2) {
      ctx.strokeStyle = colorOf(e);
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(sxp(e.pts[0][0]), syp(e.pts[0][1]));
      for (i = 1; i < e.pts.length; i++) ctx.lineTo(sxp(e.pts[i][0]), syp(e.pts[i][1]));
      ctx.stroke();
    }
    if (e.kind === 'vector') {
      drawArrow(sxp(e.sx || 0), syp(e.sy || 0), sxp((e.sx || 0) + e.dx), syp((e.sy || 0) + e.dy), colorOf(e));
    }
    if (e.kind === 'point') {
      var sel = (selected === e.label);
      var px = sxp(e.x), py = syp(e.y);
      ctx.fillStyle = sel ? '#f59e0b' : (e.locked ? '#9ca3af' : (e.color && e.color !== '#1a1a1a' ? e.color : (e.free ? '#dc2626' : '#2563eb')));
      ctx.beginPath();
      ctx.arc(px, py, sel ? 6.5 : 4.5, 0, Math.PI * 2);
      ctx.fill();
      if (sel) { ctx.strokeStyle = '#f59e0b'; ctx.lineWidth = 2; ctx.stroke(); }
      if (activeTool && toolSel.indexOf(e.label) !== -1) {
        // 作图/变换工具进行中：已选对象加橙色外圈（明确"已选中"）
        ctx.beginPath();
        ctx.arc(px, py, 8.5, 0, Math.PI * 2);
        ctx.strokeStyle = '#f59e0b';
        ctx.lineWidth = 2;
        ctx.stroke();
      }
      ctx.fillStyle = C.text;
      ctx.font = '13px sans-serif';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'bottom';
      ctx.fillText(e.label, px + 6, py - 4);
    }
    if (e.kind === 'complex') {
      // 复数：复平面点（紫色）
      var cpX = sxp(e.x), cpY = syp(e.y);
      ctx.fillStyle = '#7c3aed';
      ctx.beginPath();
      ctx.arc(cpX, cpY, 4.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 1.2;
      ctx.stroke();
      ctx.fillStyle = C.text;
      ctx.font = '13px sans-serif';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'bottom';
      ctx.fillText(e.label, cpX + 6, cpY - 4);
    }
  }


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
  var chartBoxes = {};                    // label → 屏幕包围盒（整体拖动命中用）
  var PIE_PAL = ['#ef4444', '#3b82f6', '#f59e0b', '#10b981', '#8b5cf6', '#06b6d4', '#f97316', '#ec4899', '#84cc16', '#64748b'];




  // ---------- 统计图工具：点击画布 → 输入数据 → 生成图 ----------
  function isChartTool(name) {
    return !!CHART_TOOL_CMD[name] || name === 'histogram' || name === 'scatterplot' ||
           name === 'scatterplot3d' || name === 'surfacechart3d';
  }

  var CHART_TOOL_CMD = {
    barchart: 'BarChart', boxplot: 'BoxPlot', piechart: 'PieChart',
    linechart: 'LineChart', dotplot: 'DotPlot', barchart3d: 'BarChart3D'
  };

  function chartDataPrompt(title, def) {
    var txt = prompt(title, def || '');
    if (txt === null || !txt.trim()) return null;
    var parts = txt.split(/[,，\s]+/).map(function (v) { return v.trim(); }).filter(Boolean);
    if (!parts.length || parts.some(function (v) { return isNaN(parseFloat(v)); })) return '';
    return parts;
  }

  function chartToolPrompt(tool) {
    var zhTitle = {
      barchart: '数据（逗号分隔，如 1,2,2,3,3）：', histogram: '数据（逗号分隔）：',
      boxplot: '数据（逗号分隔）：', piechart: '各部分数值（逗号分隔，如 3,5,2）：',
      linechart: '数据（逗号分隔，按顺序连线）：', dotplot: '数据（逗号分隔，相同值叠点）：',
      scatterplot: '点（如 1,2; 3,4; 5,3）：', barchart3d: '数据（逗号分隔）→ 三维柱状图：',
      scatterplot3d: '三维点（如 1,2,3; 4,5,6）：', surfacechart3d: '数值（逗号分隔）：'
    }[tool] || '数据（逗号分隔）：';
    var enTitle = {
      barchart: 'Data (comma separated, e.g. 1,2,2,3,3):', histogram: 'Data (comma separated):',
      boxplot: 'Data (comma separated):', piechart: 'Part values (comma separated, e.g. 3,5,2):',
      linechart: 'Data (comma separated, connected in order):', dotplot: 'Data (comma separated, repeats stack):',
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
  function conicPathPts(e) {
    var i, paths = [];
    if (e.ctype === 'ellipse' || e.ctype === 'circle') {
      var a = e.semi_a, b = e.semi_b || a, ang = e.angle || 0;
      var ca = Math.cos(ang), sa = Math.sin(ang);
      var path = [];
      for (i = 0; i <= 64; i++) {
        var t = i * Math.PI * 2 / 64;
        path.push([e.cx + a * Math.cos(t) * ca - b * Math.sin(t) * sa,
                   e.cy + a * Math.cos(t) * sa + b * Math.sin(t) * ca]);
      }
      paths.push(path);
    } else if (e.ctype === 'hyperbola') {
      var a2 = e.semi_a, b2 = e.semi_b, ang2 = e.angle || 0;
      var ca2 = Math.cos(ang2), sa2 = Math.sin(ang2);
      for (var sgn = -1; sgn <= 1; sgn += 2) {
        var br = [];
        for (i = -40; i <= 40; i++) {
          var t2 = i * 0.11;
          var xl = sgn * a2 * Math.cosh(t2), yl = b2 * Math.sinh(t2);
          br.push([e.cx + xl * ca2 - yl * sa2, e.cy + xl * sa2 + yl * ca2]);
        }
        paths.push(br);
      }
    } else if (e.ctype === 'parabola') {
      var pp = e.semi_a || 1, ang3 = e.angle || 0;
      var ux = Math.cos(ang3), uy = Math.sin(ang3);
      var vx = -uy, vy = ux;
      var span = Math.max(Math.abs(view.xmax - view.xmin), Math.abs(view.ymax - view.ymin));
      var tm = Math.sqrt(span * pp * 4) * 1.6;
      var pa = [];
      for (i = -60; i <= 60; i++) {
        var t3 = i * tm / 60;
        var xl3 = t3, yl3 = t3 * t3 / (4 * pp);
        pa.push([e.cx + xl3 * vx + yl3 * ux, e.cy + xl3 * vy + yl3 * uy]);
      }
      paths.push(pa);
    }
    return paths;
  }

  function drawConic(e) {
    var c = colorOf(e);
    var i, t, x, y;
    if (e.ctype === 'ellipse' || e.ctype === 'circle') {
      var a = e.semi_a, b = e.semi_b || a, ang = e.angle || 0;
      var ca = Math.cos(ang), sa = Math.sin(ang);
      ctx.strokeStyle = c; ctx.lineWidth = 2; ctx.beginPath();
      var first = true;
      for (i = 0; i <= 160; i++) {
        t = i * Math.PI * 2 / 160;
        x = e.cx + a * Math.cos(t) * ca - b * Math.sin(t) * sa;
        y = e.cy + a * Math.cos(t) * sa + b * Math.sin(t) * ca;
        if (first) { ctx.moveTo(sxp(x), syp(y)); first = false; }
        else ctx.lineTo(sxp(x), syp(y));
      }
      ctx.stroke();
    } else if (e.ctype === 'hyperbola') {
      var a2 = e.semi_a, b2 = e.semi_b, ang2 = e.angle || 0;
      var ca2 = Math.cos(ang2), sa2 = Math.sin(ang2);
      ctx.strokeStyle = c; ctx.lineWidth = 2;
      var branch = function (sgn) {
        ctx.beginPath();
        var first2 = true;
        for (i = -50; i <= 50; i++) {
          t = i * 0.09;
          var xl = sgn * a2 * Math.cosh(t), yl = b2 * Math.sinh(t);
          x = e.cx + xl * ca2 - yl * sa2;
          y = e.cy + xl * sa2 + yl * ca2;
          if (first2) { ctx.moveTo(sxp(x), syp(y)); first2 = false; }
          else ctx.lineTo(sxp(x), syp(y));
        }
        ctx.stroke();
      };
      branch(1); branch(-1);
    } else if (e.ctype === 'parabola') {
      var p = e.semi_a || 1, ang3 = e.angle || 0;
      var ux = Math.cos(ang3), uy = Math.sin(ang3);
      var vx = -uy, vy = ux;
      var span = Math.max(Math.abs(view.xmax - view.xmin), Math.abs(view.ymax - view.ymin));
      var tm = Math.sqrt(span * p * 4) * 1.6;
      ctx.strokeStyle = c; ctx.lineWidth = 2; ctx.beginPath();
      var first3 = true;
      for (i = -120; i <= 120; i++) {
        t = i * tm / 120;
        var xl = t, yl = t * t / (4 * p);
        x = e.cx + xl * vx + yl * ux;
        y = e.cy + xl * vy + yl * uy;
        if (first3) { ctx.moveTo(sxp(x), syp(y)); first3 = false; }
        else ctx.lineTo(sxp(x), syp(y));
      }
      ctx.stroke();
    } else if (e.segs) {
      ctx.strokeStyle = c; ctx.lineWidth = 2; ctx.beginPath();
      for (i = 0; i < e.segs.length; i++) {
        ctx.moveTo(sxp(e.segs[i][0]), syp(e.segs[i][1]));
        ctx.lineTo(sxp(e.segs[i][2]), syp(e.segs[i][3]));
      }
      ctx.stroke();
    }
  }

  function drawInequality(e) {
    var fill = 'rgba(59,130,246,.16)';
    if (e.form === 'y' && e.boundary) {
      var ys = e.boundary;
      ctx.fillStyle = fill;
      var top = e.yside > 0;
      // 按连续段分割边界，每段与画布边缘构成填充多边形
      var runs = [];
      var cur = [];
      for (var i = 0; i < ys.length; i++) {
        if (!isFinite(ys[i][1])) {
          if (cur.length >= 2) runs.push(cur);
          cur = [];
        } else cur.push(ys[i]);
      }
      if (cur.length >= 2) runs.push(cur);
      for (var ri = 0; ri < runs.length; ri++) {
        var run = runs[ri];
        ctx.beginPath();
        ctx.moveTo(sxp(run[0][0]), syp(run[0][1]));
        for (var rp = 1; rp < run.length; rp++) ctx.lineTo(sxp(run[rp][0]), syp(run[rp][1]));
        var last = run[run.length - 1];
        if (top) {
          ctx.lineTo(sxp(last[0]), 0);
          ctx.lineTo(sxp(run[0][0]), 0);
        } else {
          ctx.lineTo(sxp(last[0]), cssH);
          ctx.lineTo(sxp(run[0][0]), cssH);
        }
        ctx.closePath();
        ctx.fill();
      }
      // 边界曲线
      ctx.strokeStyle = '#3b82f6'; ctx.lineWidth = 2; ctx.beginPath();
      var started = false;
      for (var j = 0; j < ys.length; j++) {
        if (!isFinite(ys[j][1])) { started = false; continue; }
        if (!started) { ctx.moveTo(sxp(ys[j][0]), syp(ys[j][1])); started = true; }
        else ctx.lineTo(sxp(ys[j][0]), syp(ys[j][1]));
      }
      ctx.stroke();
      if (e.strict) {
        ctx.fillStyle = '#3b82f6';
        for (var k = 0; k < ys.length; k += 24) {
          if (isFinite(ys[k][1])) {
            ctx.beginPath();
            ctx.arc(sxp(ys[k][0]), syp(ys[k][1]), 2, 0, Math.PI * 2);
            ctx.fill();
          }
        }
      }
    } else if (e.loops) {
      ctx.fillStyle = fill;
      ctx.strokeStyle = '#3b82f6';
      ctx.lineWidth = 2;
      for (var li = 0; li < e.loops.length; li++) {
        var loop = e.loops[li];
        if (loop.length < 3) continue;
        ctx.beginPath();
        ctx.moveTo(sxp(loop[0][0]), syp(loop[0][1]));
        for (var lp = 1; lp < loop.length; lp++) ctx.lineTo(sxp(loop[lp][0]), syp(loop[lp][1]));
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
      }
    }
  }


  // 滑块播放动画（点击 ▶ 自动递增参数，依赖曲线实时联动）
  var playState = null;
  function sliderPlay(label) {
    if (playState && playState.label === label) {
      clearInterval(playState.timer); playState = null; render(); return;
    }
    if (playState) { clearInterval(playState.timer); playState = null; }
    playState = { label: label, timer: setInterval(function () {
      var el = null;
      for (var pi = 0; pi < elements.length; pi++) {
        if (elements[pi].label === label && elements[pi].min !== undefined) el = elements[pi];
      }
      if (!el) { clearInterval(playState.timer); playState = null; render(); return; }
      var v = el.val + el.step;
      if (v > el.max) v = el.min;
      api('POST', '/api/drag', { label: label, x: v, y: 0, push: false }, function (d) {
        if (d && d.elements) { elements = d.elements; render(); }
      });
    }, 90) };
    render();
  }


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
  var CHART_KINDS = ['barchart', 'histogram', 'boxplot', 'piechart', 'linechart', 'scatterplot', 'dotplot'];
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
    if (playState) { clearInterval(playState.timer); playState = null; render(); }  // 画布交互自动停止播放
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
      canvas.setPointerCapture(ev.pointerId);
      return;
    }
    var sx = ev.offsetX, sy = ev.offsetY;
    // 宏点选模式：点击画布对象 → 加入输入/输出框
    if (macroPickMode) {
      var pkHit = hitAnyPoint(sx, sy) || hitObject(sx, sy, ['segment', 'circle', 'line', 'polygon', 'arc', 'text', 'vector', 'ray', 'conic', 'function']);
      if (pkHit) handleMacroPick(pkHit);
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
        canvas.setPointerCapture(ev.pointerId);
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
        canvas.setPointerCapture(ev.pointerId);
        return;
      }
      pan = { sx: sx, sy: sy, xmin: view.xmin, ymin: view.ymin };
      canvas.style.cursor = 'grabbing';
    }
    canvas.setPointerCapture(ev.pointerId);
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
      drag = null;
      dragPending = false;
      canvas.style.cursor = 'default';
      // 最后一次落点已随 move 提交
      loadState();
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
  function unproj3(sx, sy, z) {
    var W = cssW, H = cssH;
    var f = cam.r * 2.2;
    var pxScale = Math.min(W, H) * 0.42 / cam.r;
    var u = (sx - W / 2) / pxScale, v = (H / 2 - sy) / pxScale;
    // 斜二测逆投影：v = z + K·y（z 已知），u = x + K·y
    if (view3dMode === 'oblique') {
      var K = 0.3536;
      var yy = (v - (z - cam.tz)) / K;
      var xx = u - K * yy;
      return [xx + cam.tx, yy + cam.ty, z];
    }
    var b = camBasis3();
    var cp = b.up[2], sp = b.dir[2];
    var xc, yc, zc;
    if (ortho3d) {
      // 正交：z_cam 由平面约束直接解（dir_z = sp）
      if (Math.abs(sp) < COORD) {
        zc = 0;
      } else {
        zc = ((z - cam.tz) - v * cp) / sp;
      }
      xc = u; yc = v;
    } else {
      var denom = (z - cam.tz) + (f + cam.r) * sp;
      if (Math.abs(denom) < COORD) {
        xc = u; yc = v; zc = 0;
      } else {
        var s = (v * cp + f * sp) / denom;
        s = Math.max(0.05, Math.min(20, s));
        xc = u / s; yc = v / s; zc = f / s - f - cam.r;
      }
    }
    var d0 = [xc * b.right[0] + yc * b.up[0] + zc * b.dir[0],
              xc * b.right[1] + yc * b.up[1] + zc * b.dir[1],
              xc * b.right[2] + yc * b.up[2] + zc * b.dir[2]];
    return [d0[0] + cam.tx, d0[1] + cam.ty, z];
  }


  // 3D 坐标轴：带箭头的彩色轴 + x/y/z 标签 + 原点；左下角微缩坐标轴指示器
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
    els3dCount: function () { return (typeof els3d !== 'undefined' && els3d) ? els3d.length : -1; },
    mode3d: function () { return typeof mode3d !== 'undefined' ? !!mode3d : null; },
    load3d: function () { load3d(); },
    rev3d: function () { return typeof lastRev3d !== 'undefined' ? lastRev3d : -1; },
    refreshCount: function () { return dbgRefreshN; },
    loadCount: function () { return dbgLoadN; }
  };

  function render3d() {
    ctx3.clearRect(0, 0, cssW, cssH);
    // 坐标轴（带箭头 + 标签 + 原点）
    drawAxes3d();
    // 工作平面网格画在坐标轴之下（已在上方画箭头，这里只画基准平面网格）
    // 基准平面（z=planeZ 网格，工作平面指示）
    var pz = planeZ;
    ctx3.strokeStyle = 'rgba(99,102,241,.35)';
    ctx3.lineWidth = 1;
    ctx3.beginPath();
    var pzStep = 1;
    var pspan = 12;   // 基准平面半宽（扩大一倍）
    for (var pxg = -pspan; pxg <= pspan; pxg++) {
      line3([pxg, -pspan, pz], [pxg, pspan, pz], 'rgba(99,102,241,.22)', 1);
    }
    for (var pyg = -pspan; pyg <= pspan; pyg++) {
      line3([-pspan, pyg, pz], [pspan, pyg, pz], 'rgba(99,102,241,.22)', 1);
    }
    line3([-pspan, -pspan, pz], [pspan, -pspan, pz], 'rgba(99,102,241,.45)', 1.4);
    line3([pspan, -pspan, pz], [pspan, pspan, pz], 'rgba(99,102,241,.45)', 1.4);
    line3([pspan, pspan, pz], [-pspan, pspan, pz], 'rgba(99,102,241,.45)', 1.4);
    line3([-pspan, pspan, pz], [-pspan, -pspan, pz], 'rgba(99,102,241,.45)', 1.4);
    // 三维场景绘制（几何收集/遮挡/顶点）已抽到 static/scene3d.js（P2 前端拆分）
    _scene.drawScene();
    // 选中 3D 对象高亮（橙色虚线）
    if (selected3d) {
      var selEl = findEl3d(selected3d);
      if (selEl) {
        var sdt = selEl.data || {};
        ctx3.strokeStyle = '#f59e0b';
        ctx3.lineWidth = 3;
        ctx3.setLineDash([6, 4]);
        ctx3.beginPath();
        if (selEl.kind === 'point') {
          // 点的选中样式已在上面的点绘制中处理（菱形变橙 + 光环）
        } else if ((selEl.objtype === 'cube' || selEl.objtype === 'polyhedron') && sdt.verts) {
          for (var se = 0; se < (sdt.edges || []).length; se++) {
            var sedg = sdt.edges[se];
            var sp1 = proj3(sdt.verts[sedg[0]]), sp2 = proj3(sdt.verts[sedg[1]]);
            ctx3.moveTo(sp1.x, sp1.y); ctx3.lineTo(sp2.x, sp2.y);
          }
        } else if (selEl.objtype === 'plane') {
          var sa3 = [sdt.ax, sdt.ay, sdt.az], su3 = [sdt.ux, sdt.uy, sdt.uz], sv3 = [sdt.vx, sdt.vy, sdt.vz];
          var sq = [[sa3[0], sa3[1], sa3[2]],
                    [sa3[0] + su3[0], sa3[1] + su3[1], sa3[2] + su3[2]],
                    [sa3[0] + su3[0] + sv3[0], sa3[1] + su3[1] + sv3[1], sa3[2] + su3[2] + sv3[2]],
                    [sa3[0] + sv3[0], sa3[1] + sv3[1], sa3[2] + sv3[2]]];
          for (var sqi = 0; sqi < 4; sqi++) {
            var sqa = proj3(sq[sqi]), sqb = proj3(sq[(sqi + 1) % 4]);
            ctx3.moveTo(sqa.x, sqa.y); ctx3.lineTo(sqb.x, sqb.y);
          }
        } else if (selEl.objtype === 'segment') {
          var ss1 = proj3([sdt.x1, sdt.y1, sdt.z1]), ss2 = proj3([sdt.x2, sdt.y2, sdt.z2]);
          ctx3.moveTo(ss1.x, ss1.y); ctx3.lineTo(ss2.x, ss2.y);
        } else if (selEl.objtype === 'sphere') {
          // 球的轮廓圆（屏幕空间近似：用大圆上多点连成）
          var shc = [sdt.cx, sdt.cy, sdt.cz], shr = sdt.r;
          for (var shAng = 0; shAng <= 360; shAng += 10) {
            var shR = shAng * Math.PI / 180;
            var shP = proj3([shc[0] + shr * Math.cos(shR), shc[1], shc[2] + shr * Math.sin(shR)]);
            if (shAng === 0) ctx3.moveTo(shP.x, shP.y); else ctx3.lineTo(shP.x, shP.y);
          }
          var shP2 = proj3([shc[0] + shr, shc[1], shc[2]]);
          var shP3 = proj3([shc[0] - shr, shc[1], shc[2]]);
          ctx3.moveTo(shP2.x, shP2.y); ctx3.lineTo(shP3.x, shP3.y);
          var shP4 = proj3([shc[0], shc[1] + shr, shc[2]]);
          var shP5 = proj3([shc[0], shc[1] - shr, shc[2]]);
          ctx3.moveTo(shP4.x, shP4.y); ctx3.lineTo(shP5.x, shP5.y);
        }
        ctx3.stroke();
        ctx3.setLineDash([]);
      }
    }
    // z 轴控制柄：选中自由 3D 点时显示竖直小箭头，拖动改 z 高度
    if (selected3d) {
      var zhEl = findEl3d(selected3d);
      if (zhEl && zhEl.kind === 'point' && zhEl.free) {
        var zp = proj3([zhEl.x, zhEl.y, zhEl.z]);
        var handleLen = 42;
        // z 轴屏幕方向：世界 (0,0,1) 的投影方向
        var zUp3 = proj3([zhEl.x, zhEl.y, zhEl.z + 1]);
        var zdx = zUp3.x - zp.x, zdy = zUp3.y - zp.y;
        var zln = Math.hypot(zdx, zdy) || 1;
        zdx /= zln; zdy /= zln;
        var hx = zp.x + zdx * handleLen, hy = zp.y + zdy * handleLen;
        ctx3.strokeStyle = '#0891b2';
        ctx3.lineWidth = 3;
        ctx3.beginPath();
        ctx3.moveTo(zp.x, zp.y); ctx3.lineTo(hx, hy);
        ctx3.stroke();
        // 箭头
        ctx3.fillStyle = '#0891b2';
        ctx3.beginPath();
        ctx3.moveTo(hx, hy);
        ctx3.lineTo(hx - zdy * 9, hy + zdx * 9);
        ctx3.lineTo(hx + zdy * 9, hy - zdx * 9);
        ctx3.closePath();
        ctx3.fill();
      }
    }
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
  function hitObject3dKind(sx, sy, kinds) {
    var best = null, bestD = 12;
    for (var i = 0; i < els3d.length; i++) {
      var e = els3d[i];
      if (e.visible === false) continue;
      if (kinds.indexOf(e.objtype) === -1) continue;
      var dt = e.data || {};
      if (e.objtype === 'segment') {
        var s1 = proj3([dt.x1, dt.y1, dt.z1]), s2 = proj3([dt.x2, dt.y2, dt.z2]);
        var ds = distToSeg(sx, sy, s1.x, s1.y, s2.x, s2.y);
        if (ds <= 10 && ds < bestD) { bestD = ds; best = e; }
      } else if (e.objtype === 'circle2d') {
        var cc3 = [dt.cx || 0, dt.cy || 0, dt.cz || 0], cr3 = dt.r || 0;
        var prevC = null;
        for (var ci3 = 0; ci3 <= 48; ci3++) {
          var angC = 2 * Math.PI * ci3 / 48;
          var prC = proj3([cc3[0] + cr3 * Math.cos(angC), cc3[1] + cr3 * Math.sin(angC), cc3[2]]);
          if (prevC) {
            var dC = distToSeg(sx, sy, prevC.x, prevC.y, prC.x, prC.y);
            if (dC <= 10 && dC < bestD) { bestD = dC; best = e; }
          }
          prevC = prC;
        }
      } else if (e.objtype === 'polygon2d') {
        var pts = dt.pts || [];
        var sp = [];
        for (var pi = 0; pi < pts.length; pi++) {
          var pa = proj3(pts[pi]), pb = proj3(pts[(pi + 1) % pts.length]);
          sp.push([pa.x, pa.y]);
          var dp = distToSeg(sx, sy, pa.x, pa.y, pb.x, pb.y);
          if (dp <= 10 && dp < bestD) { bestD = dp; best = e; }
        }
        // 点击内部也可命中
        var inside3 = false;
        for (var a3 = 0, b3 = sp.length - 1; a3 < sp.length; b3 = a3++) {
          if (((sp[a3][1] > sy) !== (sp[b3][1] > sy)) &&
              (sx < (sp[b3][0] - sp[a3][0]) * (sy - sp[a3][1]) / (sp[b3][1] - sp[a3][1]) + sp[a3][0])) inside3 = !inside3;
        }
        if (inside3) { bestD = 0; best = e; }
      }
    }
    return best;
  }
  function hitObject3d(sx, sy) {
    var best = null, bestD = 12;
    for (var i = 0; i < els3d.length; i++) {
      var e = els3d[i];
      if (e.visible === false) continue;
      if (e.kind === 'point') {
        var pr = proj3([e.x, e.y, e.z]);
        var dd = Math.hypot(pr.x - sx, pr.y - sy);
        if (dd <= 12 && dd < bestD) { bestD = dd; best = e; }
        continue;
      }
      var dt = e.data || {};
      var pts3 = [];
      if (e.objtype === 'polyhedron' || e.objtype === 'cube') {
        var vs = dt.verts || [];
        for (var ei = 0; ei < (dt.edges || []).length; ei++) {
          var edg = dt.edges[ei];
          var p1 = proj3(vs[edg[0]]), p2 = proj3(vs[edg[1]]);
          var d2 = distToSeg(sx, sy, p1.x, p1.y, p2.x, p2.y);
          if (d2 <= 10 && d2 < bestD) { bestD = d2; best = e; }
        }
      } else if (e.objtype === 'plane') {
        var a3 = [dt.ax, dt.ay, dt.az], u3 = [dt.ux, dt.uy, dt.uz], v3 = [dt.vx, dt.vy, dt.vz];
        var quad = [[a3[0], a3[1], a3[2]],
                    [a3[0] + u3[0], a3[1] + u3[1], a3[2] + u3[2]],
                    [a3[0] + u3[0] + v3[0], a3[1] + u3[1] + v3[1], a3[2] + u3[2] + v3[2]],
                    [a3[0] + v3[0], a3[1] + v3[1], a3[2] + v3[2]]];
        for (var qi = 0; qi < 4; qi++) {
          var pa = proj3(quad[qi]), pb = proj3(quad[(qi + 1) % 4]);
          var dq = distToSeg(sx, sy, pa.x, pa.y, pb.x, pb.y);
          if (dq <= 10 && dq < bestD) { bestD = dq; best = e; }
        }
      } else if (e.objtype === 'segment') {
        var s1 = proj3([dt.x1, dt.y1, dt.z1]), s2 = proj3([dt.x2, dt.y2, dt.z2]);
        var ds = distToSeg(sx, sy, s1.x, s1.y, s2.x, s2.y);
        if (ds <= 10 && ds < bestD) { bestD = ds; best = e; }
      } else if (e.objtype === 'sphere') {
        // 球：按经/纬线框采样后取屏幕最近距离
        var sc = [dt.cx, dt.cy, dt.cz], sr = dt.r;
        var latN2 = 12, longN2 = 24;
        for (var la = 0; la < latN2; la++) {
          for (var lo2 = 0; lo2 < longN2; lo2++) {
            var phA = Math.PI * la / latN2, phB = Math.PI * (la + 1) / latN2;
            var thA = 2 * Math.PI * lo2 / longN2, thB = 2 * Math.PI * (lo2 + 1) / longN2;
            var pA = [sc[0] + sr * Math.sin(phA) * Math.cos(thA), sc[1] + sr * Math.cos(phA), sc[2] + sr * Math.sin(phA) * Math.sin(thA)];
            var pB = [sc[0] + sr * Math.sin(phA) * Math.cos(thB), sc[1] + sr * Math.cos(phA), sc[2] + sr * Math.sin(phA) * Math.sin(thB)];
            var pC = [sc[0] + sr * Math.sin(phB) * Math.cos(thB), sc[1] + sr * Math.cos(phB), sc[2] + sr * Math.sin(phB) * Math.sin(thB)];
            var prA = proj3(pA), prB = proj3(pB), prC = proj3(pC);
            var dS = Math.min(distToSeg(sx, sy, prA.x, prA.y, prB.x, prB.y),
                              distToSeg(sx, sy, prB.x, prB.y, prC.x, prC.y));
            if (dS <= 10 && dS < bestD) { bestD = dS; best = e; }
          }
        }
      }
    }
    return best;
  }
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
  function tool3dPointAt(sx, sy, cb) {
    var hit = hitPoint3d(sx, sy);
    if (hit) { cb(hit.label); return; }
    // 轴吸附优先：点击 z 轴（竖直中心线）→ 得到 z 轴上的点 (0,0,z)
    var snap = snapAxis3d(sx, sy);
    if (snap) {
      var w0 = [snap.ax[0] * snap.t, snap.ax[1] * snap.t, snap.ax[2] * snap.t];
      postInput3d('(' + fmtW(w0[0]) + ',' + fmtW(w0[1]) + ',' + fmtW(w0[2]) + ')', function (d) {
        if (!d || !d.ok) { resetTool3d(); return; }
        var prev0 = {};
        for (var i0 = 0; i0 < els3d.length; i0++) prev0[els3d[i0].label] = true;
        var newEls0 = d.elements || [];
        for (var j0 = 0; j0 < newEls0.length; j0++) {
          if (newEls0[j0].kind === 'point' && !prev0[newEls0[j0].label]) { cb(newEls0[j0].label); return; }
        }
        load3d();
        cb(null);
      });
      return;
    }
    var w = unproj3(sx, sy, planeZ);
    // 把工作平面上的取点限制在合理范围（透视近处点会延伸到远处，钳制到 ±10）
    var CLAMP = 10;
    w[0] = Math.max(-CLAMP, Math.min(CLAMP, w[0]));
    w[1] = Math.max(-CLAMP, Math.min(CLAMP, w[1]));
    postInput3d('(' + fmtW(w[0]) + ',' + fmtW(w[1]) + ',' + fmtW(w[2]) + ')', function (d) {
      if (!d || !d.ok) { resetTool3d(); return; }
      // 用 API 返回的完整 elements（比异步 load3d 可靠），找到刚创建的点
      var prev = {};
      for (var i = 0; i < els3d.length; i++) prev[els3d[i].label] = true;
      var newEls = d.elements || [];
      for (var j = 0; j < newEls.length; j++) {
        if (newEls[j].kind === 'point' && !prev[newEls[j].label]) { cb(newEls[j].label); return; }
      }
      load3d();
      cb(null);
    });
  }
  function tool3dClick(sx, sy) {
    if (tool3d === 'pt3d') {
      tool3dPointAt(sx, sy, function () {
        // 连续操作：保持工具激活，可继续画下一个点（Esc / 再点按钮退出）
        toolSel3d = [];
        setToolStatus3d();
      });
      return;
    }
    if (tool3d === 'seg3d' || tool3d === 'line3d') {
      tool3dPointAt(sx, sy, function (lbl) {
        if (!lbl) return;
        toolSel3d.push(lbl);
        if (toolSel3d.length === 2) {
          var cmd3 = tool3d === 'seg3d' ? 'Segment[' : 'Line[';
          postInput3d(cmd3 + toolSel3d.join(',') + ']', function (ok) { if (ok) { toolSel3d = []; setToolStatus3d(); } });
        } else setToolStatus3d();
      });
      return;
    }
    if (tool3d === 'plane3d') {
      tool3dPointAt(sx, sy, function (lbl) {
        if (!lbl) return;
        toolSel3d.push(lbl);
        if (toolSel3d.length === 3) {
          postInput3d('Plane[' + toolSel3d.join(',') + ']', function (ok) { if (ok) { toolSel3d = []; setToolStatus3d(); } });
        } else setToolStatus3d();
      });
      return;
    }
    if (tool3d === 'sphere3d') {
      tool3dPointAt(sx, sy, function (lbl) {
        if (!lbl) return;
        toolSel3d.push(lbl);
        if (toolSel3d.length === 2) {
          postInput3d('Sphere[' + toolSel3d.join(',') + ']', function (ok) { if (ok) { toolSel3d = []; setToolStatus3d(); } });
        } else setToolStatus3d();
      });
      return;
    }
    if (tool3d === 'cube3d') {
      function cubeCreate3(cmd) {
        postInput3d(cmd, function (ok) { if (ok) { toolSel3d = []; setToolStatus3d(); } });
      }
      // 1) 点优先：点两个空间点 → Cube[A,B]；已选一点则补成第二点
      var ptHit3 = hitPoint3d(sx, sy);
      if (ptHit3) {
        toolSel3d.push(ptHit3.label);
        if (toolSel3d.length >= 2) cubeCreate3('Cube[' + toolSel3d.join(',') + ']');
        else setToolStatus3d();
        return;
      }
      // 2) 线段：直接 Cube[线段]；已选一点 → Cube[线段, 点]
      var segHit3 = hitObject3dKind(sx, sy, ['segment']);
      if (segHit3) {
        if (toolSel3d.length >= 1) cubeCreate3('Cube[' + segHit3.label + ',' + toolSel3d[0] + ']');
        else cubeCreate3('Cube[' + segHit3.label + ']');
        return;
      }
      // 3) 正方形多边形：Cube[正方形]
      var polyHit3 = hitObject3dKind(sx, sy, ['polygon2d']);
      if (polyHit3) {
        cubeCreate3('Cube[' + polyHit3.label + ']');
        return;
      }
      // 4) 空白：在基准平面取点
      tool3dPointAt(sx, sy, function (lbl) {
        if (!lbl) return;
        toolSel3d.push(lbl);
        if (toolSel3d.length >= 2) cubeCreate3('Cube[' + toolSel3d.join(',') + ']');
        else setToolStatus3d();
      });
      return;
    }
    if (tool3d === 'cone3d') {
      // 形式 1：点已有圆（3D 中显示的圆）→ 输入高度
      if (toolSel3d.length === 0) {
        var circHit3 = hitObject3dKind(sx, sy, ['circle2d']);
        if (circHit3) {
          var hTxt = prompt(lang === 'en' ? 'Cone height:' : '圆锥高度：', '3');
          if (hTxt === null || hTxt.trim() === '') { resetTool3d(); return; }
          var hv3 = parseFloat(hTxt);
          if (isNaN(hv3) || hv3 <= 0) { setMsg(lang === 'en' ? 'Enter a positive height' : '请输入正数高度', true); return; }
          postInput3d('Cone[' + circHit3.label + ',' + hv3 + ']', function (ok) { if (ok) { toolSel3d = []; setToolStatus3d(); } });
          return;
        }
        tool3dPointAt(sx, sy, function (lbl) {
          if (!lbl) return;
          toolSel3d = [lbl];   // 顶点
          setToolStatus3d();
        });
        return;
      }
      // 形式 2：顶点已定 → 点底面中心（随后输入半径；取消则改点半径点走三点式）
      if (toolSel3d.length === 1) {
        tool3dPointAt(sx, sy, function (lbl) {
          if (!lbl) return;
          var apex3 = toolSel3d[0];
          var rTxt = prompt(lang === 'en' ? 'Base radius (Cancel → pick a radius point):'
                                          : '底面半径（取消 → 再点一个底面半径点）：', '2');
          if (rTxt === null) { toolSel3d = [apex3, lbl]; setToolStatus3d(); return; }
          var rv3 = parseFloat(rTxt);
          if (isNaN(rv3) || rv3 <= 0) { setMsg(lang === 'en' ? 'Enter a positive radius' : '请输入正数半径', true); return; }
          postInput3d('Cone[' + apex3 + ',' + lbl + ',' + rv3 + ']', function (ok) { if (ok) { toolSel3d = []; setToolStatus3d(); } });
        });
        return;
      }
      // 形式 3（经典三点）：顶点、底心已定 → 点底面半径点 → Cone[底心, 半径点, 顶点]
      if (toolSel3d.length === 2) {
        tool3dPointAt(sx, sy, function (lbl) {
          if (!lbl) return;
          var apex4 = toolSel3d[0], base4 = toolSel3d[1];
          postInput3d('Cone[' + base4 + ',' + lbl + ',' + apex4 + ']', function (ok) { if (ok) { toolSel3d = []; setToolStatus3d(); } });
        });
        return;
      }
    }
    if (tool3d === 'cylinder3d') {
      // 形式 1：点已有圆 → 输入高度 → Cylinder[圆, 高]
      if (toolSel3d.length === 0) {
        var cycHit3 = hitObject3dKind(sx, sy, ['circle2d']);
        if (cycHit3) {
          var chTxt = prompt(lang === 'en' ? 'Cylinder height:' : '圆柱高度：', '3');
          if (chTxt === null || chTxt.trim() === '') { resetTool3d(); return; }
          var chv3 = parseFloat(chTxt);
          if (isNaN(chv3) || chv3 <= 0) { setMsg(lang === 'en' ? 'Enter a positive height' : '请输入正数高度', true); return; }
          postInput3d('Cylinder[' + cycHit3.label + ',' + chv3 + ']', function (ok) { if (ok) { toolSel3d = []; setToolStatus3d(); } });
          return;
        }
        tool3dPointAt(sx, sy, function (lbl) {
          if (!lbl) return;
          toolSel3d = [lbl];   // 底面圆心
          setToolStatus3d();
        });
        return;
      }
      // 形式 2：底心已定 → 点顶面圆心（随后输入半径；取消则改点半径点走三点式）
      if (toolSel3d.length === 1) {
        tool3dPointAt(sx, sy, function (lbl) {
          if (!lbl) return;
          var cbase3 = toolSel3d[0];
          var crTxt = prompt(lang === 'en' ? 'Radius (Cancel → pick a radius point):'
                                           : '底面半径（取消 → 再点一个底面半径点）：', '2');
          if (crTxt === null) { toolSel3d = [cbase3, lbl]; setToolStatus3d(); return; }
          var crv3 = parseFloat(crTxt);
          if (isNaN(crv3) || crv3 <= 0) { setMsg(lang === 'en' ? 'Enter a positive radius' : '请输入正数半径', true); return; }
          postInput3d('Cylinder[' + cbase3 + ',' + lbl + ',' + crv3 + ']', function (ok) { if (ok) { toolSel3d = []; setToolStatus3d(); } });
        });
        return;
      }
      // 形式 3（经典三点）：底心、顶心已定 → 点底面半径点 → Cylinder[底心, 半径点, 顶心]
      if (toolSel3d.length === 2) {
        tool3dPointAt(sx, sy, function (lbl) {
          if (!lbl) return;
          var cbase5 = toolSel3d[0], ctop5 = toolSel3d[1];
          postInput3d('Cylinder[' + cbase5 + ',' + lbl + ',' + ctop5 + ']', function (ok) { if (ok) { toolSel3d = []; setToolStatus3d(); } });
        });
        return;
      }
    }

    // 通用 3 点多面体工具：圆锥/圆柱/棱柱/棱锥/正四面体/正八面体/正二十面体/正十二面体
    var SOLID3_CMD = { cone3d: 'Cone', cylinder3d: 'Cylinder', prism3d: 'Prism', pyramid3d: 'Pyramid',
                       tetra3d: 'Tetrahedron', octa3d: 'Octahedron', hexa3d: 'Hexahedron', icosa3d: 'Icosahedron', dodeca3d: 'Dodecahedron' };
    if (SOLID3_CMD[tool3d]) {
      tool3dPointAt(sx, sy, function (lbl) {
        if (!lbl) return;
        toolSel3d.push(lbl);
        if (toolSel3d.length === 3) {
          postInput3d(SOLID3_CMD[tool3d] + '[' + toolSel3d.join(',') + ']', function (ok) { if (ok) { toolSel3d = []; setToolStatus3d(); } });
        } else setToolStatus3d();
      });
      return;
    }
  }
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
  function postInput3d(text, cb) {
    api('POST', '/api/input', { text: text, xmin: view.xmin, xmax: view.xmax, ymin: view.ymin, ymax: view.ymax }, function (d) {
      setMsg(d.message, !d.ok);
      if (d.ok) load3d();
      if (cb) cb(d);
    });
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
      cv3d.setPointerCapture(ev.pointerId);
      return;
    }
    // 优先：点击 z 控制柄 → 拖动改 z（直观改高度）
    var zh = hitZHandle3d(ev.offsetX, ev.offsetY);
    if (zh) {
      var zpe = proj3([zh.x, zh.y, zh.z]);
      dragZHandle = { label: zh.label, sy0: ev.offsetY, z0: (zh.z != null ? zh.z : 0), handleScreenY: zpe.y };
      cv3d.setPointerCapture(ev.pointerId);
      return;
    }
    // 点击 3D 自由点 → 拖动（普通=沿基准平面 x/y；Shift=仅改 z 垂直移动）
    var hp = hitPoint3d(ev.offsetX, ev.offsetY);
    if (hp && hp.free) {
      var wasSelPt = (selected3d === hp.label);
      setSelected3d(hp.label);   // 点击控制点即选中（橙色菱形 + 光环）
      drag3d = { label: hp.label, sx: ev.offsetX, sy: ev.offsetY, z0: (hp.z != null ? hp.z : 0),
                 mode: ev.shiftKey ? 'z' : 'xy', moved: false, wasSelected: wasSelPt };
      cv3d.setPointerCapture(ev.pointerId);
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
      cv3d.setPointerCapture(ev.pointerId);
      ev.preventDefault();
      return;
    }
    camDrag = { x: ev.offsetX, y: ev.offsetY, shift: ev.shiftKey };
    cv3d.setPointerCapture(ev.pointerId);
  });
  // 阻止 3D 画布右键弹出浏览器菜单
  cv3d.addEventListener('contextmenu', function (ev) { ev.preventDefault(); });
  // 本地乐观平移（拖动期间即时反馈；服务器返回后 load3d 校正）
  function localShift3dEl(label, dx, dy, dz) {
    var e = findEl3d(label);
    if (!e) return;
    if (e.kind === 'point') { e.x += dx; e.y += dy; e.z = (e.z || 0) + dz; return; }
    var dt = e.data || {};
    if (e.objtype === 'cube' || e.objtype === 'polyhedron') {
      var vs = dt.verts || [];
      for (var i = 0; i < vs.length; i++) { vs[i][0] += dx; vs[i][1] += dy; vs[i][2] = (vs[i][2] || 0) + dz; }
    } else if (e.objtype === 'segment' || e.objtype === 'line2d' || e.objtype === 'line3d') {
      dt.x1 += dx; dt.y1 += dy; dt.z1 = (dt.z1 || 0) + dz;
      dt.x2 += dx; dt.y2 += dy; dt.z2 = (dt.z2 || 0) + dz;
    } else if (e.objtype === 'plane') {
      dt.ax += dx; dt.ay += dy; dt.az = (dt.az || 0) + dz;
    } else if (e.objtype === 'sphere') {
      dt.cx += dx; dt.cy += dy; dt.cz = (dt.cz || 0) + dz;
    } else if (e.objtype === 'polygon2d' || e.objtype === 'polyline2d') {
      var ps = dt.pts || [];
      for (var j = 0; j < ps.length; j++) { ps[j][0] += dx; ps[j][1] += dy; ps[j][2] = (ps[j][2] || 0) + dz; }
    }
  }
  // 累积位移合并提交（避免异步竞态）
  function flushObjShift3d() {
    if (objShift3d.pending) return;
    if (!objShift3d.dx && !objShift3d.dy && !objShift3d.dz) return;
    if (!drag3dObj) return;
    var label = drag3dObj.label;
    var ox = objShift3d.dx, oy = objShift3d.dy, oz = objShift3d.dz;
    objShift3d.dx = 0; objShift3d.dy = 0; objShift3d.dz = 0;
    var push = !objShift3d.pushed;
    objShift3d.pushed = true;
    objShift3d.pending = true;
    api('POST', '/api/shift', { label: label, dx: ox, dy: oy, dz: oz, push: push,
        xmin: view.xmin, xmax: view.xmax, ymin: view.ymin, ymax: view.ymax }, function (d) {
      objShift3d.pending = false;
      if (d && d.ok) load3d();
      else if (d && d.message) setMsg(d.message, true);
      if (drag3dObj && (objShift3d.dx || objShift3d.dy || objShift3d.dz)) flushObjShift3d();
    });
  }

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
      if (d.ok) cmdEl.value = '';
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
  function toLatex(s) {
    var out = '';
    var i = 0;
    var stack = [];  // 括号栈：'p'普通 '(' / 'f'函数 '(' / 's'sqrt{ / 'a'abs|
    while (i < s.length) {
      var ch = s[i];
      var hit = null;
      // 命令名 [ → \text{...} 保持
      for (var ci = 0; ci < CMD_W.length; ci++) {
        var cm = CMD_W[ci];
        if (s.slice(i, i + cm.length) === cm && s[i + cm.length] === '[') { hit = ['cmd', cm]; break; }
      }
      if (!hit) {
        for (var fi = 0; fi < FN_W.length; fi++) {
          var fw = FN_W[fi];
          if (s.slice(i, i + fw.length) === fw && s[i + fw.length] === '(') { hit = ['fn', fw]; break; }
        }
      }
      if (!hit) {
        for (var gi = 0; gi < GREEK_W.length; gi++) {
          var gw = GREEK_W[gi];
          if (s.slice(i, i + gw.length) === gw && !/[a-zA-Z]/.test(s[i + gw.length] || ' ')) { hit = ['gk', gw]; break; }
        }
      }
      if (hit && hit[0] === 'cmd') {
        out += '\\text{' + hit[1] + '}';
        i += hit[1].length;
        continue;
      }
      if (hit && hit[0] === 'fn') {
        if (hit[1] === 'sqrt') { out += '\\sqrt{'; stack.push('s'); }
        else if (hit[1] === 'abs') { out += '\\left|'; stack.push('a'); }
        else { out += FN_T[hit[1]] + '\\left('; stack.push('f'); }
        i += hit[1].length + 1;  // 跳过函数名与结构性的 '('
        continue;
      }
      if (hit && hit[0] === 'gk') {
        out += GREEK_T[hit[1]];
        i += hit[1].length;
        continue;
      }
      if (ch === '(') { out += '('; stack.push('p'); i++; continue; }
      if (ch === ')') {
        var kind = stack.pop() || 'p';
        if (kind === 's') out += '}';
        else if (kind === 'a') out += '\\right|';
        else if (kind === 'f') out += '\\right)';
        else out += ')';
        i++;
        continue;
      }
      if (ch === '^' || ch === '_') {
        var nx = s[i + 1];
        if (nx === '(' || nx === '{') {
          var depth = 1;
          var j = i + 2;
          var inner = '';
          while (j < s.length && depth > 0) {
            if (s[j] === '(' || s[j] === '{') depth++;
            else if (s[j] === ')' || s[j] === '}') { depth--; if (depth === 0) break; }
            inner += s[j];
            j++;
          }
          out += (ch === '^' ? '^{' : '_{') + toLatex(inner) + '}';
          i = j + 1;
          continue;
        }
        if (/[A-Za-z0-9\\u4e00-\\u9fff]/.test(nx || '')) {
          out += (ch === '^' ? '^{' : '_{') + nx + '}';
          i += 2;
          continue;
        }
        out += ch;
        i++;
        continue;
      }
      if (ch === '~') { out += '\\sim '; i++; continue; }
      if (ch === '*') { out += '\\cdot '; i++; continue; }
      if (ch === '<' && s[i + 1] === '=') { out += '\\le '; i += 2; continue; }
      if (ch === '>' && s[i + 1] === '=') { out += '\\ge '; i += 2; continue; }
      if (ch === '=') { out += '='; i++; continue; }
      out += ch;
      i++;
    }
    return out;
  }
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
  // 命令补全 datalist
  fetch('/api/commands').then(function (r) { return r.json(); }).then(function (d) {
    var dl = document.getElementById('cmd-list');
    var s = '';
    var dsp = d.display || {};
    for (var i = 0; i < d.commands.length; i++) {
      var nm = dsp[d.commands[i]] || d.commands[i];
      s += '<option value="' + nm + '["></option>';
    }
    dl.innerHTML = s;
  }).catch(function () {});
  btn('btn-help', function () {
    fetch('/api/commands').then(function (r) { return r.json(); }).then(function (d) {
      showHelpModal(d.commands, d.display || {});
    }).catch(function () { setMsg('加载命令失败', true); });
  });
  function showHelpModal(commands, display) {
    var ex = document.getElementById('help-pop');
    if (!ex) {
      ex = document.createElement('div');
      ex.id = 'help-pop';
      document.getElementById('app').appendChild(ex);
    }
    var head = lang === 'en' ? ('Commands (' + commands.length + ')') : ('可用命令（共 ' + commands.length + ' 条）');
    var casChips = CAS_COMMANDS.map(function (c) {
      return '<span class="hc hc-cas" data-cas="' + c.name + '" title="' + esc(c.zh) + ' / ' + esc(c.en) + '">' + c.name + '</span>';
    }).join('');
    ex.innerHTML = '<div class="help-head"><span>' + head + '</span><button id="help-close" class="x" title="' + (lang === 'en' ? 'Close' : '关闭') + '">✕</button></div>'
      + '<div class="help-search"><input id="help-search" type="text" placeholder="'
      + (lang === 'en' ? 'Filter commands (e.g. surface, volume, fit)' : '筛选命令（如 surface / volume / 拟合 / 曲面）') + '"></div>'
      + '<div class="help-body" id="help-cmds">' + commands.map(function (c) {
          var cnm = (display && display[c]) || c;
          return '<span class="hc hc-cmd" data-cmd="' + cnm + '" title="' + (lang === 'en' ? 'Click to insert' : '点击插入') + '">' + cnm + '</span>';
        }).join('') + '</div>'
      + '<div class="help-sec">' + (lang === 'en' ? 'CAS symbolic commands (click to use in the CAS panel)' : 'CAS 符号命令（点击可直接在 CAS 面板使用）') + '</div>'
      + '<div class="help-body">' + casChips + '</div>'
      + '<div class="help-foot">' + (lang === 'en' ? 'Click a command to insert Name[] into the input bar; CAS commands run in the CAS panel.' : '点击命令即在输入框插入 Name[]；CAS 命令在 CAS 面板执行。') + '</div>';
    var searchEl = ex.querySelector('#help-search');
    if (searchEl) {
      searchEl.addEventListener('input', function () {
        var q = searchEl.value.trim().toLowerCase();
        var chips = ex.querySelectorAll('#help-cmds .hc-cmd');
        for (var i = 0; i < chips.length; i++) {
          var nm = (chips[i].getAttribute('data-cmd') || '').toLowerCase();
          chips[i].style.display = (!q || nm.indexOf(q) !== -1) ? '' : 'none';
        }
      });
      searchEl.focus();
    }
    ex.style.display = 'block';
    ex.querySelector('#help-close').addEventListener('click', function () { ex.style.display = 'none'; });
    ex.addEventListener('click', function (ev) {
      var tc = ev.target.closest ? ev.target.closest('.hc-cmd') : null;
      if (tc) {
        var cname = tc.getAttribute('data-cmd') || '';   // 已是规范显示名（如 SurfacePoint）
        var inp = document.getElementById('cmd');
        if (inp) {
          inp.value = cname + '[]';
          inp.focus();
          try { inp.setSelectionRange(cname.length + 1, cname.length + 1); } catch (e) {}
        }
        return;
      }
      var t = ev.target.closest ? ev.target.closest('.hc-cas') : null;
      if (!t) return;
      var nm = t.getAttribute('data-cas');
      if (!casOpen) {
        casOpen = true;
        casPanel.style.display = 'flex';
        api('GET', '/api/cas', null, function (d) { renderCas(d.cells); });
      }
      casInsert(nm + '[]', 1);
    });
  }

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
  listEl.addEventListener('dblclick', function (ev) {
    var df = ev.target.closest ? ev.target.closest('.df') : null;
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
  function resetTool() {
    toolSel = [];
    pendingImage = null;
    updateToolButtons();
    setToolStatus();
    hintEl.textContent = toolHintText();
  }
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
  function snapHitLabel(wx, wy) {
    for (var shi = 0; shi < elements.length; shi++) {
      var she = elements[shi];
      if (she.kind !== 'point' || she.visible === false) continue;
      if (Math.abs(she.x - wx) < COORD && Math.abs(she.y - wy) < COORD) return she.label;
    }
    return null;
  }
  function toolPointAt(sx, sy, cb) {
    if (toolBusy) {
      toolPointQueue.push([sx, sy, cb]);
      return;
    }
    var lbl = hitAnyPoint(sx, sy);
    if (lbl) { cb(lbl); return; }
    var wx = wxp(sx), wy = wyp(sy);
    if (snapOn || shiftKeyPressed) {
      var snapped = snapPoint(wx, wy, niceStep(), sx, sy);
      wx = snapped[0]; wy = snapped[1];
      // 吸附后落点若与某个已有点重合 → 复用该点（避免网格点处新建重叠点）
      var rl = snapHitLabel(wx, wy);
      if (rl) { cb(rl); return; }
    }
    var prev = {};
    for (var i = 0; i < elements.length; i++) prev[elements[i].label] = true;
    toolBusy = true;
    postInput('(' + fmtW(wx) + ',' + fmtW(wy) + ')', function (ok) {
      toolBusy = false;
      if (!ok) { resetTool(); }
      else {
        for (var j = 0; j < elements.length; j++) {
          if (elements[j].kind === 'point' && !prev[elements[j].label]) { cb(elements[j].label); return; }
        }
        // 极快点击（down→up 无间隔）时元素列表可能尚未合并到本地：图片工具不能因此丢掉
        // 已选好的图片，否则用户需要重新选文件；其余工具仍走完整重置。
        if (activeTool === 'image' && pendingImage) {
          toolSel = [];
          updateToolButtons();
          setToolStatus();
        } else {
          resetTool();
        }
      }
      // 处理排队的下一次点击
      if (toolPointQueue.length) {
        var nx = toolPointQueue.shift();
        toolPointAt(nx[0], nx[1], nx[2]);
      }
    });
  }
  // 选中对象整体拖动：本地乐观平移
  function shiftLocal(label, dx, dy) {
    for (var i = 0; i < elements.length; i++) {
      var e = elements[i];
      if (e.label !== label) continue;
      if (e.kind === 'point') { e.x += dx; e.y += dy; }
      else if (e.kind === 'segment') { e.x1 += dx; e.y1 += dy; e.x2 += dx; e.y2 += dy; }
      else if (e.kind === 'circle') { e.cx += dx; e.cy += dy; }
      else if (e.kind === 'line') { e.c -= e.a * dx + e.b * dy; }
      else if (e.kind === 'polygon') { for (var k = 0; k < e.pts.length; k++) { e.pts[k][0] += dx; e.pts[k][1] += dy; } }
      else if (e.kind === 'arc') { e.cx += dx; e.cy += dy; }
      else if (e.kind === 'text') { e.x += dx; e.y += dy; }
      else if (e.kind === 'vector') { e.sx += dx; e.sy += dy; }
    }
    render();
  }

  // 屏幕坐标射线法：点是否在多边形内

  // 动点在其母体对象上的最近参数 t（PointOnPath/PointOnCircle 的驱动滑块值）
  function nearestPathParam(obj, wx, wy) {
    if (!obj) return null;
    if (obj.kind === 'segment') {
      var dx = obj.x2 - obj.x1, dy = obj.y2 - obj.y1, l2 = dx * dx + dy * dy;
      var t = l2 ? ((wx - obj.x1) * dx + (wy - obj.y1) * dy) / l2 : 0;
      return Math.max(0, Math.min(1, t));
    }
    if (obj.kind === 'circle') {
      var ang = Math.atan2(wy - obj.cy, wx - obj.cx);
      var a = ((ang % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2);
      return a / (Math.PI * 2);
    }
    if (obj.kind === 'arc') {
      var ang2 = Math.atan2(wy - obj.cy, wx - obj.cx);
      var span = obj.ang2 - obj.ang1;
      var tt = (ang2 - obj.ang1) / span;
      return Math.max(0, Math.min(1, tt));
    }
    if (obj.kind === 'line') {
      var a = obj.a, b = obj.b, c = obj.c, denom = a * a + b * b;
      if (denom < EPSILON) return 0.5;
      var spr = Math.sqrt(denom);
      var px = -a * c / denom, py = -b * c / denom;
      var s = (wx - px) * (-b / spr) + (wy - py) * (a / spr);  // 沿方向投影
      return Math.max(0, Math.min(1, s / 60 + 0.5));
    }
    if (obj.kind === 'ray') {
      var el = Math.hypot(obj.dx, obj.dy);
      var s = ((wx - obj.ox) * obj.dx + (wy - obj.oy) * obj.dy) / (el * el);
      return Math.max(0, Math.min(1, (s * el) / 20));
    }
    if (obj.kind === 'polygon' && obj.pts && obj.pts.length >= 3) {
      var best = null, bestD = 1e18, bestT = 0, cum = 0, total = 0;
      var segs = [];
      for (var i = 0; i < obj.pts.length; i++) {
        var j = (i + 1) % obj.pts.length;
        var ln = Math.hypot(obj.pts[j][0] - obj.pts[i][0], obj.pts[j][1] - obj.pts[i][1]);
        segs.push([i, j, ln]);
        total += ln;
      }
      for (var k = 0; k < segs.length; k++) {
        var sd = segs[k], i0 = sd[0], j0 = sd[1], ln = sd[2];
        var x1 = obj.pts[i0][0], y1 = obj.pts[i0][1], x2 = obj.pts[j0][0], y2 = obj.pts[j0][1];
        var ddx = x2 - x1, ddy = y2 - y1, l2 = ddx * ddx + ddy * ddy;
        var t = l2 ? ((wx - x1) * ddx + (wy - y1) * ddy) / l2 : 0;
        t = Math.max(0, Math.min(1, t));
        var qx = x1 + t * ddx, qy = y1 + t * ddy;
        var d = Math.hypot(wx - qx, wy - qy);
        if (d < bestD) { bestD = d; bestT = cum + t * ln; }
        cum += ln;
      }
      return total > 0 ? bestT / total : 0;
    }
    return null;
  }
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
  function conicCoeffs(pts) {
    var m = [];
    for (var i = 0; i < 5; i++) {
      var x = pts[i][0], y = pts[i][1];
      m.push([x * x, x * y, y * y, x, y, 1]);
    }
    var rows = 5, cols = 6, r = 0, pivotCol = [];
    for (var c = 0; c < cols && r < rows; c++) {
      var pr = -1;
      for (var rr = r; rr < rows; rr++) if (Math.abs(m[rr][c]) > COORD) { pr = rr; break; }
      if (pr < 0) continue;
      var t0 = m[r]; m[r] = m[pr]; m[pr] = t0;
      var piv = m[r][c];
      for (var cc = 0; cc < cols; cc++) m[r][cc] /= piv;
      for (var rr2 = 0; rr2 < rows; rr2++) if (rr2 !== r) {
        var f2 = m[rr2][c];
        if (Math.abs(f2) > EPSILON) for (var cc2 = 0; cc2 < cols; cc2++) m[rr2][cc2] -= f2 * m[r][cc2];
      }
      pivotCol.push(c);
      r++;
    }
    var freeCol = -1;
    for (var c2 = 0; c2 < cols; c2++) if (pivotCol.indexOf(c2) === -1) { freeCol = c2; break; }
    if (freeCol < 0) return null;
    var xv = [0, 0, 0, 0, 0, 0];
    xv[freeCol] = 1;
    for (var pr2 = pivotCol.length - 1; pr2 >= 0; pr2--) {
      var pc = pivotCol[pr2];
      var s = 0;
      for (var cc3 = pc + 1; cc3 < cols; cc3++) s += m[pr2][cc3] * xv[cc3];
      xv[pc] = -s;
    }
    var any = false;
    for (var k = 0; k < 6; k++) if (Math.abs(xv[k]) > EPSILON) { any = true; break; }
    return any ? xv : null;
  }
  function conicPreviewSegs(coeff) {
    var a = coeff[0], b = coeff[1], c = coeff[2], d = coeff[3], e = coeff[4], f = coeff[5];
    function F(x, y) { return a * x * x + b * x * y + c * y * y + d * x + e * y + f; }
    var span = Math.max(view.xmax - view.xmin, view.ymax - view.ymin);
    var cell = span / 48;
    var x0 = view.xmin - cell, x1 = view.xmax + cell, y0 = view.ymin - cell, y1 = view.ymax + cell;
    var nx = Math.ceil((x1 - x0) / cell), ny = Math.ceil((y1 - y0) / cell);
    var segs = [];
    function edge(p1x, p1y, f1, p2x, p2y, f2) {
      var tt = f1 / (f1 - f2);
      return [p1x + tt * (p2x - p1x), p1y + tt * (p2y - p1y)];
    }
    function triSeg(ax2, ay2, fa, bx2, by2, fb, cx2, cy2, fc) {
      var n0 = (fa < 0 ? 1 : 0) + (fb < 0 ? 1 : 0) + (fc < 0 ? 1 : 0);
      if (n0 === 0 || n0 === 3) return;
      var v = [[ax2, ay2, fa], [bx2, by2, fb], [cx2, cy2, fc]];
      var hits = [];
      for (var i = 0; i < 3; i++) {
        var j = (i + 1) % 3;
        if ((v[i][2] < 0) !== (v[j][2] < 0)) hits.push(edge(v[i][0], v[i][1], v[i][2], v[j][0], v[j][1], v[j][2]));
      }
      if (hits.length === 2) segs.push([hits[0][0], hits[0][1], hits[1][0], hits[1][1]]);
    }
    for (var ix = 0; ix < nx; ix++) for (var iy = 0; iy < ny; iy++) {
      var X0 = x0 + ix * cell, X1 = X0 + cell, Y0 = y0 + iy * cell, Y1 = Y0 + cell;
      var bl = F(X0, Y0), br = F(X1, Y0), tr = F(X1, Y1), tl = F(X0, Y1);
      triSeg(X0, Y0, bl, X1, Y0, br, X0, Y1, tl);
      triSeg(X1, Y0, br, X1, Y1, tr, X0, Y1, tl);
    }
    return segs;
  }
  // 工具绘制中的预览形状（部分参数完成 → 随鼠标临时图形）
  function computeToolPreview(sel, mx, my) {
    var wx = wxp(mx), wy = wyp(my);
    if (snapOn || shiftKeyPressed) {
      var snapped = snapPoint(wx, wy, niceStep(), mx, my);
      wx = snapped[0]; wy = snapped[1];
    }
    if (!sel.length) return null;
    if (activeTool === 'circle' && sel.length === 1) {
      var cc = findEl(sel[0]);
      if (!cc) return null;
      return { type: 'circle', cx: cc.x, cy: cc.y, r: Math.hypot(wx - cc.x, wy - cc.y) };
    }
    if ((activeTool === 'segment' || activeTool === 'line' || activeTool === 'ray' ||
         activeTool === 'vector' || activeTool === 'semicircle' || activeTool === 'perp' ||
         activeTool === 'parallel') && sel.length === 1 && activeTool !== 'perp' && activeTool !== 'parallel') {
      var p1 = findEl(sel[0]);
      if (!p1) return null;
      return { type: 'seg', x1: p1.x, y1: p1.y, x2: wx, y2: wy };
    }
    if ((activeTool === 'polygon' || activeTool === 'rigidpolygon' || activeTool === 'polyline') && sel.length >= 1) {
      var pts = [];
      for (var k = 0; k < sel.length; k++) {
        var pp = findEl(sel[k]);
        if (pp) pts.push([pp.x, pp.y]);
      }
      pts.push([wx, wy]);
      return { type: 'poly', pts: pts };
    }
    if (activeTool === 'ellipse' && sel.length === 2) {
      var el1 = findEl(sel[0]), el2 = findEl(sel[1]);
      if (!el1 || !el2) return null;
      var efc = Math.hypot(el2.x - el1.x, el2.y - el1.y) / 2;
      var e1 = Math.hypot(wx - el1.x, wy - el1.y), e2 = Math.hypot(wx - el2.x, wy - el2.y);
      var esa = (e1 + e2) / 2;              // 半长轴 = (|PF1|+|PF2|)/2
      if (esa <= efc) return null;          // 2a <= 焦距 → 无椭圆
      var esb = Math.sqrt(esa * esa - efc * efc);
      return { type: 'conic', ctype: 'ellipse', cx: (el1.x + el2.x) / 2, cy: (el1.y + el2.y) / 2,
               semi_a: esa, semi_b: esb, angle: Math.atan2(el2.y - el1.y, el2.x - el1.x) };
    }
    if (activeTool === 'hyperbola' && sel.length === 2) {
      var hl1 = findEl(sel[0]), hl2 = findEl(sel[1]);
      if (!hl1 || !hl2) return null;
      var hfc = Math.hypot(hl2.x - hl1.x, hl2.y - hl1.y) / 2;
      var h1 = Math.hypot(wx - hl1.x, wy - hl1.y), h2 = Math.hypot(wx - hl2.x, wy - hl2.y);
      var hsa = Math.abs(h1 - h2) / 2;      // 实半轴 = ||PF1|-|PF2||/2
      if (hsa < COORD || hsa >= hfc) return null;
      var hsb = Math.sqrt(hfc * hfc - hsa * hsa);
      return { type: 'conic', ctype: 'hyperbola', cx: (hl1.x + hl2.x) / 2, cy: (hl1.y + hl2.y) / 2,
               semi_a: hsa, semi_b: hsb, angle: Math.atan2(hl2.y - hl1.y, hl2.x - hl1.x) };
    }
    if (activeTool === 'parabola' && sel.length === 1) {
      var pfc = findEl(sel[0]);
      if (!pfc) return null;
      var dL = hitObject(mx, my, ['line', 'segment', 'ray']);
      if (!dL) return null;
      var dlEl = findEl(dL);
      if (!dlEl) return null;
      // 准线系数 A x + B y + C = 0
      var qA, qB, qC;
      if (dlEl.kind === 'line') { qA = dlEl.a; qB = dlEl.b; qC = dlEl.c; }
      else if (dlEl.kind === 'segment') { var sdx = dlEl.x2 - dlEl.x1, sdy = dlEl.y2 - dlEl.y1; qA = -sdy; qB = sdx; qC = -(qA * dlEl.x1 + qB * dlEl.y1); }
      else { qA = -dlEl.uy; qB = dlEl.ux; qC = -(qA * dlEl.ox + qB * dlEl.oy); }
      var qden = qA * qA + qB * qB;
      if (qden < EPSILON) return null;
      var qt = -(qA * pfc.x + qB * pfc.y + qC) / qden;
      var qhx = pfc.x + qA * qt, qhy = pfc.y + qB * qt;   // 焦点到准线垂足
      var qp = Math.hypot(pfc.x - qhx, pfc.y - qhy) / 2;  // p（顶点到焦点/准线距离）
      if (qp < COORD) return null;
      return { type: 'conic', ctype: 'parabola', cx: (pfc.x + qhx) / 2, cy: (pfc.y + qhy) / 2,
               semi_a: qp, angle: Math.atan2(pfc.y - qhy, pfc.x - qhx) };
    }
    if (activeTool === 'image' && pendingImage && sel.length === 1) {
      var aImg = findEl(sel[0]);
      if (!aImg) return null;
      var wImg = Math.hypot(wx - aImg.x, wy - aImg.y);
      if (wImg < COORD) return null;
      var uxI = (wx - aImg.x) / wImg, uyI = (wy - aImg.y) / wImg;
      var hImg = wImg * pendingImage.ratio;
      var vxI = -uyI, vyI = uxI;
      return { type: 'poly', pts: [[aImg.x, aImg.y], [wx, wy],
                                   [wx + hImg * vxI, wy + hImg * vyI],
                                   [aImg.x + hImg * vxI, aImg.y + hImg * vyI],
                                   [aImg.x, aImg.y]] };
    }
    if (activeTool === 'conic5' && sel.length === 4) {
      var p5 = [];
      for (var c5 = 0; c5 < 4; c5++) { var el5 = findEl(sel[c5]); if (!el5) return null; p5.push([el5.x, el5.y]); }
      p5.push([wx, wy]);
      var cf = conicCoeffs(p5);
      if (!cf) return null;
      return { type: 'conic5', pts: p5, preSegs: conicPreviewSegs(cf) };
    }
    if (activeTool === 'arc' || activeTool === 'sector') {
      if (sel.length === 1) {
        var ac = findEl(sel[0]);
        if (ac) return { type: 'circle', cx: ac.x, cy: ac.y, r: Math.hypot(wx - ac.x, wy - ac.y) };  // 圆心已定：预览随鼠标半径的圆
      }
      if (sel.length === 2) {
        var ac2 = findEl(sel[0]), as2 = findEl(sel[1]);
        if (ac2 && as2) return { type: 'circle', cx: ac2.x, cy: ac2.y, r: Math.hypot(as2.x - ac2.x, as2.y - ac2.y) };  // 起点已定：预览过起点的圆
      }
    }
    return null;
  }

  function hitObject(sx, sy, kinds) {
    for (var i = 0; i < elements.length; i++) {
      var e = elements[i];
      if (kinds.indexOf(e.kind) === -1) continue;
      if (e.kind === 'point') {
        var dx = sxp(e.x) - sx, dy = syp(e.y) - sy;
        if (dx * dx + dy * dy <= 81) return e.label;
      } else if (e.kind === 'segment') {
        if (distToSeg(sx, sy, sxp(e.x1), syp(e.y1), sxp(e.x2), syp(e.y2)) <= 10) return e.label;
      } else if (e.kind === 'line' || e.kind === 'ray') {
        if (e.seg && distToSeg(sx, sy, sxp(e.seg[0]), syp(e.seg[1]), sxp(e.seg[2]), syp(e.seg[3])) <= 10) return e.label;
      } else if (e.kind === 'circle') {
        var d = Math.hypot(sxp(e.cx) - sx, syp(e.cy) - sy);
        if (Math.abs(d - e.r * scale) <= 10) return e.label;
      } else if (e.kind === 'vector') {
        if (distToSeg(sx, sy, sxp(e.sx || 0), syp(e.sy || 0), sxp((e.sx || 0) + e.dx), syp((e.sy || 0) + e.dy)) <= 14) return e.label;
      } else if (e.kind === 'arc') {
        var arD = Math.hypot(sxp(e.cx) - sx, syp(e.cy) - sy);
        if (Math.abs(arD - e.r * scale) <= 10) return e.label;
      } else if (e.kind === 'polygon' && e.pts && e.pts.length >= 3) {
        for (var pli = 0; pli < e.pts.length; pli++) {
          var pj = (pli + 1) % e.pts.length;
          if (distToSeg(sx, sy, sxp(e.pts[pli][0]), syp(e.pts[pli][1]), sxp(e.pts[pj][0]), syp(e.pts[pj][1])) <= 10) return e.label;
        }
        // 点击多边形内部任意点也可选中（射线法）
        if (pointInPoly(sx, sy, e.pts)) return e.label;
      } else if (e.kind === 'image' && e.corners && e.corners.length === 4) {
        if (pointInPoly(sx, sy, e.corners)) return e.label;
      } else if (e.kind === 'function' && e.samples) {
        var prevF = null;
        for (var fi2 = 0; fi2 < e.samples.length; fi2++) {
          var fy = e.samples[fi2][1];
          if (fy === null || !isFinite(fy)) { prevF = null; continue; }
          var fpt = [sxp(e.samples[fi2][0]), syp(fy)];
          if (prevF && distToSeg(sx, sy, prevF[0], prevF[1], fpt[0], fpt[1]) <= 10) return e.label;
          if (!prevF && Math.hypot(fpt[0] - sx, fpt[1] - sy) <= 10) return e.label;
          prevF = fpt;
        }
      } else if (e.kind === 'parametric' || e.kind === 'polar') {
        for (var pi2b = 0; pi2b < (e.pts || []).length; pi2b++) {
          if (Math.hypot(sxp(e.pts[pi2b][0]) - sx, syp(e.pts[pi2b][1]) - sy) <= 10) return e.label;
        }
      } else if (e.kind === 'implicit' && e.segs) {
        for (var isi2 = 0; isi2 < e.segs.length; isi2++) {
          if (distToSeg(sx, sy, sxp(e.segs[isi2][0]), syp(e.segs[isi2][1]), sxp(e.segs[isi2][2]), syp(e.segs[isi2][3])) <= 10) return e.label;
        }
      } else if (e.kind === 'conic' && e.segs) {
        for (var csi = 0; csi < e.segs.length; csi++) {
          if (distToSeg(sx, sy, sxp(e.segs[csi][0]), syp(e.segs[csi][1]), sxp(e.segs[csi][2]), syp(e.segs[csi][3])) <= 10) return e.label;
        }
      } else if (CHART_KINDS.indexOf(e.kind) !== -1) {
        // 统计图：整张图一个命中盒（绘制时记录），拖拽/选中都按整体处理
        var cb = chartBoxes[e.label];
        if (cb && sx >= cb.x0 - 2 && sx <= cb.x1 + 2 && sy >= cb.y0 - 2 && sy <= cb.y1 + 2) return e.label;
      } else if (e.kind === 'conic' && conicPathPts(e)) {
        var cpath = conicPathPts(e);
        for (var cpi = 0; cpi < cpath.length; cpi++) {
          var cpc = cpath[cpi];
          for (var cq = 0; cq + 1 < cpc.length; cq++) {
            if (distToSeg(sx, sy, sxp(cpc[cq][0]), syp(cpc[cq][1]), sxp(cpc[cq + 1][0]), syp(cpc[cq + 1][1])) <= 10) return e.label;
          }
        }
      }
    }
    return null;
  }
  function finishPolygon() {
    if (toolSel.length < 3) return;
    var fCmd = activeTool === 'rigidpolygon' ? 'RigidPolygon' : 'Polygon';
    postInput(fCmd + '[' + toolSel.join(',') + ']', function (ok) { if (ok) resetTool(); });
  }
  function finishPolyline() {
    if (toolSel.length < 2) return;
    postInput('Polyline[' + toolSel.join(',') + ']', function (ok) { if (ok) resetTool(); });
  }
  function toolCanvasClick(sx, sy) {
    if (activeTool === 'point') {
      toolPointAt(sx, sy, function () { resetTool(); });
      return;
    }
    if (activeTool === 'segment' || activeTool === 'circle') {
      toolPointAt(sx, sy, function (lbl) {
        toolSel.push(lbl);
        if (toolSel.length === 2) {
          var cmd = activeTool === 'segment'
            ? 'Segment[' + toolSel[0] + ',' + toolSel[1] + ']'
            : 'Circle[' + toolSel[0] + ',' + toolSel[1] + ']';
          postInput(cmd, function (ok) { if (ok) resetTool(); });
        } else setToolStatus();
      });
      return;
    }
    if (activeTool === 'midpoint') {
      // 点击线段 → 一步创建线段中点；否则收集两个点
      var segHit = hitObject(sx, sy, ['segment']);
      if (segHit) {
        postInput('Midpoint[' + segHit + ']', function (ok) { if (ok) resetTool(); });
        return;
      }
      var ml = hitObject(sx, sy, ['point']);
      if (!ml) { setMsg(lang === 'en' ? 'Click a point or segment' : '请点击点或线段', true); return; }
      toolSel.push(ml);
      if (toolSel.length === 2) {
        postInput('Midpoint[' + toolSel.join(',') + ']', function (ok) { if (ok) resetTool(); });
      } else setToolStatus();
      return;
    }
    if (activeTool === 'dist') {
      // 点击线段 → 求其长度；否则收集 点+点/线/圆 → Distance
      var dseg = hitObject(sx, sy, ['segment']);
      if (dseg) { postInput('Length[' + dseg + ']', function (ok) { if (ok) resetTool(); }); return; }
      var dpt = hitObject(sx, sy, ['point']);
      if (!dpt) { setMsg(lang === 'en' ? 'Click a point or segment' : '请点击点或线段', true); return; }
      if (toolSel.length === 0) { toolSel.push(dpt); setToolStatus(); return; }
      var dO2 = hitObject(sx, sy, ['point', 'line', 'segment', 'ray', 'circle']);
      if (!dO2) { setMsg(lang === 'en' ? 'Click a point, line or circle' : '请点击点/直线/圆', true); return; }
      postInput('Distance[' + toolSel[0] + ',' + dO2 + ']', function (ok) { if (ok) resetTool(); });
      return;
    }
    if (activeTool === 'slope') {
      var slL = hitObject(sx, sy, ['line', 'segment', 'ray']);
      if (!slL) { setMsg(lang === 'en' ? 'Click a line/segment/ray' : '请点击直线/线段/射线', true); return; }
      postInput('Slope[' + slL + ']', function (ok) { if (ok) resetTool(); });
      return;
    }
    if (activeTool === 'angle') {
      toolCollectPoints(3, function (s) { return 'Angle[' + s.join(',') + ']'; }, sx, sy);
      return;
    }
    if (activeTool === 'area' || activeTool === 'perimeter') {
      var kindsA = activeTool === 'area' ? ['polygon', 'circle', 'conic'] : ['polygon', 'circle'];
      var aHit = hitObject(sx, sy, kindsA);
      if (!aHit) { setMsg(lang === 'en' ? 'Click a polygon/circle' : '请点击多边形或圆', true); return; }
      var acmd = activeTool === 'area' ? 'Area[' : 'Perimeter[';
      postInput(acmd + aHit + ']', function (ok) { if (ok) resetTool(); });
      return;
    }
    // 视图工具：放大/缩小/复位（不创建对象）
    if (activeTool === 'zoomin' || activeTool === 'zoomout' || activeTool === 'home') {
      if (activeTool === 'home') {
        view.xmin = -8; view.xmax = 8; view.ymin = -8; view.ymax = 8; scale = 60;
      } else {
        var zf = activeTool === 'zoomin' ? 1.3 : 1 / 1.3;
        var zwx = wxp(sx), zwy = wyp(sy);
        scale *= zf;
        scale = Math.max(2, Math.min(200000, scale));
        view.xmin = zwx - sx / scale;
        view.xmax = view.xmin + cssW / scale;
        view.ymin = zwy - (cssH - sy) / scale;
        view.ymax = view.ymin + cssH / scale;
      }
      render();
      clearTimeout(canvas._zw);
      canvas._zw = setTimeout(loadState, 180);
      resetTool();
      return;
    }
    if (activeTool === 'perp' || activeTool === 'parallel') {
      if (toolSel.length === 0) {
        var ll = hitObject(sx, sy, ['line', 'segment', 'ray']);
        if (!ll) { setMsg(lang === 'en' ? 'Click a line or segment' : '请点击直线或线段', true); return; }
        toolSel.push(ll);
        setToolStatus();
        return;
      }
      toolPointAt(sx, sy, function (ptLbl) {
        var cmd = activeTool === 'perp'
          ? 'PerpendicularLine[' + ptLbl + ',' + toolSel[0] + ']'
          : 'Line[' + ptLbl + ',' + toolSel[0] + ']';
        postInput(cmd, function (ok) { if (ok) resetTool(); });
      });
      return;
    }
    if (activeTool === 'tangent') {
      if (toolSel.length === 0) {
        var cl = hitObject(sx, sy, ['circle', 'conic', 'line', 'segment', 'arc', 'function']);
        if (!cl) { setMsg(lang === 'en' ? 'Click a circle or curve' : '请点击圆或曲线', true); return; }
        toolSel.push(cl);
        setToolStatus();
        return;
      }
      toolPointAt(sx, sy, function (ptLbl) {
        postInput('Tangent[' + toolSel[0] + ',' + ptLbl + ']', function (ok) { if (ok) resetTool(); });
      });
      return;
    }
    if (activeTool === 'polygon' || activeTool === 'rigidpolygon') {
      var firstLbl = toolSel.length ? toolSel[0] : null;
      // 宽容差命中第一个顶点 → 自动闭合（已选 ≥2 点；18px 屏幕半径，方便回到起点收口）
      if (firstLbl && toolSel.length >= 2) {
        // 与预览/建点一致：吸附开启时先修正点击落点（网格吸附可能远离鼠标原始位置）
        var plx = wxp(sx), ply = wyp(sy);
        if (snapOn || shiftKeyPressed) {
          var plsn = snapPoint(plx, ply, niceStep(), sx, sy);
          plx = plsn[0]; ply = plsn[1];
        }
        for (var fpi = 0; fpi < elements.length; fpi++) {
          var fpel = elements[fpi];
          if (fpel.label !== firstLbl || fpel.kind !== 'point') continue;
          var fdx = (fpel.x - plx) * scale, fdy = (fpel.y - ply) * scale;
          if (fdx * fdx + fdy * fdy <= 18 * 18) { finishPolygon(); return; }
          break;
        }
      }
      var hitLbl = hitAnyPoint(sx, sy);
      // 点击已选中的其他顶点 → 忽略（提示回起点闭合）
      if (hitLbl && toolSel.indexOf(hitLbl) !== -1) {
        setMsg(lang === 'en' ? 'Click the first point to close' : '点击第一个点闭合多边形', true);
        return;
      }
      toolPointAt(sx, sy, function (lbl) {
        if (toolSel.indexOf(lbl) !== -1) {
          setMsg(lang === 'en' ? 'Click the first point to close' : '点击第一个点闭合多边形', true);
          return;
        }
        toolSel.push(lbl);
        updateToolButtons();
        setToolStatus();
      });
      return;
    }
    // 通用多点收集工具（直线/半圆/圆弧/椭圆/双曲线）
    function toolCollectPoints(n, makeCmd, sx2, sy2) {
      toolPointAt(sx2, sy2, function (lbl) {
        toolSel.push(lbl);
        if (toolSel.length >= n) {
          var cmd = makeCmd(toolSel);
          postInput(cmd, function (ok) { if (ok) resetTool(); });
        } else setToolStatus();
      });
    }
    if (activeTool === 'conic5') {
      // 五点圆锥曲线：前 4 点击点，第 5 击落点（过程中虚线预览随鼠标变化）
      toolCollectPoints(5, function (s) { return 'Conic[' + s.join(',') + ']'; }, sx, sy);
      return;
    }
    if (activeTool === 'ray' || activeTool === 'vector' || activeTool === 'perpbis') {
      if (activeTool === 'perpbis' && toolSel.length === 0) {
        var sl = hitObject(sx, sy, ['segment', 'line', 'ray']);
        if (sl) { postInput('PerpendicularBisector[' + sl + ']', function (ok) { if (ok) resetTool(); }); return; }
      }
      toolCollectPoints(2, function (s) {
        if (activeTool === 'ray') return 'Ray[' + s.join(',') + ']';
        if (activeTool === 'vector') return 'Vector[' + s.join(',') + ']';
        return 'PerpendicularBisector[' + s.join(',') + ']';
      }, sx, sy);
      return;
    }
    if (activeTool === 'anglebis') {
      toolCollectPoints(3, function (s) { return 'AngleBisector[' + s.join(',') + ']'; }, sx, sy);
      return;
    }
    if (activeTool === 'regpoly') {
      toolPointAt(sx, sy, function (lbl) {
        toolSel.push(lbl);
        if (toolSel.length >= 2) {
          var nTxt = prompt(lang === 'en' ? 'Number of sides (3-100):' : '边数（3-100）：');
          if (nTxt === null || !nTxt.trim()) { resetTool(); return; }
          var nv = parseInt(nTxt, 10);
          if (!nv || nv < 3 || nv > 100) { setMsg(lang === 'en' ? 'Sides must be 3-100' : '边数需在 3~100', true); resetTool(); return; }
          postInput('RegularPolygon[' + toolSel.join(',') + ',' + nv + ']', function (ok) { if (ok) resetTool(); });
        } else setToolStatus();
      });
      return;
    }
    var TRANS_KINDS = ['point', 'segment', 'ray', 'circle', 'polygon', 'line', 'polyline', 'vector', 'conic'];
    if (activeTool === 'foot') {
      if (toolSel.length === 0) {
        toolPointAt(sx, sy, function (l) { toolSel.push(l); setToolStatus(); });
        return;
      }
      var fl = hitObject(sx, sy, ['line', 'segment', 'ray']);
      if (!fl) { setMsg(lang === 'en' ? 'Click a line/segment/ray' : '请点击直线/线段/射线', true); return; }
      postInput('Foot[' + toolSel[0] + ',' + fl + ']', function (ok) { if (ok) resetTool(); });
      return;
    }
    if (activeTool === 'incenter' || activeTool === 'centroid' || activeTool === 'incircle') {
      var poly = hitObject(sx, sy, ['polygon']);
      if (!poly) { setMsg(lang === 'en' ? 'Click a triangle polygon' : '请点击三角形多边形', true); return; }
      var ccmd = activeTool === 'incenter' ? 'Incenter[' + poly + ']'
        : activeTool === 'centroid' ? 'Centroid[' + poly + ']' : 'Incircle[' + poly + ']';
      postInput(ccmd, function (ok) { if (ok) resetTool(); });
      return;
    }
    if (activeTool === 'reflect') {
      if (toolSel.length === 0) {
        var ro = hitObject(sx, sy, TRANS_KINDS);
        if (!ro) { setMsg(lang === 'en' ? 'Click object to reflect' : '请点击要反射的对象', true); return; }
        toolSel.push(ro); setToolStatus(); return;
      }
      var axis = hitObject(sx, sy, ['line', 'segment', 'ray']);
      var center = hitAnyPoint(sx, sy);
      var mirror = axis || center;
      if (!mirror) { setMsg(lang === 'en' ? 'Click axis line or center point' : '请点击轴对称线或中心点', true); return; }
      postInput('Reflect[' + toolSel[0] + ',' + mirror + ']', function (ok) { if (ok) resetTool(); });
      return;
    }
    if (activeTool === 'rotate') {
      if (toolSel.length === 0) {
        var rlo = hitObject(sx, sy, TRANS_KINDS);
        if (!rlo) { setMsg(lang === 'en' ? 'Click object to rotate' : '请点击要旋转的对象', true); return; }
        toolSel.push(rlo); setToolStatus(); return;
      }
      toolPointAt(sx, sy, function (c) {
        var angTxt = prompt(lang === 'en' ? 'Rotation angle (degrees):' : '旋转角度（度）：');
        if (angTxt === null || angTxt.trim() === '') { resetTool(); return; }
        var av = parseFloat(angTxt);
        if (isNaN(av)) { setMsg(lang === 'en' ? 'Enter a number' : '请输入数字角度', true); resetTool(); return; }
        postInput('Rotate[' + toolSel[0] + ',' + av + ',' + c + ']', function (ok) { if (ok) resetTool(); });
      });
      return;
    }
    if (activeTool === 'translate') {
      if (toolSel.length === 0) {
        var tlo = hitObject(sx, sy, TRANS_KINDS);
        if (!tlo) { setMsg(lang === 'en' ? 'Click object to translate' : '请点击要平移的对象', true); return; }
        toolSel.push(tlo); setToolStatus(); return;
      }
      if (toolSel.length === 1) {
        // 优先：点击已有向量对象 → 直接平移
        var vHit = hitObject(sx, sy, ['vector']);
        if (vHit) {
          postInput('Translate[' + toolSel[0] + ',' + vHit + ']', function (ok) { if (ok) resetTool(); });
          return;
        }
        toolPointAt(sx, sy, function (p1) { toolSel.push(p1); setToolStatus(); });
        return;
      }
      toolPointAt(sx, sy, function (p2) {
        var p1 = toolSel[1], e1 = null, e2 = null;
        for (var ti = 0; ti < elements.length; ti++) {
          if (elements[ti].label === p1 && elements[ti].kind === 'point') e1 = elements[ti];
          if (elements[ti].label === p2 && elements[ti].kind === 'point') e2 = elements[ti];
        }
        if (!e1 || !e2) { resetTool(); return; }
        var tdx = e2.x - e1.x, tdy = e2.y - e1.y;
        postInput('Translate[' + toolSel[0] + ',(' + fmtW(tdx) + ',' + fmtW(tdy) + ')]', function (ok) { if (ok) resetTool(); });
      });
      return;
    }
    if (activeTool === 'dilate') {
      if (toolSel.length === 0) {
        var dlo = hitObject(sx, sy, TRANS_KINDS);
        if (!dlo) { setMsg(lang === 'en' ? 'Click object' : '请点击要位似的对象', true); return; }
        toolSel.push(dlo); setToolStatus(); return;
      }
      toolPointAt(sx, sy, function (c) {
        var kTxt = prompt(lang === 'en' ? 'Dilation ratio (k):' : '位似比例 k：');
        if (kTxt === null || kTxt.trim() === '') { resetTool(); return; }
        var kv = parseFloat(kTxt);
        if (isNaN(kv)) { setMsg(lang === 'en' ? 'Enter a number' : '请输入数字比例', true); resetTool(); return; }
        postInput('Dilate[' + toolSel[0] + ',' + kv + ',' + c + ']', function (ok) { if (ok) resetTool(); });
      });
      return;
    }
    if (activeTool === 'image') {
      if (!pendingImage) { setMsg(lang === 'en' ? 'Choose an image file first' : '请先选择图片文件', true); cancelTool(); return; }
      toolPointAt(sx, sy, function (lbl) {
        toolSel.push(lbl);
        if (toolSel.length < 2) { updateToolButtons(); setToolStatus(); return; }
        var aLbl = toolSel[0], bLbl = toolSel[1];
        if (aLbl === bLbl) { setMsg(lang === 'en' ? 'Base points must differ' : '两个基点不能相同', true); return; }
        postInput('Image[' + aLbl + ',' + bLbl + ',' + pendingImage.id + ']', function () {
          pendingImage = null;
          cancelTool();   // 插入一张后结束工具（再插入需重新选文件）
        });
      });
      return;
    }
    if (activeTool === 'invert') {
      if (toolSel.length === 0) {
        var invObj = hitObject(sx, sy, ['point', 'line', 'segment', 'ray', 'circle', 'polygon', 'polyline', 'arc', 'vector', 'conic', 'function', 'parametric', 'polar', 'implicit', 'locus']);
        if (!invObj) { setMsg(lang === 'en' ? 'Click an object to invert' : '请点击要反演的对象', true); return; }
        toolSel.push(invObj); setToolStatus(); return;
      }
      var invC = hitObject(sx, sy, ['circle']);
      if (!invC) { setMsg(lang === 'en' ? 'Click the inversion circle' : '请点击反演圆', true); return; }
      postInput('Invert[' + toolSel[0] + ',' + invC + ']', function (ok) { if (ok) resetTool(); });
      return;
    }
    if (activeTool === 'pointoncircle') {
      var pc = hitObject(sx, sy, ['circle']);
      if (!pc) { setMsg(lang === 'en' ? 'Click a circle' : '请点击圆', true); return; }
      postInput('PointOnCircle[' + pc + ']', function (ok) { if (ok) resetTool(); });
      return;
    }
    if (activeTool === 'function') {
      var fTxt = prompt(lang === 'en' ? 'Function expression (e.g. x^2+1, sin(x)):' : '函数表达式（如 x^2+1、sin(x)）：');
      if (fTxt === null || !fTxt.trim()) { resetTool(); return; }
      fTxt = fTxt.trim();
      // 带完整定义（f(x)=...）则原样，否则补 (x)=expr 自动命名
      var fcmd = /^\s*[A-Za-z_][A-Za-z0-9_]*\s*\([^)]*\)\s*=/.test(fTxt) ? fTxt : '(x)=' + fTxt;
      postInput(fcmd, function (ok) { if (ok) resetTool(); });
      return;
    }
    if (activeTool === 'slider') {
      var sTxt = prompt(lang === 'en' ? 'min,max,step (e.g. 0,10,0.5):' : '最小值,最大值,增量（如 0,10,0.5）：', '0,10,0.1');
      if (sTxt === null || !sTxt.trim()) { resetTool(); return; }
      var sp = sTxt.split(','), slo = parseFloat(sp[0]), shi = parseFloat(sp[1] || '10'), sstep = parseFloat(sp[2]);
      if (isNaN(slo) || isNaN(shi) || shi <= slo) { setMsg(lang === 'en' ? 'Invalid min/max' : '无效的最小/最大值', true); resetTool(); return; }
      var scmd = 'Slider[' + slo + ',' + shi;
      if (!isNaN(sstep) && sstep > 0) scmd += ',' + sstep;
      scmd += ']';
      postInput(scmd, function (ok) { if (ok) resetTool(); });
      return;
    }
    if (activeTool === 'locus') {
      if (toolSel.length === 0) {
        var lq = hitAnyPoint(sx, sy);
        if (!lq) { setMsg(lang === 'en' ? 'Click driven point' : '请点击被驱动点（轨迹点）', true); return; }
        toolSel.push(lq); setToolStatus(); return;
      }
      var lp = hitAnyPoint(sx, sy);
      if (!lp) { setMsg(lang === 'en' ? 'Click driver point' : '请点击驱动点（圆上点）', true); return; }
      postInput('Locus[' + toolSel[0] + ',' + lp + ']', function (ok) { if (ok) resetTool(); });
      return;
    }
    if (CHART_TOOL_CMD[activeTool] || activeTool === 'histogram' || activeTool === 'scatterplot' ||
        activeTool === 'scatterplot3d' || activeTool === 'surfacechart3d') {
      chartToolPrompt(activeTool);
      return;
    }
    if (activeTool === 'ineq') {
      var iTxt = prompt(lang === 'en' ? 'Inequality (e.g. y<x^2, x^2+y^2<4):' : '不等式（如 y<x^2、x^2+y^2<4）：');
      if (iTxt === null || !iTxt.trim()) { resetTool(); return; }
      postInput(iTxt.trim(), function (ok) { if (ok) resetTool(); });
      return;
    }
    if (activeTool === 'compass') {
      toolPointAt(sx, sy, function (c) {
        var rTxt = prompt(lang === 'en' ? 'Radius length:' : '半径长度：', '3');
        if (rTxt === null || rTxt.trim() === '') { resetTool(); return; }
        var rv = parseFloat(rTxt);
        if (isNaN(rv) || rv <= 0) { setMsg(lang === 'en' ? 'Enter a positive radius' : '请输入正数半径', true); resetTool(); return; }
        postInput('Circle[' + c + ',' + rv + ']', function (ok) { if (ok) resetTool(); });
      });
      return;
    }
    if (activeTool === 'pointonpath') {
      var popObj = hitObject(sx, sy, ['line', 'segment', 'ray', 'circle', 'polygon', 'arc']);
      if (!popObj) { setMsg(lang === 'en' ? 'Click a line/segment/ray/circle/polygon/arc' : '请点击线/线段/射线/圆/多边形/圆弧', true); return; }
      postInput('PointOnPath[' + popObj + ']', function (ok) { if (ok) resetTool(); });
      return;
    }
    if (activeTool === 'polyline') {
      var plFirst = toolSel.length ? toolSel[0] : null;
      // 宽容差命中起点 → 完成折线（18px；与预览一致：吸附开启时按吸附后落点判定）
      if (plFirst && toolSel.length >= 2) {
        var plwx = wxp(sx), plwy = wyp(sy);
        if (snapOn || shiftKeyPressed) {
          var plsp = snapPoint(plwx, plwy, niceStep(), sx, sy);
          plwx = plsp[0]; plwy = plsp[1];
        }
        for (var pli2 = 0; pli2 < elements.length; pli2++) {
          var pfel = elements[pli2];
          if (pfel.label !== plFirst || pfel.kind !== 'point') continue;
          var pdx = (pfel.x - plwx) * scale, pdy = (pfel.y - plwy) * scale;
          if (pdx * pdx + pdy * pdy <= 18 * 18) { finishPolyline(); return; }
          break;
        }
      }
      var plHit = hitAnyPoint(sx, sy);
      // 点击已选中的其他顶点 → 提示回起点
      if (plHit && toolSel.indexOf(plHit) !== -1) {
        setMsg(lang === 'en' ? 'Click the first point to finish' : '点击第一个点完成折线', true);
        return;
      }
      // 点击已选中的其他顶点 → 提示回起点
      if (plHit && toolSel.indexOf(plHit) !== -1) {
        setMsg(lang === 'en' ? 'Click the first point to finish' : '点击第一个点完成折线', true);
        return;
      }
      toolPointAt(sx, sy, function (l) {
        if (toolSel.indexOf(l) !== -1) {
          setMsg(lang === 'en' ? 'Click the first point to finish' : '点击第一个点完成折线', true);
          return;
        }
        toolSel.push(l);
        updateToolButtons();
        setToolStatus();
      });
      return;
    }
    if (activeTool === 'circumcircle') {
      // 直接点击三角形（内部/边）→ 一步得到外接圆；否则收集三点
      var ccPoly = hitObject(sx, sy, ['polygon']);
      if (ccPoly) {
        postInput('Circumcircle[' + ccPoly + ']', function (ok) { if (ok) resetTool(); });
        return;
      }
      toolCollectPoints(3, function (s) { return 'Circumcircle[' + s.join(',') + ']'; }, sx, sy);
      return;
    }
    if (activeTool === 'line' || activeTool === 'semicircle') {
      toolCollectPoints(2, function (s) {
        return (activeTool === 'line' ? 'Line[' : 'Semicircle[') + s.join(',') + ']';
      }, sx, sy);
      return;
    }
    if (activeTool === 'arc' || activeTool === 'sector') {
      // 点击顺序：圆心,起点,终点（arc→Arc[起点,终点,圆心]；sector→Sector[起点,终点,圆心]）
      var seCmd = activeTool === 'arc' ? 'Arc' : 'Sector';
      toolCollectPoints(3, function (s) { return seCmd + '[' + s[1] + ',' + s[2] + ',' + s[0] + ']'; }, sx, sy);
      return;
    }
    if (activeTool === 'ellipse' || activeTool === 'hyperbola') {
      toolCollectPoints(3, function (s) {
        return (activeTool === 'ellipse' ? 'Ellipse[' : 'Hyperbola[') + s.join(',') + ']';
      }, sx, sy);
      return;
    }
    if (activeTool === 'parabola') {
      if (toolSel.length === 0) {
        toolPointAt(sx, sy, function (fLbl) {
          toolSel.push(fLbl);
          setToolStatus();
        });
        return;
      }
      var dLbl = hitObject(sx, sy, ['line', 'segment', 'ray']);
      if (!dLbl) { setMsg(lang === 'en' ? 'Click the directrix (line/segment)' : '请点击准线（直线/线段）', true); return; }
      postInput('Parabola[' + toolSel[0] + ',' + dLbl + ']', function (ok) { if (ok) resetTool(); });
      return;
    }
    if (activeTool === 'intersect') {
      var ixKinds = ['line', 'segment', 'ray', 'circle', 'conic', 'function', 'parametric', 'polar', 'implicit'];
      if (toolSel.length === 0) {
        var o1 = hitObject(sx, sy, ixKinds);
        if (!o1) { setMsg(lang === 'en' ? 'Click a line/circle/curve/function' : '请点击线/圆/曲线/函数等对象', true); return; }
        toolSel.push(o1);
        setToolStatus();
        return;
      }
      var o2 = hitObject(sx, sy, ixKinds);
      if (!o2) { setMsg(lang === 'en' ? 'Click the second object' : '请点击第二个对象', true); return; }
      createIntersections(toolSel[0], o2);
      return;
    }
    // 循环创建全部交点（Intersect[o1,o2,1..N]，直到新元素带 error 或无新元素）
    function createIntersections(a, b) {
      var k = 1;
      (function next() {
        var prev = {};
        for (var i = 0; i < elements.length; i++) prev[elements[i].label] = true;
        api('POST', '/api/input', {
          text: 'Intersect[' + a + ',' + b + ',' + k + ']',
          xmin: view.xmin, xmax: view.xmax, ymin: view.ymin, ymax: view.ymax
        }, function (d) {
          if (!d) { resetTool(); return; }
          if (d.elements) { elements = d.elements; render(); }
          var bad = false;
          for (var j = 0; j < elements.length; j++) {
            if (!prev[elements[j].label] && elements[j].error) bad = true;
          }
          if (bad || !d.ok) { resetTool(); return; }
          k++;
          next();
        });
      })();
    }
    if (activeTool === 'text') {
      toolPointAt(sx, sy, function (posLbl) {
        var content = prompt(lang === 'en' ? 'Text content:' : '文本内容：');
        if (content === null || !content.trim()) { resetTool(); return; }
        postInput('Text["' + content.replace(/"/g, "'") + '",' + posLbl + ']', function (ok) { if (ok) resetTool(); });
      });
    }
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
