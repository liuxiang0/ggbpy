/* ggbpy 工具预览计算（2D 工具预览几何，P2 前端拆分）（P2 前端拆分：从 app.js 抽出）。
 *
 * 用法（app.js）：
 *   var _preview = GGB_PREV.create({ get: _stateGet, findEl: findEl, niceStep: niceStep, hitObject: hitObject });
 *   之后同名函数由 app.js 保留薄包装，调用点无需改动。
 *
 * 状态：COORD, EPSILON, activeTool, pendingImage, shiftKeyPressed, snapOn, view
 */
window.GGB_PREV = (function () {
  'use strict';

  function create(env) {
      var wxp = env.wxp;   // 由 app.js 注入（属于其他模块）

      var wyp = env.wyp;   // 由 app.js 注入（属于其他模块）

      var findEl = env.findEl;   // 由 app.js 注入（属于其他模块）

      var niceStep = env.niceStep;   // 由 app.js 注入（属于其他模块）

      var hitObject = env.hitObject;   // 由 app.js 注入（属于其他模块）

      var snapPoint = env.snapPoint;   // 由 app.js 注入（属于其他模块）

      function conicCoeffs(pts) {
        var COORD = env.get('COORD'), EPSILON = env.get('EPSILON');
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
        var view = env.get('view');
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

      function computeToolPreview(sel, mx, my) {
        var COORD = env.get('COORD'), EPSILON = env.get('EPSILON'), activeTool = env.get('activeTool'), pendingImage = env.get('pendingImage'), shiftKeyPressed = env.get('shiftKeyPressed'), snapOn = env.get('snapOn');
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

    return {
      conicCoeffs: conicCoeffs,
      conicPreviewSegs: conicPreviewSegs,
      computeToolPreview: computeToolPreview,
    };
  }

  return { create: create };
})();
