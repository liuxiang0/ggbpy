/* ggbpy 命中测试与逆投影（2D/3D 命中、屏幕→世界逆投影、路径参数）（P2 前端拆分：从 app.js 抽出）。
 *
 * 用法（app.js）：
 *   var _hit = GGB_HIT.create({ get: _stateGet, sxp: sxp, syp: syp, camBasis3: camBasis3, proj3: proj3, pointInPoly: pointInPoly, distToSeg: distToSeg, conicPathPts: conicPathPts });
 *   之后同名函数由 app.js 保留薄包装，调用点无需改动。
 *
 * 状态：CHART_KINDS, COORD, EPSILON, cam, chartBoxes, cssH, cssW, elements, els3d, ortho3d, scale, view3dMode
 */
window.GGB_HIT = (function () {
  'use strict';

  function create(env) {
      var sxp = env.sxp;   // 由 app.js 注入（属于其他模块）

      var syp = env.syp;   // 由 app.js 注入（属于其他模块）

      var camBasis3 = env.camBasis3;   // 由 app.js 注入（属于其他模块）

      var proj3 = env.proj3;   // 由 app.js 注入（属于其他模块）

      var pointInPoly = env.pointInPoly;   // 由 app.js 注入（属于其他模块）

      var distToSeg = env.distToSeg;   // 由 app.js 注入（属于其他模块）

      var conicPathPts = env.conicPathPts;   // 由 app.js 注入（属于其他模块）

      function unproj3(sx, sy, z) {
        var COORD = env.get('COORD'), cam = env.get('cam'), cssH = env.get('cssH'), cssW = env.get('cssW'), ortho3d = env.get('ortho3d'), view3dMode = env.get('view3dMode');
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

      function hitObject3d(sx, sy) {
        var els3d = env.get('els3d');
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

      function nearestPathParam(obj, wx, wy) {
        var EPSILON = env.get('EPSILON');
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

      function hitObject(sx, sy, kinds) {
        var CHART_KINDS = env.get('CHART_KINDS'), chartBoxes = env.get('chartBoxes'), elements = env.get('elements'), scale = env.get('scale');
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

    return {
      unproj3: unproj3,
      hitObject3d: hitObject3d,
      nearestPathParam: nearestPathParam,
      hitObject: hitObject,
    };
  }

  return { create: create };
})();
