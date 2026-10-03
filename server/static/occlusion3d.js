/* ggbpy 三维遮挡判定（P2 前端拆分：render3d 第三步）。
 *
 * 从 render3d 内部抽出，改为**显式参数**（不再依赖闭包局部量）：
 *   - pointInPoly2d(px, py, poly)                纯函数（射线法）
 *   - buildFacePolys(faces)                      面表：屏外接矩形 + 平均深度，近→远排序
 *   - edgeOccluded(p1, p2, facePolys, proj3, onTest)  边中点遮挡测试（先用包围盒筛，再精确判定）
 *
 * render3d 侧保留同名薄包装：
 *   var facePolys = GGB_OCC.buildFacePolys(faces);
 *   function edgeOccluded(p1, p2) {
 *     return GGB_OCC.edgeOccluded(p1, p2, facePolys, proj3, function () { dbgOccTests++; });
 *   }
 */
window.GGB_OCC = (function () {
  'use strict';

    function pointInPoly2d(px, py, poly) {
      var inside = false;
      for (var i = 0, j = poly.length - 1; i < poly.length; j = i++) {
        var xi = poly[i].x, yi = poly[i].y, xj = poly[j].x, yj = poly[j].y;
        if (((yi > py) !== (yj > py)) && (px < (xj - xi) * (py - yi) / (yj - yi) + xi)) inside = !inside;
      }
      return inside;
    }

function buildFacePolys(faces) {
  var facePolys = [];
for (var fpi = 0; fpi < faces.length; fpi++) {
  var fpPoly = faces[fpi].poly;
  if (fpPoly.length < 3) continue;
  var bx0 = Infinity, by0 = Infinity, bx1 = -Infinity, by1 = -Infinity;
  for (var bi = 0; bi < fpPoly.length; bi++) {
    var bpt = fpPoly[bi];
    if (bpt.x < bx0) bx0 = bpt.x;
    if (bpt.y < by0) by0 = bpt.y;
    if (bpt.x > bx1) bx1 = bpt.x;
    if (bpt.y > by1) by1 = bpt.y;
  }
  facePolys.push({ poly: fpPoly, z: faces[fpi].z, x0: bx0, y0: by0, x1: bx1, y1: by1 });
}
facePolys.sort(function (p, q) { return p.z - q.z; });   // 近 → 远
  return facePolys;
}

    function edgeOccluded(p1, p2, facePolys, proj3, onTest) {
      // 边中点投影：先用面屏外接矩形筛掉绝大多数面，再做精确多边形测试
      var a = proj3(p1), b = proj3(p2);
      var mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2, mz = (a.z + b.z) / 2;
      for (var i = 0; i < facePolys.length; i++) {
        var fp = facePolys[i];
        if (fp.z >= mz - 0.01) break;                       // 已排序：更远的都不比中点近
        if (mx < fp.x0 || mx > fp.x1 || my < fp.y0 || my > fp.y1) continue;
        if (onTest) onTest();
        if (pointInPoly2d(mx, my, fp.poly)) return true;
      }
      return false;
    }

  return {
    pointInPoly2d: pointInPoly2d,
    buildFacePolys: buildFacePolys,
    edgeOccluded: edgeOccluded,
  };
})();
