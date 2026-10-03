/* ggbpy 二维画布绘制基元（网格/坐标轴/线段/多边形/箭头）（P2 前端拆分：从 app.js 抽出）。
 *
 * 用法（app.js）：
 *   var _draw2d = GGB_D2.create({ get: _stateGet, fmtNum: fmtNum });
 *   之后同名函数由 app.js 保留薄包装，调用点无需改动。
 *
 * 状态：C, cssH, cssW, ctx, elements, scale, showAxes, showGrid, view
 */
window.GGB_D2 = (function () {
  'use strict';

  function create(env) {
      function sxp(x) { var scale = env.get('scale'), view = env.get('view'); return (x - view.xmin) * scale; }

      function syp(y) { var cssH = env.get('cssH'), scale = env.get('scale'), view = env.get('view'); return cssH - (y - view.ymin) * scale; }

      var fmtNum = env.fmtNum;   // 由 app.js 注入（属于其他模块）

      function niceStep() {
        var scale = env.get('scale');
        var target = 70 / scale;
        var pow = Math.pow(10, Math.floor(Math.log(target) / Math.LN10));
        var m = target / pow;
        var step = (m < 1.5) ? 1 : (m < 3.5) ? 2 : (m < 7.5) ? 5 : 10;
        return step * pow;
      }

      function drawGrid() {
        var C = env.get('C'), cssH = env.get('cssH'), cssW = env.get('cssW'), ctx = env.get('ctx'), elements = env.get('elements'), scale = env.get('scale'), showAxes = env.get('showAxes'), showGrid = env.get('showGrid'), view = env.get('view');
        var step = niceStep();
        var w = cssW, h = cssH;
        ctx.lineWidth = 1;
        ctx.strokeStyle = C.grid;
        ctx.beginPath();
        if (showGrid) {
          for (var x = Math.ceil(view.xmin / step) * step; x <= view.xmax; x += step) {
            var sx = Math.round(sxp(x)) + 0.5;
            ctx.moveTo(sx, 0); ctx.lineTo(sx, h);
          }
          for (var y = Math.ceil(view.ymin / step) * step; y <= view.ymax; y += step) {
            var sy = Math.round(syp(y)) + 0.5;
            ctx.moveTo(0, sy); ctx.lineTo(w, sy);
          }
        }
        ctx.stroke();
        // 极坐标网格：存在极坐标曲线时自动叠加（同心圆 + 每 30° 射线）
        var hasPolar = false;
        for (var pi2 = 0; pi2 < elements.length; pi2++) if (elements[pi2].kind === 'polar') { hasPolar = true; break; }
        if (showGrid && hasPolar) {
          ctx.strokeStyle = C.grid;
          ctx.lineWidth = 1;
          ctx.beginPath();
          var orx = Math.round(sxp(0)) + 0.5, ory = Math.round(syp(0)) + 0.5;
          var rmax = Math.max(Math.abs(view.xmin), Math.abs(view.xmax), Math.abs(view.ymin), Math.abs(view.ymax));
          for (var pr = step; pr <= rmax; pr += step) {
            ctx.arc(orx, ory, Math.max(1, pr * scale), 0, Math.PI * 2);
          }
          for (var ang = 0; ang < 360; ang += 30) {
            var rad2 = ang * Math.PI / 180;
            ctx.moveTo(orx, ory);
            ctx.lineTo(orx + Math.cos(rad2) * (w + h), ory - Math.sin(rad2) * (w + h));
          }
          ctx.stroke();
        }
        ctx.strokeStyle = C.major;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        if (showAxes) {
          var ox = Math.round(sxp(0)) + 0.5;
          var oy = Math.round(syp(0)) + 0.5;
          ctx.moveTo(0, oy); ctx.lineTo(w, oy);
          ctx.moveTo(ox, 0); ctx.lineTo(ox, h);
          ctx.stroke();
        }
        ctx.fillStyle = C.tick;
        ctx.font = '11px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        for (var x2 = Math.ceil(view.xmin / step) * step; x2 <= view.xmax; x2 += step) {
          if (Math.abs(x2) < step / 2) continue;
          ctx.fillText(fmtNum(x2), sxp(x2), oy + 4);
        }
        ctx.textBaseline = 'middle';
        ctx.textAlign = 'right';
        for (var y2 = Math.ceil(view.ymin / step) * step; y2 <= view.ymax; y2 += step) {
          if (Math.abs(y2) < step / 2) continue;
          ctx.fillText(fmtNum(y2), ox - 4, syp(y2));
        }
      }

      function strokeSeg(x1, y1, x2, y2, color, lw) {
        var ctx = env.get('ctx');
        ctx.strokeStyle = color;
        ctx.lineWidth = lw || 2;
        ctx.beginPath();
        ctx.moveTo(sxp(x1), syp(y1));
        ctx.lineTo(sxp(x2), syp(y2));
        ctx.stroke();
      }

      function strokePoly(pts, color, lw) {
        var ctx = env.get('ctx');
        if (!pts || pts.length < 2) return;
        ctx.strokeStyle = color;
        ctx.lineWidth = lw || 2;
        ctx.beginPath();
        ctx.moveTo(sxp(pts[0][0]), syp(pts[0][1]));
        for (var k = 1; k < pts.length; k++) ctx.lineTo(sxp(pts[k][0]), syp(pts[k][1]));
        ctx.stroke();
      }

      function drawArrow(x1, y1, x2, y2, color) {
        var ctx = env.get('ctx');
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
        // 箭头（仅当长度足够）
        var dx = x2 - x1, dy = y2 - y1;
        var len = Math.sqrt(dx * dx + dy * dy);
        if (len < 14) return;
        var ux = dx / len, uy = dy / len;
        var hs = 10;
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.moveTo(x2 + ux * 3, y2 + uy * 3);
        ctx.lineTo(x2 - ux * hs + uy * hs * 0.5, y2 - uy * hs - ux * hs * 0.5);
        ctx.lineTo(x2 - ux * hs - uy * hs * 0.5, y2 - uy * hs + ux * hs * 0.5);
        ctx.closePath();
        ctx.fill();
      }

    return {
      sxp: sxp,
      syp: syp,
      fmtNum: fmtNum,
      niceStep: niceStep,
      drawGrid: drawGrid,
      strokeSeg: strokeSeg,
      strokePoly: strokePoly,
      drawArrow: drawArrow,
    };
  }

  return { create: create };
})();
