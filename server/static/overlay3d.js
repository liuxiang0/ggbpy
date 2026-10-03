/* ggbpy 三维叠加层绘制（P2 前端拆分：render3d 余下三段）。
 *
 *   drawBasePlane()    基准平面网格（z = planeZ 工作平面指示）
 *   drawSelection3d()  选中三维对象高亮（橙色虚线）
 *   drawZHandle()      z 轴控制柄（选中自由三维点时拖动改高度）
 *
 * 调用顺序（render3d）：clearRect → drawAxes3d → drawBasePlane → scene.drawScene
 *                      → drawSelection3d → drawZHandle → drawMiniAxes3d
 */
window.GGB_OVERLAY = (function () {
  'use strict';

  function create(env) {
    var get = env.get;
    var findEl3d = env.findEl3d;
    var line3 = env.line3;
    var proj3 = env.proj3;

    function drawBasePlane() {
      var ctx3 = get('ctx3'), planeZ = get('planeZ');
      var line3 = env.line3;
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
    }

    function drawSelection3d() {
      var ctx3 = get('ctx3'), selected3d = get('selected3d');
      var findEl3d = env.findEl3d, proj3 = env.proj3;
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
    }

    function drawZHandle() {
      var ctx3 = get('ctx3'), selected3d = get('selected3d');
      var findEl3d = env.findEl3d, proj3 = env.proj3;
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
    }

    return {
      drawBasePlane: drawBasePlane,
      drawSelection3d: drawSelection3d,
      drawZHandle: drawZHandle,
    };
  }

  return { create: create };
})();
