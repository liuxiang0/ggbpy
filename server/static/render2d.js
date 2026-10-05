/* ggbpy 二维元素绘制层（元素/圆锥曲线/不等式/叠加层/图片，P2 前端拆分）（P2 前端拆分：从 app.js 抽出）。
 *
 * 用法（app.js）：
 *   var _render2d = GGB_R2D.create({ get: _stateGet, fmtNum: fmtNum, renderList: renderList, populateEditBar: populateEditBar, sxp: sxp, syp: syp, drawGrid: drawGrid, strokeSeg: strokeSeg, drawArrow: drawArrow, usableCanvasRect: usableCanvasRect, drawBarChart: drawBarChart, drawBoxPlot: drawBoxPlot, drawPieChart: drawPieChart, drawLineChart: drawLineChart, drawScatterPlot: drawScatterPlot, drawDotPlot: drawDotPlot, is3DEl: is3DEl });
 *   之后同名函数由 app.js 保留薄包装，调用点无需改动。
 *
 * 状态：C, COARSE, activeTool, cssH, cssW, ctx, imgCache, scale, selected, showAxes, toolSel, view
 */
window.GGB_R2D = (function () {
  'use strict';

  function create(env) {
      function gcdInt(a, b) { a = Math.abs(a); b = Math.abs(b); while (b) { var t = a % b; a = b; b = t; } return a || 1; }

      var angleUnit = env.angleUnit;   // 由 app.js 注入（属于其他模块）
      var findEl = env.findEl;   // 由 app.js 注入（属于其他模块）

      function fmtAngleDeg(deg) {
        var COARSE = env.get('COARSE');
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

      var fmtNum = env.fmtNum;   // 由 app.js 注入（属于其他模块）

      var renderList = env.renderList;   // 由 app.js 注入（属于其他模块）

      var populateEditBar = env.populateEditBar;   // 由 app.js 注入（属于其他模块）

      var sxp = env.sxp;   // 由 app.js 注入（属于其他模块）

      var syp = env.syp;   // 由 app.js 注入（属于其他模块）

      var drawGrid = env.drawGrid;   // 由 app.js 注入（属于其他模块）

      var strokeSeg = env.strokeSeg;   // 由 app.js 注入（属于其他模块）

      var drawArrow = env.drawArrow;   // 由 app.js 注入（属于其他模块）

      var usableCanvasRect = env.usableCanvasRect;   // 由 app.js 注入（属于其他模块）

      var drawBarChart = env.drawBarChart;   // 由 app.js 注入（属于其他模块）

      var drawBoxPlot = env.drawBoxPlot;   // 由 app.js 注入（属于其他模块）

      var drawPieChart = env.drawPieChart;   // 由 app.js 注入（属于其他模块）

      var drawLineChart = env.drawLineChart;   // 由 app.js 注入（属于其他模块）

      var drawScatterPlot = env.drawScatterPlot;   // 由 app.js 注入（属于其他模块）

      var drawDotPlot = env.drawDotPlot;   // 由 app.js 注入（属于其他模块）
      var drawStemPlot = env.drawStemPlot;   // 由 app.js 注入（属于其他模块）

      var is3DEl = env.is3DEl;   // 由 app.js 注入（属于其他模块）

      function drawSelectionOverlay(e) {
        var ctx = env.get('ctx'), scale = env.get('scale');
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

      function drawOverlay() {
        var C = env.get('C'), cssH = env.get('cssH'), cssW = env.get('cssW'), ctx = env.get('ctx'), showAxes = env.get('showAxes'), view = env.get('view');
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
        var C = env.get('C');
        // 锁定对象：统一灰色，表示不可移动/编辑
        if (e.locked) return '#9ca3af';
        var m = { line: '#2563eb', segment: '#059669', ray: '#0d9488', circle: '#7c3aed',
                  polygon: '#3b82f6', polyline: '#0d9488', function: '#0f766e', point: '#dc2626', vector: '#b45309',
                  conic: '#7c3aed', inequality: '#3b82f6', arc: '#7c3aed' };
        return m[e.kind] || C.text;
      }

      function getImage(iid) {
        var imgCache = env.get('imgCache');
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
        var ctx = env.get('ctx');
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
        var C = env.get('C'), activeTool = env.get('activeTool'), ctx = env.get('ctx'), scale = env.get('scale'), selected = env.get('selected'), toolSel = env.get('toolSel');
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
          // 有向角约定：rad ∈ [0, 2π) = 从 BA 逆时针到 BC 的圆心角（可为优角），
          // 因此弧恒为逆时针扫 rad（y-down 画布 → 负角映射 + anticlockwise=true）。
          var sweepA = e.rad > 0 ? e.rad : 0;
          ctx.beginPath();
          ctx.arc(cx2, cy2, r2, -e.ang1, -e.ang1 - sweepA, true);   // y-down 映射
          ctx.stroke();
          var mid = e.ang1 + sweepA / 2;
          var lx = cx2 + r2 * 1.45 * Math.cos(mid);
          var ly = cy2 - r2 * 1.45 * Math.sin(mid);
          ctx.fillStyle = '#7c3aed';
          ctx.font = '12px sans-serif';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(fmtAngleDeg(e.deg), lx, ly);
        }
        if (e.kind === 'number' && e.min !== null && e.min !== undefined
            && e.slider_x !== null && e.slider_x !== undefined) {
          // 滑动条：按 GeoGebra 样式画成线段 + 可拖动滑钮（min / 当前值 / max 标注）
          var tk0 = sxp(e.slider_x), tk1 = sxp(e.slider_x + (e.slider_len || 3)), tky = syp(e.slider_y);
          var span = (e.max - e.min) || 1;
          var frac = Math.max(0, Math.min(1, (e.val - e.min) / span));
          var kx = tk0 + (tk1 - tk0) * frac;
          ctx.save();
          ctx.strokeStyle = '#94a3b8';
          ctx.lineWidth = 4;
          ctx.beginPath();
          ctx.moveTo(tk0, tky);
          ctx.lineTo(tk1, tky);
          ctx.stroke();
          ctx.fillStyle = '#2563eb';
          ctx.beginPath();
          ctx.arc(kx, tky, 7, 0, Math.PI * 2);
          ctx.fill();
          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = 2;
          ctx.stroke();
          ctx.fillStyle = '#334155';
          ctx.font = '12px sans-serif';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'top';
          ctx.fillText(fmtNum(e.min), tk0, tky + 9);
          ctx.fillText(fmtNum(e.max), tk1, tky + 9);
          ctx.textBaseline = 'bottom';
          ctx.fillStyle = '#1d4ed8';
          ctx.fillText(e.label + ' = ' + fmtNum(e.val), (tk0 + tk1) / 2, tky - 9);
          ctx.restore();
          var wsmap = env.get('widgetBoxes');
          if (wsmap) {
            wsmap[e.label] = { kind: 'slider', label: e.label,
                               x0: Math.min(tk0, tk1) - 10, x1: Math.max(tk0, tk1) + 10,
                               y0: tky - 14, y1: tky + 16,
                               wx0: e.slider_x, wx1: e.slider_x + (e.slider_len || 3) };
          }
        }
        if (e.kind === 'button' || e.kind === 'checkbox' || e.kind === 'inputbox') {
          // 交互控件（Button / CheckBox / InputBox）：锚点在左下角；实时态从绑定对象派生
          var wbx = sxp(e.x), wby = syp(e.y);
          var wcap = e.caption || '';
          var tgt = findEl ? findEl(e.target) : null;
          var wlab = wcap, ww = 0, wh = 0;
          if (e.kind === 'button') {
            ww = Math.max(64, ctx.measureText ? 0 : 0);
            ctx.font = '13px sans-serif';
            ww = Math.max(64, ctx.measureText(wcap).width + 26);
            wh = 28; wlab = wcap;
          } else if (e.kind === 'checkbox') {
            ctx.font = '13px sans-serif';
            // visible 为 null/undefined 表示默认可见（只有显式 false 才是隐藏）
            var won = !tgt || tgt.visible === undefined || tgt.visible === null ? true : !!tgt.visible;
            wlab = (won ? '☑ ' : '☐ ') + wcap;
            ww = Math.max(34, ctx.measureText(wlab).width + 16);
            wh = 24;
          } else {
            ctx.font = '13px sans-serif';
            var wv = tgt && tgt.value != null ? tgt.value : '';
            wlab = wcap + ' = ' + wv;
            ww = Math.max(96, ctx.measureText(wlab).width + 18);
            wh = 26;
          }
          var wx0 = wbx, wy0 = wby - wh;
          ctx.save();
          ctx.fillStyle = e.kind === 'button' ? '#2563eb' : 'rgba(255,255,255,.95)';
          ctx.strokeStyle = e.kind === 'button' ? '#1d4ed8' : '#94a3b8';
          ctx.lineWidth = 1;
          var wr = 5;
          ctx.beginPath();
          ctx.moveTo(wx0 + wr, wy0);
          ctx.lineTo(wx0 + ww - wr, wy0);
          ctx.quadraticCurveTo(wx0 + ww, wy0, wx0 + ww, wy0 + wr);
          ctx.lineTo(wx0 + ww, wy0 + wh - wr);
          ctx.quadraticCurveTo(wx0 + ww, wy0 + wh, wx0 + ww - wr, wy0 + wh);
          ctx.lineTo(wx0 + wr, wy0 + wh);
          ctx.quadraticCurveTo(wx0, wy0 + wh, wx0, wy0 + wh - wr);
          ctx.lineTo(wx0, wy0 + wr);
          ctx.quadraticCurveTo(wx0, wy0, wx0 + wr, wy0);
          ctx.closePath();
          ctx.fill();
          ctx.stroke();
          ctx.fillStyle = e.kind === 'button' ? '#ffffff' : '#0f172a';
          ctx.textAlign = 'left';
          ctx.textBaseline = 'middle';
          ctx.fillText(wlab, wx0 + (e.kind === 'checkbox' ? 8 : 12), wy0 + wh / 2);
          ctx.restore();
          var wmap = env.get('widgetBoxes');
          if (wmap) wmap[e.label] = { x0: wx0, y0: wy0, x1: wx0 + ww, y1: wy0 + wh };
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
        if (e.kind === 'stemplot' && e.stems && e.stems.length) drawStemPlot(e);
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
        if (e.kind === 'list' && e.itemkind === 'polygon' && e.items && e.items.length) {
          // 多边形列表（Delaunay 三角剖分 / Voronoi 元胞）：半透明填充 + 描边
          ctx.save();
          ctx.strokeStyle = colorOf(e);
          ctx.lineWidth = 1.4;
          ctx.fillStyle = 'rgba(37,99,235,0.10)';
          for (var pi = 0; pi < e.items.length; pi++) {
            var poly = e.items[pi];
            if (!poly || poly.length < 3) continue;
            ctx.beginPath();
            ctx.moveTo(sxp(poly[0][0]), syp(poly[0][1]));
            for (var pj = 1; pj < poly.length; pj++) ctx.lineTo(sxp(poly[pj][0]), syp(poly[pj][1]));
            ctx.closePath();
            ctx.fill();
            ctx.stroke();
          }
          // 面积标注（每个多边形的质心；数量多时不标注，避免糊成一片）
          if (e.areas && e.areas.length === e.items.length && e.items.length <= 30) {
            ctx.fillStyle = 'rgba(30,58,138,0.85)';
            ctx.font = '11px ui-monospace, Menlo, Consolas, monospace';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            for (var ai = 0; ai < e.items.length; ai++) {
              var ct = (e.centroids && e.centroids[ai]) || null;
              if (!ct) continue;
              ctx.fillText(Number(e.areas[ai]).toFixed(2), sxp(ct[0]), syp(ct[1]));
            }
          }
          ctx.restore();
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

      var render = env.render;   // 由 app.js 注入（属于其他模块）

      function conicPathPts(e) {
        var view = env.get('view');
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
        var ctx = env.get('ctx'), view = env.get('view');
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
        var cssH = env.get('cssH'), ctx = env.get('ctx');
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

      var tipText = env.tipText;   // 由 app.js 注入（属于其他模块）

    return {
      gcdInt: gcdInt,
      fmtAngleDeg: fmtAngleDeg,
      drawSelectionOverlay: drawSelectionOverlay,
      drawOverlay: drawOverlay,
      colorOf: colorOf,
      getImage: getImage,
      drawImageEl: drawImageEl,
      drawElement: drawElement,
      conicPathPts: conicPathPts,
      drawConic: drawConic,
      drawInequality: drawInequality,
    };
  }

  return { create: create };
})();
