/* ggbpy 三维场景绘制（P2 前端拆分：render3d 主绘制段）。
 *
 * 覆盖：几何收集（面片/边/点，含网格 LOD 与投影复用缓存）→ 画家算法排序 →
 *       遮挡分类（实线/虚线）→ 顶点绘制与标签。
 * 原为 render3d 内的一段 245 行内联代码（依赖众多闭包局部量），现改为 env 注入 + 显式状态读取。
 *
 * app.js 侧调用：_scene.drawScene();
 */
window.GGB_SCENE = (function () {
  'use strict';

  function create(env) {
    var get = env.get, set = env.set;
    var line3 = env.line3, proj3 = env.proj3, selectMeshFaces = env.selectMeshFaces;

    function drawScene() {
      var C = get('C'), ctx3 = get('ctx3'), els3d = get('els3d'), selected3d = get('selected3d');
      var MESH_EDGE_BUDGET = get('MESH_EDGE_BUDGET'), OCCLUSION_BUDGET = get('OCCLUSION_BUDGET');

      // 收集面片（画家算法）
      var faces = [];
      var polys = [];
      var segs = [];
      var pts = [];
      for (var i = 0; i < els3d.length; i++) {
        var e = els3d[i];
        if (e.visible === false) continue;   // show/hide：隐藏对象不渲染
        if (e.kind === 'point') {
          var pr = proj3([e.x, e.y, e.z]);
          pts.push({ x: pr.x, y: pr.y, label: e.label, free: e.free });
          continue;
        }
        var dt = e.data || {};
        // 多面体统一渲染：立方体 + 圆锥/圆柱/棱柱/棱锥/正多面体（verts/faces/edges 数据模型）
        if (e.objtype === 'cube' || e.objtype === 'polyhedron') {
          var verts = dt.verts;
          var cfaces = dt.faces || [];
          var fillCol = e.objtype === 'cube' ? 'rgba(79,70,229,.16)' : 'rgba(217,70,239,.12)';
          var strokeCol = e.objtype === 'cube' ? '#4f46e5' : '#d946ef';
          cfaces = selectMeshFaces(e, verts, cfaces);   // 大网格 LOD：只画最大的若干面
          // 顶点投影复用：同一顶点被多面共用，避免每面重复 proj3（大网格下省一大截）
          var projV = [];
          var projVFn = function (vi2) {
            var q = projV[vi2];
            if (q === undefined) { q = proj3(verts[vi2]); projV[vi2] = q; } else { set('dbgProjReuse', get('dbgProjReuse') + 1); }
            return q;
          };
          for (var f = 0; f < cfaces.length; f++) {
            var idx = cfaces[f];
            var poly = [];
            var zsum = 0;
            for (var vi = 0; vi < idx.length; vi++) {
              var pr2 = projVFn(idx[vi]);
              poly.push(pr2);
              zsum += pr2.z;
            }
            faces.push({ poly: poly, z: zsum / idx.length, color: fillCol, stroke: strokeCol, wire: e.wire });
          }
          if ((dt.edges || []).length <= MESH_EDGE_BUDGET) {
            for (var ed = 0; ed < (dt.edges || []).length; ed++) {
              var e2 = dt.edges[ed];
              segs.push([verts[e2[0]], verts[e2[1]]]);
            }
          }
        } else if (e.objtype === 'plane') {
          var a3 = [dt.ax, dt.ay, dt.az], u3 = [dt.ux, dt.uy, dt.uz], v3 = [dt.vx, dt.vy, dt.vz];
          var quad = [[a3[0], a3[1], a3[2]],
                      [a3[0] + u3[0], a3[1] + u3[1], a3[2] + u3[2]],
                      [a3[0] + u3[0] + v3[0], a3[1] + u3[1] + v3[1], a3[2] + u3[2] + v3[2]],
                      [a3[0] + v3[0], a3[1] + v3[1], a3[2] + v3[2]]];
          var poly3 = [], zs3 = 0;
          for (var q = 0; q < 4; q++) {
            var pr3 = proj3(quad[q]);
            poly3.push(pr3);
            zs3 += pr3.z;
          }
          faces.push({ poly: poly3, z: zs3 / 4, color: 'rgba(14,165,233,.14)', stroke: '#0ea5e9', wire: e.wire });
        } else if (e.objtype === 'sphere') {
          var sc = [dt.cx, dt.cy, dt.cz], sr = dt.r;
          var rings = [];
          // 精细球面：更多纬/经分段，细线绘制
          var latN = 16, longN = 40;
          for (var lat = 1; lat < latN; lat++) {
            var ph = Math.PI * lat / latN;
            var rr = sr * Math.sin(ph), yy = sr * Math.cos(ph);
            var ring = [];
            for (var li2 = 0; li2 <= longN; li2++) {
              var th2 = Math.PI * 2 * li2 / longN;
              ring.push([sc[0] + rr * Math.cos(th2), sc[1] + yy, sc[2] + rr * Math.sin(th2)]);
            }
            rings.push(ring);
          }
          for (var lo = 0; lo < longN; lo++) {
            var ring2 = [];
            for (var la2 = 0; la2 <= latN; la2++) {
              var ph2 = Math.PI * la2 / latN;
              ring2.push([sc[0] + sr * Math.sin(ph2) * Math.cos(2 * Math.PI * lo / longN),
                          sc[1] + sr * Math.cos(ph2),
                          sc[2] + sr * Math.sin(ph2) * Math.sin(2 * Math.PI * lo / longN)]);
            }
            rings.push(ring2);
          }
          for (var rg = 0; rg < rings.length; rg++) {
            var ringPts = [];
            var zr = 0;
            for (var rp2 = 0; rp2 < rings[rg].length; rp2++) {
              var pr4 = proj3(rings[rg][rp2]);
              ringPts.push(pr4);
              zr += pr4.z;
            }
            faces.push({ poly: ringPts, z: zr / ringPts.length, color: 'rgba(217,70,239,.06)', stroke: 'rgba(217,70,239,.55)', wire: e.wire });
          }
        } else if (e.objtype === 'curve3d') {
          var cs = dt.segs || [];
          for (var ci4 = 0; ci4 < cs.length; ci4++) segs.push([cs[ci4][0], cs[ci4][1]]);
        } else if (e.objtype === 'circle3d') {
          // 空间圆（球∩平面）：用平面内正交基采样成闭合折线
          var c3 = dt, u3 = dt.u || [1, 0, 0], v3 = dt.v || [0, 1, 0];
          var seg3 = 64, prev3 = null, first3 = null;
          for (var ci3 = 0; ci3 <= seg3; ci3++) {
            var th3 = 2 * Math.PI * ci3 / seg3;
            var pt3 = [c3.cx + c3.r * (Math.cos(th3) * u3[0] + Math.sin(th3) * v3[0]),
                       c3.cy + c3.r * (Math.cos(th3) * u3[1] + Math.sin(th3) * v3[1]),
                       c3.cz + c3.r * (Math.cos(th3) * u3[2] + Math.sin(th3) * v3[2])];
            if (prev3) segs.push([prev3, pt3]);
            else first3 = pt3;
            prev3 = pt3;
          }
        } else if (e.objtype === 'section') {
          // 平面截立体得到的截面多边形（任意空间平面）：填充 + 闭合边
          var sPts = dt.pts || [];
          if (sPts.length >= 3) {
            var sPoly = [], zSs = 0;
            for (var sPi = 0; sPi < sPts.length; sPi++) {
              var sPr = proj3(sPts[sPi]);
              sPoly.push(sPr);
              zSs += sPr.z;
            }
            faces.push({ poly: sPoly, z: zSs / sPts.length, color: 'rgba(245,158,11,.22)', stroke: '#d97706', wire: false });
          }
          for (var sPe = 0; sPe < sPts.length; sPe++) {
            segs.push([sPts[sPe], sPts[(sPe + 1) % sPts.length]]);
          }
        } else if (e.objtype === 'segment' || e.objtype === 'line2d' || e.objtype === 'line3d') {
          segs.push([[dt.x1, dt.y1, dt.z1], [dt.x2, dt.y2, dt.z2]]);
        } else if (e.objtype === 'circle2d') {
          // 2D 圆（z=0，xoy 平面）：采样 48 点成环
          var c2 = [dt.cx, dt.cy, dt.cz], r2 = dt.r;
          for (var ci2 = 0; ci2 < 48; ci2++) {
            var thA = 2 * Math.PI * ci2 / 48, thB = 2 * Math.PI * (ci2 + 1) / 48;
            segs.push([[c2[0] + r2 * Math.cos(thA), c2[1] + r2 * Math.sin(thA), c2[2]],
                       [c2[0] + r2 * Math.cos(thB), c2[1] + r2 * Math.sin(thB), c2[2]]]);
          }
        } else if (e.objtype === 'polygon2d') {
          // 2D 多边形（z=0）：填充面 + 边
          var p2pts = dt.pts || [];
          if (p2pts.length >= 3) {
            var p2poly = [], z2s = 0;
            for (var p2i = 0; p2i < p2pts.length; p2i++) {
              var p2pr = proj3(p2pts[p2i]);
              p2poly.push(p2pr);
              z2s += p2pr.z;
            }
            faces.push({ poly: p2poly, z: z2s / p2pts.length, color: 'rgba(59,130,246,.12)', stroke: '#3b82f6', wire: e.wire });
          }
          for (var p2e = 0; p2e < p2pts.length; p2e++) {
            segs.push([p2pts[p2e], p2pts[(p2e + 1) % p2pts.length]]);
          }
        } else if (e.objtype === 'vector2d') {
          segs.push([[dt.sx, dt.sy, dt.sz], [dt.sx + dt.dx, dt.sy + dt.dy, dt.sz + dt.dz]]);
        } else if (e.objtype === 'polyline2d') {
          var pl2pts = dt.pts || [];
          for (var pl2i = 0; pl2i + 1 < pl2pts.length; pl2i++) {
            segs.push([pl2pts[pl2i], pl2pts[pl2i + 1]]);
          }
        }
      }
      faces.sort(function (a, b) { return b.z - a.z; });
      for (var fi = 0; fi < faces.length; fi++) {
        var fc = faces[fi];
        if (fc.wire) {
          // 线框模式：不填充面，但保留描边——球/平面等无独立边线的物体靠面描边显示网格线框
          ctx3.strokeStyle = fc.stroke;
          ctx3.lineWidth = fc.stroke === 'rgba(217,70,239,.55)' ? 0.7 : 1;
          ctx3.beginPath();
          ctx3.moveTo(fc.poly[0].x, fc.poly[0].y);
          for (var fp2 = 1; fp2 < fc.poly.length; fp2++) ctx3.lineTo(fc.poly[fp2].x, fc.poly[fp2].y);
          ctx3.closePath();
          ctx3.stroke();
          continue;
        }
        ctx3.fillStyle = fc.color;
        ctx3.strokeStyle = fc.stroke;
        ctx3.lineWidth = fc.stroke === 'rgba(217,70,239,.55)' ? 0.7 : 1.2;
        ctx3.beginPath();
        ctx3.moveTo(fc.poly[0].x, fc.poly[0].y);
        for (var fp = 1; fp < fc.poly.length; fp++) ctx3.lineTo(fc.poly[fp].x, fc.poly[fp].y);
        ctx3.closePath();
        ctx3.fill();
        ctx3.stroke();
      }
      // 遮挡处理：边端点投影落在某面屏幕多边形内且该面更近 → 被遮挡（虚线）
      // 面表构建与遮挡判定已抽到 static/occlusion3d.js（P2 前端拆分）
      var facePolys = window.GGB_OCC.buildFacePolys(faces);
      function edgeOccluded(p1, p2) {
        return window.GGB_OCC.edgeOccluded(p1, p2, facePolys, proj3, function () { set('dbgOccTests', get('dbgOccTests') + 1); });
      }
      set('dbgLastFaces', faces.length);
      set('dbgLastSegs', segs.length);
      var doOcclusion = (faces.length * segs.length) <= OCCLUSION_BUDGET;
      for (var si = 0; si < segs.length; si++) {
        var occ = doOcclusion && edgeOccluded(segs[si][0], segs[si][1]);
        if (occ) {
          var oa = proj3(segs[si][0]), ob = proj3(segs[si][1]);
          ctx3.strokeStyle = 'rgba(107,114,128,.55)';
          ctx3.lineWidth = 1.6;
          ctx3.setLineDash([4, 3]);
          ctx3.beginPath();
          ctx3.moveTo(oa.x, oa.y); ctx3.lineTo(ob.x, ob.y);
          ctx3.stroke();
          ctx3.setLineDash([]);
        } else {
          line3(segs[si][0], segs[si][1], C.text, 2);
        }
      }
      ctx3.font = '13px sans-serif';
      for (var pi = 0; pi < pts.length; pi++) {
        var pt = pts[pi];
        var selPt = (selected3d === pt.label);
        if (pt.free) {
          // 控制点（自由点）：实心菱形 + 白边（可拖动，改变关联立体大小）
          var r0 = selPt ? 7 : 5;
          ctx3.beginPath();
          ctx3.moveTo(pt.x, pt.y - r0);
          ctx3.lineTo(pt.x + r0, pt.y);
          ctx3.lineTo(pt.x, pt.y + r0);
          ctx3.lineTo(pt.x - r0, pt.y);
          ctx3.closePath();
          ctx3.fillStyle = selPt ? '#f59e0b' : '#dc2626';
          ctx3.fill();
          ctx3.lineWidth = 1.5;
          ctx3.strokeStyle = '#ffffff';
          ctx3.stroke();
        } else {
          ctx3.beginPath();
          ctx3.arc(pt.x, pt.y, selPt ? 6.5 : 4, 0, Math.PI * 2);
          ctx3.fillStyle = selPt ? '#f59e0b' : '#2563eb';
          ctx3.fill();
          if (selPt) { ctx3.lineWidth = 1.5; ctx3.strokeStyle = '#ffffff'; ctx3.stroke(); }
        }
        if (selPt) {
          // 选中：橙色虚线光环强调
          ctx3.beginPath();
          ctx3.arc(pt.x, pt.y, (pt.free ? 7 : 6.5) + 3.5, 0, Math.PI * 2);
          ctx3.strokeStyle = '#f59e0b';
          ctx3.lineWidth = 2;
          ctx3.setLineDash([4, 3]);
          ctx3.stroke();
          ctx3.setLineDash([]);
        }
        ctx3.fillStyle = selPt ? '#f59e0b' : C.text;
        ctx3.font = selPt ? 'bold 13px sans-serif' : '13px sans-serif';
        ctx3.fillText(pt.label, pt.x + 8, pt.y - 5);
      }
    }

    return { drawScene: drawScene };
  }

  return { create: create };
})();
