/* ggbpy 三维工具点击交互（P2 前端拆分：3D 工具族）（P2 前端拆分：从 app.js 抽出）。
 *
 * 用法（app.js）：
 *   var _tools3d = GGB_T3D.create({ get: _stateGet, renderList3d: renderList3d, updateToolButtons3d: updateToolButtons3d, camBasis3: camBasis3, proj3: proj3, snapAxis3d: snapAxis3d, distToSeg: distToSeg, drawAxes3d: drawAxes3d, drawMiniAxes3d: drawMiniAxes3d });
 *   之后同名函数由 app.js 保留薄包装，调用点无需改动。
 *
 * 状态：MSG_MAP_EN, RE_MAP_EN, els3d, lang, planeZ, tool3d, toolSel3d, view
 */
window.GGB_T3D = (function () {
  'use strict';

  function create(env) {
      function translateMsg(m) {
        var MSG_MAP_EN = env.get('MSG_MAP_EN'), RE_MAP_EN = env.get('RE_MAP_EN'), lang = env.get('lang');
        if (lang !== 'en' || !m) return m;
        var body = m, prefix = '';
        if (m.indexOf('OK:已创建') === 0) { prefix = 'Created: '; body = m.slice(6); }
        else if (m.indexOf('错误: ') === 0) { prefix = 'Error: '; body = m.slice(4); }
        else if (m.indexOf('CAS: ') === 0) { prefix = 'CAS: '; body = m.slice(5); }
        else if (m.indexOf('CAS 错误') === 0) return 'CAS error';
        else if (m.indexOf('网络错误: ') === 0) { prefix = 'Network error: '; body = m.slice(6); }
        else if (m.indexOf('加载失败: ') === 0) { prefix = 'Load failed: '; body = m.slice(6); }
        else if (m.indexOf('已创建 ') === 0) { prefix = 'Created: '; body = m.slice(4); }
        else {
          for (var k in MSG_MAP_EN) {
            if (m.indexOf(k) === 0) return MSG_MAP_EN[k] + m.slice(k.length);
          }
        }
        for (var i = 0; i < RE_MAP_EN.length; i++) {
          if (RE_MAP_EN[i][0].test(body)) { body = body.replace(RE_MAP_EN[i][0], RE_MAP_EN[i][1]); break; }
        }
        return prefix + body;
      }

      var api = env.api;   // 由 app.js 注入（属于其他模块）

      var updateUndoBtns = env.updateUndoBtns;   // 由 app.js 注入（属于其他模块）

      var renderList3d = env.renderList3d;   // 由 app.js 注入（属于其他模块）

      var updateToolButtons3d = env.updateToolButtons3d;   // 由 app.js 注入（属于其他模块）

      var camBasis3 = env.camBasis3;   // 由 app.js 注入（属于其他模块）

      var proj3 = env.proj3;   // 由 app.js 注入（属于其他模块）

      var snapAxis3d = env.snapAxis3d;   // 由 app.js 注入（属于其他模块）

      var distToSeg = env.distToSeg;   // 由 app.js 注入（属于其他模块）

      var drawAxes3d = env.drawAxes3d;   // 由 app.js 注入（属于其他模块）

      var drawMiniAxes3d = env.drawMiniAxes3d;   // 由 app.js 注入（属于其他模块）

      var setMsg = env.setMsg;   // 由 app.js 注入（属于其他模块）

      var load3d = env.load3d;   // 由 app.js 注入（属于其他模块）

      var unproj3 = env.unproj3;   // 由 app.js 注入（属于其他模块）

      var render3d = env.render3d;   // 由 app.js 注入（属于其他模块）

      var hitPoint3d = env.hitPoint3d;   // 由 app.js 注入（属于其他模块）

      function hitObject3dKind(sx, sy, kinds) {
        var els3d = env.get('els3d');
        var best = null, bestD = 12;
        for (var i = 0; i < els3d.length; i++) {
          var e = els3d[i];
          if (e.visible === false) continue;
          if (kinds.indexOf(e.objtype) === -1) continue;
          var dt = e.data || {};
          if (e.objtype === 'segment') {
            var s1 = proj3([dt.x1, dt.y1, dt.z1]), s2 = proj3([dt.x2, dt.y2, dt.z2]);
            var ds = distToSeg(sx, sy, s1.x, s1.y, s2.x, s2.y);
            if (ds <= 10 && ds < bestD) { bestD = ds; best = e; }
          } else if (e.objtype === 'circle2d') {
            var cc3 = [dt.cx || 0, dt.cy || 0, dt.cz || 0], cr3 = dt.r || 0;
            var prevC = null;
            for (var ci3 = 0; ci3 <= 48; ci3++) {
              var angC = 2 * Math.PI * ci3 / 48;
              var prC = proj3([cc3[0] + cr3 * Math.cos(angC), cc3[1] + cr3 * Math.sin(angC), cc3[2]]);
              if (prevC) {
                var dC = distToSeg(sx, sy, prevC.x, prevC.y, prC.x, prC.y);
                if (dC <= 10 && dC < bestD) { bestD = dC; best = e; }
              }
              prevC = prC;
            }
          } else if (e.objtype === 'polygon2d') {
            var pts = dt.pts || [];
            var sp = [];
            for (var pi = 0; pi < pts.length; pi++) {
              var pa = proj3(pts[pi]), pb = proj3(pts[(pi + 1) % pts.length]);
              sp.push([pa.x, pa.y]);
              var dp = distToSeg(sx, sy, pa.x, pa.y, pb.x, pb.y);
              if (dp <= 10 && dp < bestD) { bestD = dp; best = e; }
            }
            // 点击内部也可命中
            var inside3 = false;
            for (var a3 = 0, b3 = sp.length - 1; a3 < sp.length; b3 = a3++) {
              if (((sp[a3][1] > sy) !== (sp[b3][1] > sy)) &&
                  (sx < (sp[b3][0] - sp[a3][0]) * (sy - sp[a3][1]) / (sp[b3][1] - sp[a3][1]) + sp[a3][0])) inside3 = !inside3;
            }
            if (inside3) { bestD = 0; best = e; }
          }
        }
        return best;
      }

      function tool3dPointAt(sx, sy, cb) {
        var els3d = env.get('els3d'), planeZ = env.get('planeZ');
        var hit = hitPoint3d(sx, sy);
        if (hit) { cb(hit.label); return; }
        // 轴吸附优先：点击 z 轴（竖直中心线）→ 得到 z 轴上的点 (0,0,z)
        var snap = snapAxis3d(sx, sy);
        if (snap) {
          var w0 = [snap.ax[0] * snap.t, snap.ax[1] * snap.t, snap.ax[2] * snap.t];
          postInput3d('(' + fmtW(w0[0]) + ',' + fmtW(w0[1]) + ',' + fmtW(w0[2]) + ')', function (d) {
            if (!d || !d.ok) { resetTool3d(); return; }
            var prev0 = {};
            for (var i0 = 0; i0 < els3d.length; i0++) prev0[els3d[i0].label] = true;
            var newEls0 = d.elements || [];
            for (var j0 = 0; j0 < newEls0.length; j0++) {
              if (newEls0[j0].kind === 'point' && !prev0[newEls0[j0].label]) { cb(newEls0[j0].label); return; }
            }
            load3d();
            cb(null);
          });
          return;
        }
        var w = unproj3(sx, sy, planeZ);
        // 把工作平面上的取点限制在合理范围（透视近处点会延伸到远处，钳制到 ±10）
        var CLAMP = 10;
        w[0] = Math.max(-CLAMP, Math.min(CLAMP, w[0]));
        w[1] = Math.max(-CLAMP, Math.min(CLAMP, w[1]));
        postInput3d('(' + fmtW(w[0]) + ',' + fmtW(w[1]) + ',' + fmtW(w[2]) + ')', function (d) {
          if (!d || !d.ok) { resetTool3d(); return; }
          // 用 API 返回的完整 elements（比异步 load3d 可靠），找到刚创建的点
          var prev = {};
          for (var i = 0; i < els3d.length; i++) prev[els3d[i].label] = true;
          var newEls = d.elements || [];
          for (var j = 0; j < newEls.length; j++) {
            if (newEls[j].kind === 'point' && !prev[newEls[j].label]) { cb(newEls[j].label); return; }
          }
          load3d();
          cb(null);
        });
      }

      function tool3dClick(sx, sy) {
        var lang = env.get('lang'), tool3d = env.get('tool3d');
        // 3D 测量工具：体积 / 表面积 —— 点立体即可（与 Volume/SurfaceArea 命令能力一致）
        if (tool3d === 'vol3d' || tool3d === 'sarea3d') {
          var solid = env.hitObjectForDrag3d ? env.hitObjectForDrag3d(sx, sy) : null;
          var isSolid = solid && (solid.objtype === 'cube' || solid.objtype === 'polyhedron' || solid.objtype === 'sphere');
          if (!isSolid) {
            setMsg(lang === 'en'
              ? 'Click a solid (cube / polyhedron / sphere / cone / cylinder)'
              : '请点击立体（立方体/多面体/球/圆锥/圆柱）', true);
            return;
          }
          var c3m = tool3d === 'vol3d' ? 'Volume[' : 'SurfaceArea[';
          postInput3d(c3m + solid.label + ']', function (d) {
            if (!d || !d.ok) return;
            var nums = (d.elements || []).filter(function (e) { return e.kind === 'number'; });
            var vtxt = nums.length ? String(nums[nums.length - 1].value || '').replace(/^=\s*/, '') : '?';
            setMsg((tool3d === 'vol3d'
              ? (lang === 'en' ? 'Volume ' : '体积 ')
              : (lang === 'en' ? 'Surface area ' : '表面积 ')) + solid.label + ' = ' + vtxt, false);
            env.set('toolSel3d', []);
            setToolStatus3d();
          });
          return;
        }
        if (tool3d === 'pt3d') {
          tool3dPointAt(sx, sy, function () {
            // 连续操作：保持工具激活，可继续画下一个点（Esc / 再点按钮退出）
            env.set('toolSel3d', []);
            setToolStatus3d();
          });
          return;
        }
        if (tool3d === 'seg3d' || tool3d === 'line3d') {
          tool3dPointAt(sx, sy, function (lbl) {
            if (!lbl) return;
            env.get('toolSel3d').push(lbl);
            if (env.get('toolSel3d').length === 2) {
              var cmd3 = tool3d === 'seg3d' ? 'Segment[' : 'Line[';
              postInput3d(cmd3 + env.get('toolSel3d').join(',') + ']', function (ok) { if (ok) { env.set('toolSel3d', []); setToolStatus3d(); } });
            } else setToolStatus3d();
          });
          return;
        }
        if (tool3d === 'plane3d') {
          tool3dPointAt(sx, sy, function (lbl) {
            if (!lbl) return;
            env.get('toolSel3d').push(lbl);
            if (env.get('toolSel3d').length === 3) {
              postInput3d('Plane[' + env.get('toolSel3d').join(',') + ']', function (ok) { if (ok) { env.set('toolSel3d', []); setToolStatus3d(); } });
            } else setToolStatus3d();
          });
          return;
        }
        if (tool3d === 'sphere3d') {
          tool3dPointAt(sx, sy, function (lbl) {
            if (!lbl) return;
            env.get('toolSel3d').push(lbl);
            if (env.get('toolSel3d').length === 2) {
              postInput3d('Sphere[' + env.get('toolSel3d').join(',') + ']', function (ok) { if (ok) { resetTool3d(); } });
            } else setToolStatus3d();
          });
          return;
        }
        if (tool3d === 'cube3d') {
          function cubeCreate3(cmd) {
            postInput3d(cmd, function (ok) { if (ok) { resetTool3d(); } });   // 立方体建完自动退出
          }
          // 1) 点优先：点两个空间点 → Cube[A,B]；已选一点则补成第二点
          var ptHit3 = hitPoint3d(sx, sy);
          if (ptHit3) {
            env.get('toolSel3d').push(ptHit3.label);
            if (env.get('toolSel3d').length >= 2) cubeCreate3('Cube[' + env.get('toolSel3d').join(',') + ']');
            else setToolStatus3d();
            return;
          }
          // 2) 线段：直接 Cube[线段]；已选一点 → Cube[线段, 点]
          var segHit3 = hitObject3dKind(sx, sy, ['segment']);
          if (segHit3) {
            if (env.get('toolSel3d').length >= 1) cubeCreate3('Cube[' + segHit3.label + ',' + env.get('toolSel3d')[0] + ']');
            else cubeCreate3('Cube[' + segHit3.label + ']');
            return;
          }
          // 3) 正方形多边形：Cube[正方形]
          var polyHit3 = hitObject3dKind(sx, sy, ['polygon2d']);
          if (polyHit3) {
            cubeCreate3('Cube[' + polyHit3.label + ']');
            return;
          }
          // 4) 空白：在基准平面取点
          tool3dPointAt(sx, sy, function (lbl) {
            if (!lbl) return;
            env.get('toolSel3d').push(lbl);
            if (env.get('toolSel3d').length >= 2) cubeCreate3('Cube[' + env.get('toolSel3d').join(',') + ']');
            else setToolStatus3d();
          });
          return;
        }
        if (tool3d === 'cone3d') {
          // 形式 1：点已有圆（3D 中显示的圆）→ 输入高度
          if (env.get('toolSel3d').length === 0) {
            var circHit3 = hitObject3dKind(sx, sy, ['circle2d']);
            if (circHit3) {
              var hTxt = prompt(lang === 'en' ? 'Cone height:' : '圆锥高度：', '3');
              if (hTxt === null || hTxt.trim() === '') { resetTool3d(); return; }
              var hv3 = parseFloat(hTxt);
              if (isNaN(hv3) || hv3 <= 0) { setMsg(lang === 'en' ? 'Enter a positive height' : '请输入正数高度', true); return; }
              postInput3d('Cone[' + circHit3.label + ',' + hv3 + ']', function (ok) { if (ok) { resetTool3d(); } });
              return;
            }
            tool3dPointAt(sx, sy, function (lbl) {
              if (!lbl) return;
              env.set('toolSel3d', [lbl]);   // 顶点
              setToolStatus3d();
            });
            return;
          }
          // 形式 2：顶点已定 → 点底面中心（随后输入半径；取消则改点半径点走三点式）
          if (env.get('toolSel3d').length === 1) {
            tool3dPointAt(sx, sy, function (lbl) {
              if (!lbl) return;
              var apex3 = env.get('toolSel3d')[0];
              var rTxt = prompt(lang === 'en' ? 'Base radius (Cancel → pick a radius point):'
                                              : '底面半径（取消 → 再点一个底面半径点）：', '2');
              if (rTxt === null) { env.set('toolSel3d', [apex3, lbl]); setToolStatus3d(); return; }
              var rv3 = parseFloat(rTxt);
              if (isNaN(rv3) || rv3 <= 0) { setMsg(lang === 'en' ? 'Enter a positive radius' : '请输入正数半径', true); return; }
              postInput3d('Cone[' + apex3 + ',' + lbl + ',' + rv3 + ']', function (ok) { if (ok) { resetTool3d(); } });
            });
            return;
          }
          // 形式 3（经典三点）：顶点、底心已定 → 点底面半径点 → Cone[底心, 半径点, 顶点]
          if (env.get('toolSel3d').length === 2) {
            tool3dPointAt(sx, sy, function (lbl) {
              if (!lbl) return;
              var apex4 = env.get('toolSel3d')[0], base4 = env.get('toolSel3d')[1];
              postInput3d('Cone[' + base4 + ',' + lbl + ',' + apex4 + ']', function (ok) { if (ok) { resetTool3d(); } });
            });
            return;
          }
        }
        if (tool3d === 'cylinder3d') {
          // 形式 1：点已有圆 → 输入高度 → Cylinder[圆, 高]
          if (env.get('toolSel3d').length === 0) {
            var cycHit3 = hitObject3dKind(sx, sy, ['circle2d']);
            if (cycHit3) {
              var chTxt = prompt(lang === 'en' ? 'Cylinder height:' : '圆柱高度：', '3');
              if (chTxt === null || chTxt.trim() === '') { resetTool3d(); return; }
              var chv3 = parseFloat(chTxt);
              if (isNaN(chv3) || chv3 <= 0) { setMsg(lang === 'en' ? 'Enter a positive height' : '请输入正数高度', true); return; }
              postInput3d('Cylinder[' + cycHit3.label + ',' + chv3 + ']', function (ok) { if (ok) { resetTool3d(); } });
              return;
            }
            tool3dPointAt(sx, sy, function (lbl) {
              if (!lbl) return;
              env.set('toolSel3d', [lbl]);   // 底面圆心
              setToolStatus3d();
            });
            return;
          }
          // 形式 2：底心已定 → 点顶面圆心（随后输入半径；取消则改点半径点走三点式）
          if (env.get('toolSel3d').length === 1) {
            tool3dPointAt(sx, sy, function (lbl) {
              if (!lbl) return;
              var cbase3 = env.get('toolSel3d')[0];
              var crTxt = prompt(lang === 'en' ? 'Radius (Cancel → pick a radius point):'
                                               : '底面半径（取消 → 再点一个底面半径点）：', '2');
              if (crTxt === null) { env.set('toolSel3d', [cbase3, lbl]); setToolStatus3d(); return; }
              var crv3 = parseFloat(crTxt);
              if (isNaN(crv3) || crv3 <= 0) { setMsg(lang === 'en' ? 'Enter a positive radius' : '请输入正数半径', true); return; }
              postInput3d('Cylinder[' + cbase3 + ',' + lbl + ',' + crv3 + ']', function (ok) { if (ok) { resetTool3d(); } });
            });
            return;
          }
          // 形式 3（经典三点）：底心、顶心已定 → 点底面半径点 → Cylinder[底心, 半径点, 顶心]
          if (env.get('toolSel3d').length === 2) {
            tool3dPointAt(sx, sy, function (lbl) {
              if (!lbl) return;
              var cbase5 = env.get('toolSel3d')[0], ctop5 = env.get('toolSel3d')[1];
              postInput3d('Cylinder[' + cbase5 + ',' + lbl + ',' + ctop5 + ']', function (ok) { if (ok) { resetTool3d(); } });
            });
            return;
          }
        }
    
        // 通用 3 点多面体工具：圆锥/圆柱/棱柱/棱锥/正四面体/正八面体/正二十面体/正十二面体
        var SOLID3_CMD = { cone3d: 'Cone', cylinder3d: 'Cylinder', prism3d: 'Prism', pyramid3d: 'Pyramid',
                           tetra3d: 'Tetrahedron', octa3d: 'Octahedron', hexa3d: 'Hexahedron', icosa3d: 'Icosahedron', dodeca3d: 'Dodecahedron' };
        if (SOLID3_CMD[tool3d]) {
          tool3dPointAt(sx, sy, function (lbl) {
            if (!lbl) return;
            env.get('toolSel3d').push(lbl);
            if (env.get('toolSel3d').length === 3) {
              postInput3d(SOLID3_CMD[tool3d] + '[' + env.get('toolSel3d').join(',') + ']', function (ok) { if (ok) { resetTool3d(); } });
            } else setToolStatus3d();
          });
          return;
        }
      }

      var setToolStatus3d = env.setToolStatus3d;   // 由 app.js 注入（属于其他模块）

      var resetTool3d = env.resetTool3d;   // 由 app.js 注入（属于其他模块）

      function postInput3d(text, cb) {
        var view = env.get('view');
        api('POST', '/api/input', { text: text, xmin: view.xmin, xmax: view.xmax, ymin: view.ymin, ymax: view.ymax }, function (d) {
          setMsg(d.message, !d.ok);
          if (d.ok) load3d();
          if (cb) cb(d);
        });
      }

      var fmtW = env.fmtW;   // 由 app.js 注入（属于其他模块）

    return {
      translateMsg: translateMsg,
      hitObject3dKind: hitObject3dKind,
      tool3dPointAt: tool3dPointAt,
      tool3dClick: tool3dClick,
      postInput3d: postInput3d,
    };
  }

  return { create: create };
})();
