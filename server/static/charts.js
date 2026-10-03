/* ggbpy 统计图渲染（六类二维统计图的画布绘制与命中框，P2 前端拆分）（P2 前端拆分：从 app.js 抽出）。
 *
 * 用法（app.js）：
 *   var _charts = GGB_CHARTS.create({ get: _stateGet, sxp: sxp, syp: syp });
 *   之后同名函数由 app.js 保留薄包装，调用点无需改动。
 *
 * 状态：PIE_PAL, canvas, chartBoxes, cssH, cssW, ctx, scale
 */
window.GGB_CHARTS = (function () {
  'use strict';

  function create(env) {
      function usableCanvasRect() {
        var canvas = env.get('canvas'), cssH = env.get('cssH'), cssW = env.get('cssW');
        var cr = canvas.getBoundingClientRect();
        var rect = { left: 4, top: 4, right: cssW - 4, bottom: cssH - 4 };
        var panel = document.getElementById('panel');
        if (!panel) return rect;
        var st = window.getComputedStyle(panel);
        if (st.display === 'none' || st.visibility === 'hidden') return rect;   // fixed 定位元素 offsetParent 为 null，不能用它判断
        var pr = panel.getBoundingClientRect();
        if (pr.width <= 0 || pr.height <= 0) return rect;
        var overlapsX = Math.min(pr.right, cr.right) - Math.max(pr.left, cr.left);
        var overlapsY = Math.min(pr.bottom, cr.bottom) - Math.max(pr.top, cr.top);
        if (overlapsX <= 0 || overlapsY <= 0) return rect;
        // 按"面板贴住画布的哪条边"收缩可用区（面板可停靠上/下/左/右，也可能是浮动框）
        var touchesBottom = pr.bottom >= cr.bottom - 1 && pr.top > cr.top + 1;
        var touchesTop = pr.top <= cr.top + 1 && pr.bottom < cr.bottom - 1;
        var touchesLeft = pr.left <= cr.left + 1 && pr.right < cr.right - 1;
        var touchesRight = pr.right >= cr.right - 1 && pr.left > cr.left + 1;
        if (touchesBottom) rect.bottom = Math.min(rect.bottom, pr.top - cr.top - 4);
        if (touchesTop) rect.top = Math.max(rect.top, pr.bottom - cr.top + 4);
        if (touchesLeft) rect.left = Math.max(rect.left, pr.right - cr.left + 4);
        if (touchesRight) rect.right = Math.min(rect.right, pr.left - cr.left - 4);
        if (!touchesBottom && !touchesTop && !touchesLeft && !touchesRight) {
          // 浮动面板：按中心偏向收缩对应一侧
          if ((pr.left + pr.right) / 2 < (cr.left + cr.right) / 2) {
            rect.left = Math.max(rect.left, pr.right - cr.left + 4);
          } else {
            rect.right = Math.min(rect.right, pr.left - cr.left - 4);
          }
        }
        // 兜底：异常布局下至少保留画布主体，避免可用区变成负宽高
        if (rect.right - rect.left < cssW * 0.5) { rect.left = 4; rect.right = cssW - 4; }
        if (rect.bottom - rect.top < cssH * 0.4) { rect.top = 4; rect.bottom = cssH - 4; }
        return rect;
      }

      var sxp = env.sxp;   // 由 app.js 注入（属于其他模块）

      var syp = env.syp;   // 由 app.js 注入（属于其他模块）

      function chartOff(e) {
        var scale = env.get('scale');
        var o = e.offset || [0, 0];
        return { x: (o[0] || 0) * scale, y: -(o[1] || 0) * scale };
      }

      function chartBoxPut(e, co, x0, y0, x1, y1) {
        var chartBoxes = env.get('chartBoxes');
        chartBoxes[e.label] = {
          x0: Math.min(x0, x1) + co.x, y0: Math.min(y0, y1) + co.y,
          x1: Math.max(x0, x1) + co.x, y1: Math.max(y0, y1) + co.y
        };
      }

      function chartAt(sx, sy) {
        var chartBoxes = env.get('chartBoxes');
        for (var k in chartBoxes) {
          if (!Object.prototype.hasOwnProperty.call(chartBoxes, k)) continue;
          var b = chartBoxes[k];
          if (sx >= b.x0 - 2 && sx <= b.x1 + 2 && sy >= b.y0 - 2 && sy <= b.y1 + 2) return k;
        }
        return null;
      }

      function drawBarChart(e) {
        var ctx = env.get('ctx'), scale = env.get('scale');
        var co = chartOff(e);
        var maxC = 1;
        for (var bi = 0; bi < e.counts.length; bi++) if (e.counts[bi] > maxC) maxC = e.counts[bi];
        var barW = Math.max(8, e.width * scale * 0.6);
        var bx0s = 1e9, bx1s = -1e9, maxH = 0;
        // 基线取"可用区底边"（扣除停靠面板遮挡），否则默认贴画布最底会被面板盖住
        var barBase = usableCanvasRect().bottom - 4;
        ctx.save();
        ctx.translate(co.x, co.y);
        ctx.fillStyle = 'rgba(59,130,246,.75)';
        ctx.strokeStyle = '#2563eb';
        ctx.lineWidth = 1;
        for (var bj = 0; bj < e.bins.length; bj++) {
          var x0, w;
          if (e.hist && e.edges && e.edges[bj + 1] !== undefined) {
            x0 = sxp(e.edges[bj]);
            w = Math.max(2, (e.edges[bj + 1] - e.edges[bj]) * scale * 0.96);
          } else {
            x0 = sxp(e.bins[bj]) - barW / 2;
            w = barW;
          }
          var h = (e.counts[bj] / maxC) * (barBase * 0.45);
          ctx.fillRect(x0, barBase - h, w, h);
          ctx.strokeRect(x0 + 0.5, barBase - h + 0.5, w - 1, h - 1);
          bx0s = Math.min(bx0s, x0); bx1s = Math.max(bx1s, x0 + w); maxH = Math.max(maxH, h);
        }
        ctx.restore();
        if (bx1s > bx0s) chartBoxPut(e, co, bx0s, barBase - maxH, bx1s, barBase);
      }

      function drawBoxPlot(e) {
        var ctx = env.get('ctx'), scale = env.get('scale');
        var co = chartOff(e);
        var fv = e.five, bpy = syp(e.base_y), bph = Math.max(6, e.box_h * scale);
        var xMn = sxp(fv[0]), xQ1 = sxp(fv[1]), xMd = sxp(fv[2]), xQ3 = sxp(fv[3]), xMx = sxp(fv[4]);
        ctx.save();
        ctx.translate(co.x, co.y);
        ctx.strokeStyle = '#0f766e';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(xMn, bpy); ctx.lineTo(xMx, bpy);
        ctx.moveTo(xMn, bpy - bph / 2); ctx.lineTo(xMn, bpy + bph / 2);
        ctx.moveTo(xMx, bpy - bph / 2); ctx.lineTo(xMx, bpy + bph / 2);
        ctx.stroke();
        ctx.fillStyle = 'rgba(15,118,110,.18)';
        ctx.fillRect(xQ1, bpy - bph / 2, Math.max(1, xQ3 - xQ1), bph);
        ctx.strokeRect(xQ1, bpy - bph / 2, Math.max(1, xQ3 - xQ1), bph);
        ctx.beginPath();
        ctx.moveTo(xMd, bpy - bph / 2); ctx.lineTo(xMd, bpy + bph / 2);
        ctx.stroke();
        ctx.restore();
        chartBoxPut(e, co, Math.min(xMn, xQ1, xMd, xQ3, xMx), bpy - bph, Math.max(xMn, xQ1, xMd, xQ3, xMx), bpy + bph);
      }

      function drawPieChart(e) {
        var PIE_PAL = env.get('PIE_PAL'), cssH = env.get('cssH'), cssW = env.get('cssW'), ctx = env.get('ctx');
        var co = chartOff(e);
        var pCx = cssW * 0.5, pCy = cssH * 0.48, pR = Math.min(cssW, cssH) * 0.3;
        var a0 = -Math.PI / 2, pieTot = e.total > 0 ? e.total : 1;
        ctx.save();
        ctx.translate(co.x, co.y);
        for (var pj = 0; pj < e.items.length; pj++) {
          var a1 = a0 + (e.items[pj] / pieTot) * Math.PI * 2;
          ctx.beginPath();
          ctx.moveTo(pCx, pCy);
          ctx.arc(pCx, pCy, pR, a0, a1);
          ctx.closePath();
          ctx.fillStyle = PIE_PAL[pj % PIE_PAL.length];
          ctx.fill();
          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = 1.5;
          ctx.stroke();
          a0 = a1;
        }
        ctx.fillStyle = '#ffffff';
        ctx.beginPath();
        ctx.arc(pCx, pCy, pR * 0.35, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
        chartBoxPut(e, co, pCx - pR, pCy - pR, pCx + pR, pCy + pR);
      }

      function drawLineChart(e) {
        var ctx = env.get('ctx');
        var co = chartOff(e), i, x, y;
        var x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
        ctx.save();
        ctx.translate(co.x, co.y);
        ctx.strokeStyle = '#2563eb';
        ctx.lineWidth = 2;
        ctx.beginPath();
        for (i = 0; i < e.xs.length; i++) {
          if (e.ys[i] === null || !isFinite(e.ys[i])) continue;
          x = sxp(e.xs[i]); y = syp(e.ys[i]);
          if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
          x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
        }
        ctx.stroke();
        ctx.fillStyle = '#1d4ed8';
        for (i = 0; i < e.xs.length; i++) {
          if (e.ys[i] === null || !isFinite(e.ys[i])) continue;
          ctx.beginPath();
          ctx.arc(sxp(e.xs[i]), syp(e.ys[i]), 3.2, 0, Math.PI * 2);
          ctx.fill();
        }
        ctx.restore();
        if (x1 > x0) chartBoxPut(e, co, x0 - 4, y0 - 4, x1 + 4, y1 + 4);
      }

      function drawScatterPlot(e) {
        var ctx = env.get('ctx');
        var co = chartOff(e), i;
        var x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
        ctx.save();
        ctx.translate(co.x, co.y);
        ctx.fillStyle = '#dc2626';
        for (i = 0; i < e.pts.length; i++) {
          var sx2 = sxp(e.pts[i][0]), sy2 = syp(e.pts[i][1]);
          ctx.beginPath();
          ctx.arc(sx2, sy2, 3.4, 0, Math.PI * 2);
          ctx.fill();
          x0 = Math.min(x0, sx2); x1 = Math.max(x1, sx2); y0 = Math.min(y0, sy2); y1 = Math.max(y1, sy2);
        }
        ctx.restore();
        if (x1 > x0) chartBoxPut(e, co, x0 - 4, y0 - 4, x1 + 4, y1 + 4);
      }

      function drawDotPlot(e) {
        var ctx = env.get('ctx');
        var co = chartOff(e), i;
        var step = e.step || 1.0;
        var x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
        ctx.save();
        ctx.translate(co.x, co.y);
        ctx.fillStyle = '#7c3aed';
        for (i = 0; i < e.stacks.length; i++) {
          var sx3 = sxp(e.stacks[i][0]), sy3 = syp(e.stacks[i][1] * step);
          ctx.beginPath();
          ctx.arc(sx3, sy3, 3.2, 0, Math.PI * 2);
          ctx.fill();
          x0 = Math.min(x0, sx3); x1 = Math.max(x1, sx3); y0 = Math.min(y0, sy3); y1 = Math.max(y1, sy3);
        }
        ctx.restore();
        if (x1 > x0) chartBoxPut(e, co, x0 - 4, y0 - 4, x1 + 4, y1 + 4);
      }

    return {
      usableCanvasRect: usableCanvasRect,
      sxp: sxp,
      syp: syp,
      chartOff: chartOff,
      chartBoxPut: chartBoxPut,
      chartAt: chartAt,
      drawBarChart: drawBarChart,
      drawBoxPlot: drawBoxPlot,
      drawPieChart: drawPieChart,
      drawLineChart: drawLineChart,
      drawScatterPlot: drawScatterPlot,
      drawDotPlot: drawDotPlot,
    };
  }

  return { create: create };
})();
