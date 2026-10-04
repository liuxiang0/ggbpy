/* ggbpy 三维对象位移与拖动（P2 前端拆分）（P2 前端拆分：从 app.js 抽出）。
 *
 * 用法（app.js）：
 *   var _drag3d = GGB_DRAG3.create({ get: _stateGet, fmtNum: fmtNum, findEl3d: findEl3d, renderList: renderList, renderList3d: renderList3d, populateEditBar: populateEditBar, sxp: sxp, syp: syp, drawGrid: drawGrid, usableCanvasRect: usableCanvasRect, is3DEl: is3DEl, drawAxes3d: drawAxes3d, drawMiniAxes3d: drawMiniAxes3d, translateMsg: translateMsg, drawSelectionOverlay: drawSelectionOverlay, drawOverlay: drawOverlay, drawElement: drawElement });
 *   之后同名函数由 app.js 保留薄包装，调用点无需改动。
 *
 * 状态：drag3dObj, elements, objShift3d, view
 */
window.GGB_DRAG3 = (function () {
  'use strict';

  function create(env) {
      var api = env.api;   // 由 app.js 注入（属于其他模块）

      var updateUndoBtns = env.updateUndoBtns;   // 由 app.js 注入（属于其他模块）

      var fmtNum = env.fmtNum;   // 由 app.js 注入（属于其他模块）

      var findEl3d = env.findEl3d;   // 由 app.js 注入（属于其他模块）

      var renderList = env.renderList;   // 由 app.js 注入（属于其他模块）

      var renderList3d = env.renderList3d;   // 由 app.js 注入（属于其他模块）

      var populateEditBar = env.populateEditBar;   // 由 app.js 注入（属于其他模块）

      var sxp = env.sxp;   // 由 app.js 注入（属于其他模块）

      var syp = env.syp;   // 由 app.js 注入（属于其他模块）

      var drawGrid = env.drawGrid;   // 由 app.js 注入（属于其他模块）

      var usableCanvasRect = env.usableCanvasRect;   // 由 app.js 注入（属于其他模块）

      var is3DEl = env.is3DEl;   // 由 app.js 注入（属于其他模块）

      var drawAxes3d = env.drawAxes3d;   // 由 app.js 注入（属于其他模块）

      var drawMiniAxes3d = env.drawMiniAxes3d;   // 由 app.js 注入（属于其他模块）

      var translateMsg = env.translateMsg;   // 由 app.js 注入（属于其他模块）

      var drawSelectionOverlay = env.drawSelectionOverlay;   // 由 app.js 注入（属于其他模块）

      var drawOverlay = env.drawOverlay;   // 由 app.js 注入（属于其他模块）

      var drawElement = env.drawElement;   // 由 app.js 注入（属于其他模块）

      var setMsg = env.setMsg;   // 由 app.js 注入（属于其他模块）

      var render = env.render;   // 由 app.js 注入（属于其他模块）

      var tipText = env.tipText;   // 由 app.js 注入（属于其他模块）

      var load3d = env.load3d;   // 由 app.js 注入（属于其他模块）

      var render3d = env.render3d;   // 由 app.js 注入（属于其他模块）

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

      function flushObjShift3d() {
        var drag3dObj = env.get('drag3dObj'), objShift3d = env.get('objShift3d'), view = env.get('view');
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

      function shiftLocal(label, dx, dy) {
        var elements = env.get('elements');
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

    return {
      localShift3dEl: localShift3dEl,
      flushObjShift3d: flushObjShift3d,
      shiftLocal: shiftLocal,
    };
  }

  return { create: create };
})();
