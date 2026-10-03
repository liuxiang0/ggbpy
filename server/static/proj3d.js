/* ggbpy 三维投影与屏幕空间命中判定（P2 前端拆分：render3d 第一步）（P2 前端拆分：从 app.js 抽出）。
 *
 * 用法（app.js）：
 *   var _proj3d = GGB_P3.create({ get: _stateGet, sxp: sxp, syp: syp });
 *   之后同名函数由 app.js 保留薄包装，调用点无需改动。
 *
 * 状态：cam, cssH, cssW, ctx3, dbgProjCalls, ortho3d, view3dMode
 */
window.GGB_P3 = (function () {
  'use strict';

  function create(env) {
      var sxp = env.sxp;   // 由 app.js 注入（属于其他模块）

      var syp = env.syp;   // 由 app.js 注入（属于其他模块）

      function is3DEl(e) {
        return e.kind === 'geo3d' || (e.kind === 'point' && e.z !== undefined);
      }

      function camBasis3() {
        var cam = env.get('cam'), view3dMode = env.get('view3dMode');
        if (view3dMode === 'oblique') {
          return { right: [1, 0.3536, 0], up: [0, 0.3536, 1], dir: [0, -1, 0] };
        }
        if (view3dMode === 'top') {
          // 俯视：从 +z 向下看 xy 平面；x 右、y 上（屏幕）
          return { right: [1, 0, 0], up: [0, 1, 0], dir: [0, 0, 1] };
        }
        if (view3dMode === 'front') {
          // 前视：从 -y 看 xz 平面；x 右、z 上
          return { right: [1, 0, 0], up: [0, 0, 1], dir: [0, -1, 0] };
        }
        if (view3dMode === 'right') {
          // 右视：从 +x 看 yz 平面；z 上、y 屏幕左（right=right×up'=-dir 右手）
          return { right: [0, -1, 0], up: [0, 0, 1], dir: [1, 0, 0] };
        }
        var dir = [Math.cos(cam.phi) * Math.cos(cam.theta), Math.cos(cam.phi) * Math.sin(cam.theta), Math.sin(cam.phi)];
        var f = [-dir[0], -dir[1], -dir[2]];
        // right = normalize(f × up=(0,0,1)) = (f.y, -f.x, 0)/|..|
        var rx = f[1], ry = -f[0];
        var nr = Math.sqrt(rx * rx + ry * ry) || 1;
        rx /= nr; ry /= nr;
        // up' = right × f
        var ux = ry * f[2], uy = -rx * f[2], uz = rx * f[1] - ry * f[0];
        return { right: [rx, ry, 0], up: [ux, uy, uz], dir: dir };
      }

      function proj3(p) {
        var cam = env.get('cam'), cssH = env.get('cssH'), cssW = env.get('cssW'), ortho3d = env.get('ortho3d'), view3dMode = env.get('view3dMode');
        env.set('dbgProjCalls', env.get('dbgProjCalls') + 1);
        var d = [p[0] - cam.tx, p[1] - cam.ty, p[2] - cam.tz];
        var f = cam.r * 2.2;
        var pxScale = Math.min(cssW, cssH) * 0.42 / cam.r;
        // 斜二测（cabinet 正交）：x 水平全尺寸、y 右上 45° 且减半、z 竖直全尺寸
        if (view3dMode === 'oblique') {
          var K = 0.3536;   // 0.5·cos45° = 0.5·sin45°
          var sx = d[0] + K * d[1];
          var sy = d[2] + K * d[1];
          return { x: cssW / 2 + sx * pxScale, y: cssH / 2 - sy * pxScale, z: d[1], s: 1 };
        }
        var b = camBasis3();
        var xc = d[0] * b.right[0] + d[1] * b.right[1];
        var yc = d[0] * b.up[0] + d[1] * b.up[1] + d[2] * b.up[2];
        var zc = d[0] * b.dir[0] + d[1] * b.dir[1] + d[2] * b.dir[2];
        var s = ortho3d ? 1 : f / (f + cam.r + zc);   // 正交视图：平行投影
        return { x: cssW / 2 + xc * pxScale * s, y: cssH / 2 - yc * pxScale * s, z: zc, s: s };
      }

      function line3(p1, p2, color, lw) {
        var ctx3 = env.get('ctx3');
        var a = proj3(p1), b = proj3(p2);
        ctx3.strokeStyle = color;
        ctx3.lineWidth = lw || 1.6;
        ctx3.beginPath();
        ctx3.moveTo(a.x, a.y);
        ctx3.lineTo(b.x, b.y);
        ctx3.stroke();
      }

      function pointInScreenPoly(px, py, poly) {
        var inside = false;
        for (var i = 0, j = poly.length - 1; i < poly.length; j = i++) {
          var xi = poly[i][0], yi = poly[i][1], xj = poly[j][0], yj = poly[j][1];
          if (((yi > py) !== (yj > py)) && (px < (xj - xi) * (py - yi) / (yj - yi) + xi)) inside = !inside;
        }
        return inside;
      }

      function snapAxis3d(sx, sy) {
        var axes = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
        var best = null, bestD = 12;   // 屏幕像素阈值
        for (var ai = 0; ai < axes.length; ai++) {
          var ax = axes[ai];
          // 沿轴采样 -12..12（世界单位），找屏幕最近点
          for (var t = -12; t <= 12.01; t += 0.5) {
            var p3 = [ax[0] * t, ax[1] * t, ax[2] * t];
            var pr = proj3(p3);
            var dd = Math.hypot(pr.x - sx, pr.y - sy);
            if (dd < bestD) { bestD = dd; best = { ax: ax, t: t }; }
          }
        }
        return best;
      }

      function wptIn(x, y, m) { return x >= m.x0 && x <= m.x1 && y >= m.y0 && y <= m.y1; }

      function wsegHit(x1, y1, x2, y2, m) {
        // Liang-Barsky：线段与世界矩形相交
        if (wptIn(x1, y1, m) || wptIn(x2, y2, m)) return true;
        var dx = x2 - x1, dy = y2 - y1, t0 = 0, t1 = 1;
        var ps = [-dx, dx, -dy, dy], qs = [x1 - m.x0, m.x1 - x1, y1 - m.y0, m.y1 - y1];
        for (var wi = 0; wi < 4; wi++) {
          if (ps[wi] === 0) { if (qs[wi] < 0) return false; }
          else {
            var rr2 = qs[wi] / ps[wi];
            if (ps[wi] < 0) { if (rr2 > t1) return false; if (rr2 > t0) t0 = rr2; }
            else { if (rr2 < t0) return false; if (rr2 < t1) t1 = rr2; }
          }
        }
        return true;
      }

      function pointInPoly(px, py, pts) {
        var inside = false;
        for (var i = 0, j = pts.length - 1; i < pts.length; j = i++) {
          var xi = sxp(pts[i][0]), yi = syp(pts[i][1]);
          var xj = sxp(pts[j][0]), yj = syp(pts[j][1]);
          if (((yi > py) !== (yj > py)) && (px < (xj - xi) * (py - yi) / (yj - yi) + xi)) inside = !inside;
        }
        return inside;
      }

      function distToSeg(px, py, x1, y1, x2, y2) {
        var dx = x2 - x1, dy = y2 - y1;
        var len2 = dx * dx + dy * dy;
        var t = len2 ? ((px - x1) * dx + (py - y1) * dy) / len2 : 0;
        t = Math.max(0, Math.min(1, t));
        return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
      }

    return {
      sxp: sxp,
      syp: syp,
      is3DEl: is3DEl,
      camBasis3: camBasis3,
      proj3: proj3,
      line3: line3,
      pointInScreenPoly: pointInScreenPoly,
      snapAxis3d: snapAxis3d,
      wptIn: wptIn,
      wsegHit: wsegHit,
      pointInPoly: pointInPoly,
      distToSeg: distToSeg,
    };
  }

  return { create: create };
})();
