/* ggbpy 二维工具点击交互（P2 前端拆分：2D 工具族）（P2 前端拆分：从 app.js 抽出）。
 *
 * 用法（app.js）：
 *   var _tools2d = GGB_T2D.create({ get: _stateGet, t: t, fmtNum: fmtNum, renderList: renderList, renderList3d: renderList3d, populateEditBar: populateEditBar, populateEditBar3d: populateEditBar3d, updateToolButtons: updateToolButtons, sxp: sxp, syp: syp, niceStep: niceStep, drawGrid: drawGrid, usableCanvasRect: usableCanvasRect, is3DEl: is3DEl, pointInPoly: pointInPoly, distToSeg: distToSeg, drawAxes3d: drawAxes3d, drawMiniAxes3d: drawMiniAxes3d, translateMsg: translateMsg, drawSelectionOverlay: drawSelectionOverlay, drawOverlay: drawOverlay, drawElement: drawElement, conicPathPts: conicPathPts });
 *   之后同名函数由 app.js 保留薄包装，调用点无需改动。
 *
 * 状态：CHART_TOOL_CMD, COORD, activeTool, canvas, cssH, cssW, elements, hintEl, lang, pendingImage, scale, shiftKeyPressed, snapOn, toolBusy, toolPointQueue, toolSel, view
 */
window.GGB_T2D = (function () {
  'use strict';

  function create(env) {
      var wxp = env.wxp;   // 由 app.js 注入（属于其他模块）

      var wyp = env.wyp;   // 由 app.js 注入（属于其他模块）

      function viewParams() {
        var view = env.get('view');
        return '?xmin=' + view.xmin.toFixed(4) + '&xmax=' + view.xmax.toFixed(4) +
               '&ymin=' + view.ymin.toFixed(4) + '&ymax=' + view.ymax.toFixed(4);
      }

      var loadState = env.loadState;   // 由 app.js 注入（属于其他模块）

      var api = env.api;   // 由 app.js 注入（属于其他模块）

      var updateUndoBtns = env.updateUndoBtns;   // 由 app.js 注入（属于其他模块）

      var t = env.t;   // 由 app.js 注入（属于其他模块）

      var fmtNum = env.fmtNum;   // 由 app.js 注入（属于其他模块）

      var renderList = env.renderList;   // 由 app.js 注入（属于其他模块）

      var renderList3d = env.renderList3d;   // 由 app.js 注入（属于其他模块）

      var populateEditBar = env.populateEditBar;   // 由 app.js 注入（属于其他模块）

      var populateEditBar3d = env.populateEditBar3d;   // 由 app.js 注入（属于其他模块）

      var updateToolButtons = env.updateToolButtons;   // 由 app.js 注入（属于其他模块）

      var sxp = env.sxp;   // 由 app.js 注入（属于其他模块）

      var syp = env.syp;   // 由 app.js 注入（属于其他模块）

      var niceStep = env.niceStep;   // 由 app.js 注入（属于其他模块）

      var drawGrid = env.drawGrid;   // 由 app.js 注入（属于其他模块）

      var usableCanvasRect = env.usableCanvasRect;   // 由 app.js 注入（属于其他模块）

      var is3DEl = env.is3DEl;   // 由 app.js 注入（属于其他模块）

      var pointInPoly = env.pointInPoly;   // 由 app.js 注入（属于其他模块）

      var distToSeg = env.distToSeg;   // 由 app.js 注入（属于其他模块）

      var drawAxes3d = env.drawAxes3d;   // 由 app.js 注入（属于其他模块）

      var drawMiniAxes3d = env.drawMiniAxes3d;   // 由 app.js 注入（属于其他模块）

      var translateMsg = env.translateMsg;   // 由 app.js 注入（属于其他模块）

      var drawSelectionOverlay = env.drawSelectionOverlay;   // 由 app.js 注入（属于其他模块）

      var drawOverlay = env.drawOverlay;   // 由 app.js 注入（属于其他模块）

      var drawElement = env.drawElement;   // 由 app.js 注入（属于其他模块）

      var conicPathPts = env.conicPathPts;   // 由 app.js 注入（属于其他模块）

      var setMsg = env.setMsg;   // 由 app.js 注入（属于其他模块）

      var render = env.render;   // 由 app.js 注入（属于其他模块）

      function chartDataPrompt(title, def) {
        var txt = prompt(title, def || '');
        if (txt === null || !txt.trim()) return null;
        var parts = txt.split(/[,，\s]+/).map(function (v) { return v.trim(); }).filter(Boolean);
        if (!parts.length || parts.some(function (v) { return isNaN(parseFloat(v)); })) return '';
        return parts;
      }

      var chartToolPrompt = env.chartToolPrompt;   // 由 app.js 注入（属于其他模块）

      var tipText = env.tipText;   // 由 app.js 注入（属于其他模块）

      var snapPoint = env.snapPoint;   // 由 app.js 注入（属于其他模块）

      var load3d = env.load3d;   // 由 app.js 注入（属于其他模块）

      var render3d = env.render3d;   // 由 app.js 注入（属于其他模块）

      var postInput = env.postInput;   // 由 app.js 注入（属于其他模块）

      var hitAnyPoint = env.hitAnyPoint;   // 由 app.js 注入（属于其他模块）

      var toolHintText = env.toolHintText;   // 由 app.js 注入（属于其他模块）

      var setToolStatus = env.setToolStatus;   // 由 app.js 注入（属于其他模块）

      var cancelTool = env.cancelTool;   // 由 app.js 注入（属于其他模块）

      function resetTool() {
        var hintEl = env.get('hintEl');
        env.set('toolSel', []);
        env.set('pendingImage', null);
        updateToolButtons();
        setToolStatus();
        hintEl.textContent = toolHintText();
      }

      var fmtW = env.fmtW;   // 由 app.js 注入（属于其他模块）

      function snapHitLabel(wx, wy) {
        var COORD = env.get('COORD'), elements = env.get('elements');
        for (var shi = 0; shi < elements.length; shi++) {
          var she = elements[shi];
          if (she.kind !== 'point' || she.visible === false) continue;
          if (Math.abs(she.x - wx) < COORD && Math.abs(she.y - wy) < COORD) return she.label;
        }
        return null;
      }

      function toolPointAt(sx, sy, cb) {
        var activeTool = env.get('activeTool'), elements = env.get('elements'), pendingImage = env.get('pendingImage'), shiftKeyPressed = env.get('shiftKeyPressed'), snapOn = env.get('snapOn'), toolPointQueue = env.get('toolPointQueue');
        if (env.get('toolBusy')) {
          toolPointQueue.push([sx, sy, cb]);
          return;
        }
        var lbl = hitAnyPoint(sx, sy);
        if (lbl) { cb(lbl); return; }
        var wx = wxp(sx), wy = wyp(sy);
        if (snapOn || shiftKeyPressed) {
          var snapped = snapPoint(wx, wy, niceStep(), sx, sy);
          wx = snapped[0]; wy = snapped[1];
          // 吸附后落点若与某个已有点重合 → 复用该点（避免网格点处新建重叠点）
          var rl = snapHitLabel(wx, wy);
          if (rl) { cb(rl); return; }
        }
        var prev = {};
        for (var i = 0; i < elements.length; i++) prev[elements[i].label] = true;
        env.set('toolBusy', true);
        postInput('(' + fmtW(wx) + ',' + fmtW(wy) + ')', function (ok) {
          env.set('toolBusy', false);
          if (!ok) { resetTool(); }
          else {
            // 状态可能在异步回调期间被整体替换（app.js: elements = d.elements）→ 必须晚读，
            // 否则用的是函数入口捕获的旧数组，新点永远找不到（曾导致图片工具第二步失效）
            var elsNow = env.get('elements');
            for (var j = 0; j < elsNow.length; j++) {
              if (elsNow[j].kind === 'point' && !prev[elsNow[j].label]) { cb(elsNow[j].label); return; }
            }
            // 极快点击（down→up 无间隔）时元素列表可能尚未合并到本地：图片工具不能因此丢掉
            // 已选好的图片，否则用户需要重新选文件；其余工具仍走完整重置。
            if (env.get('activeTool') === 'image' && env.get('pendingImage')) {
              env.set('toolSel', []);
              updateToolButtons();
              setToolStatus();
            } else {
              resetTool();
            }
          }
          // 处理排队的下一次点击
          if (toolPointQueue.length) {
            var nx = toolPointQueue.shift();
            toolPointAt(nx[0], nx[1], nx[2]);
          }
        });
      }

      var hitObject = env.hitObject;   // 由 app.js 注入（属于其他模块）

      var finishPolygon = env.finishPolygon;   // 由 app.js 注入（属于其他模块）

      var finishPolyline = env.finishPolyline;   // 由 app.js 注入（属于其他模块）

      function widgetHit(sx, sy) {
        // 命中交互控件（按钮/复选框/输入框；滑动条由 app.js 的 sliderAt 处理）
        var wmap = env.get('widgetBoxes');
        if (!wmap) return null;
        for (var k in wmap) {
          if (!Object.prototype.hasOwnProperty.call(wmap, k)) continue;
          var b = wmap[k];
          if (!b || b.kind === 'slider') continue;
          if (sx < b.x0 - 2 || sx > b.x1 + 2 || sy < b.y0 - 2 || sy > b.y1 + 2) continue;
          var els = env.get('elements');
          for (var i = 0; i < els.length; i++) if (els[i].label === k) return els[i];
        }
        return null;
      }

      function widgetAct(label) {
        // 控件动作：按钮跑脚本 / 复选框切显示 / 输入框改数值
        var els = env.get('elements'), el = null;
        for (var i = 0; i < els.length; i++) if (els[i].label === label) { el = els[i]; break; }
        if (!el) return false;
        var lang = env.get('lang');
        if (el.kind === 'button') {
          var lines = String(el.script || '').split(/[\n;]+/);
          (function runNext(idx) {
            while (idx < lines.length && !lines[idx].trim()) idx++;
            if (idx >= lines.length) { resetTool(); return; }
            postInput(lines[idx].trim(), function () { runNext(idx + 1); });
          })(0);
          return true;
        }
        if (el.kind === 'checkbox') {
          var tgt = null;
          for (var j = 0; j < els.length; j++) if (els[j].label === el.target) { tgt = els[j]; break; }
          var curVis = !tgt || tgt.visible === undefined || tgt.visible === null ? true : !!tgt.visible;
          postInput('SetVisible[' + el.target + ', ' + (curVis ? 'false' : 'true') + ']',
                    function () { render(); });
          return true;
        }
        if (el.kind === 'inputbox') {
          var cur = '';
          for (var m = 0; m < els.length; m++) if (els[m].label === el.target) { cur = els[m].value != null ? els[m].value : ''; break; }
          var v = prompt((lang === 'en' ? 'Value for ' : '输入 ') + el.target + ':', String(cur).replace(/^= /, ''));
          if (v === null) return true;
          postInput('SetValue[' + el.target + ', ' + v + ']', function () { render(); });
          return true;
        }
        return false;
      }

      function widgetClick(sx, sy) {          // 兼容：命中即动作
        var el = widgetHit(sx, sy);
        return el ? widgetAct(el.label) : false;
      }

      function toolCanvasClick(sx, sy) {
        var CHART_TOOL_CMD = env.get('CHART_TOOL_CMD'), activeTool = env.get('activeTool'), canvas = env.get('canvas'), cssH = env.get('cssH'), cssW = env.get('cssW'), lang = env.get('lang'), shiftKeyPressed = env.get('shiftKeyPressed'), snapOn = env.get('snapOn'), toolSel = env.get('toolSel'), view = env.get('view');
        if (activeTool === 'point') {
          toolPointAt(sx, sy, function () { resetTool(); });
          return;
        }
        if (activeTool === 'segment' || activeTool === 'circle') {
          toolPointAt(sx, sy, function (lbl) {
            toolSel.push(lbl);
            if (toolSel.length === 2) {
              var cmd = activeTool === 'segment'
                ? 'Segment[' + toolSel[0] + ',' + toolSel[1] + ']'
                : 'Circle[' + toolSel[0] + ',' + toolSel[1] + ']';
              postInput(cmd, function (ok) { if (ok) resetTool(); });
            } else setToolStatus();
          });
          return;
        }
        if (activeTool === 'midpoint') {
          // 点击线段 → 一步创建线段中点；否则收集两个点
          var segHit = hitObject(sx, sy, ['segment']);
          if (segHit) {
            postInput('Midpoint[' + segHit + ']', function (ok) { if (ok) resetTool(); });
            return;
          }
          var ml = hitObject(sx, sy, ['point']);
          if (!ml) { setMsg(lang === 'en' ? 'Click a point or segment' : '请点击点或线段', true); return; }
          toolSel.push(ml);
          if (toolSel.length === 2) {
            postInput('Midpoint[' + toolSel.join(',') + ']', function (ok) { if (ok) resetTool(); });
          } else setToolStatus();
          return;
        }
        if (activeTool === 'dist') {
          // 点击线段 → 求其长度；否则收集 点+点/线/圆 → Distance
          var dseg = hitObject(sx, sy, ['segment']);
          if (dseg) { postInput('Length[' + dseg + ']', function (ok) { if (ok) resetTool(); }); return; }
          var dpt = hitObject(sx, sy, ['point']);
          if (!dpt) { setMsg(lang === 'en' ? 'Click a point or segment' : '请点击点或线段', true); return; }
          if (toolSel.length === 0) { toolSel.push(dpt); setToolStatus(); return; }
          var dO2 = hitObject(sx, sy, ['point', 'line', 'segment', 'ray', 'circle']);
          if (!dO2) { setMsg(lang === 'en' ? 'Click a point, line or circle' : '请点击点/直线/圆', true); return; }
          postInput('Distance[' + toolSel[0] + ',' + dO2 + ']', function (ok) { if (ok) resetTool(); });
          return;
        }
        if (activeTool === 'slope') {
          var slL = hitObject(sx, sy, ['line', 'segment', 'ray']);
          if (!slL) { setMsg(lang === 'en' ? 'Click a line/segment/ray' : '请点击直线/线段/射线', true); return; }
          postInput('Slope[' + slL + ']', function (ok) { if (ok) resetTool(); });
          return;
        }
        if (activeTool === 'button' || activeTool === 'checkbox' || activeTool === 'inputbox') {
          // 交互控件工具：按钮/复选框/输入框（说明与脚本用对话框输入）
          var wpx = wxp(sx).toFixed(3), wpy = wyp(sy).toFixed(3), posStr = '(' + wpx + ',' + wpy + ')';
          if (activeTool === 'button') {
            var capB = prompt(lang === 'en' ? 'Button caption:' : '按钮说明：', lang === 'en' ? 'Run' : '执行');
            if (capB === null) { resetTool(); return; }
            var scB = prompt(lang === 'en' ? 'Script (separate commands with ;):' : '命令脚本（多条用 ; 分隔）：', 'A=(1,1)');
            if (scB === null) { resetTool(); return; }
            postInput('Button["' + capB.replace(/"/g, "'") + '","' + scB.replace(/"/g, "'") + '",' + posStr + ']',
                      function (ok) { if (ok) resetTool(); });
            return;
          }
          var wHit = hitObject(sx, sy);
          if (!wHit) {
            setMsg(lang === 'en' ? 'Click the object to bind' : '请点击要绑定的对象', true);
            return;
          }
          if (activeTool === 'checkbox') {
            var capC = prompt(lang === 'en' ? 'Check box caption:' : '复选框说明：', wHit);
            if (capC === null) { resetTool(); return; }
            postInput('CheckBox["' + capC.replace(/"/g, "'") + '",' + wHit + ',' + posStr + ']',
                      function (ok) { if (ok) resetTool(); });
            return;
          }
          postInput('InputBox[' + wHit + ',' + posStr + ']', function (ok) { if (ok) resetTool(); });
          return;
        }
        if (activeTool === 'angle') {
          toolCollectPoints(3, function (s) { return 'Angle[' + s.join(',') + ']'; }, sx, sy);
          return;
        }
        if (activeTool === 'area' || activeTool === 'perimeter') {
          var kindsA = activeTool === 'area' ? ['polygon', 'circle', 'conic'] : ['polygon', 'circle'];
          var aHit = hitObject(sx, sy, kindsA);
          if (!aHit) { setMsg(lang === 'en' ? 'Click a polygon/circle' : '请点击多边形或圆', true); return; }
          var acmd = activeTool === 'area' ? 'Area[' : 'Perimeter[';
          postInput(acmd + aHit + ']', function (ok) { if (ok) resetTool(); });
          return;
        }
        // 视图工具：放大/缩小/复位（不创建对象）
        if (activeTool === 'zoomin' || activeTool === 'zoomout' || activeTool === 'home') {
          if (activeTool === 'home') {
            view.xmin = -8; view.xmax = 8; view.ymin = -8; view.ymax = 8; env.set('scale', 60);
          } else {
            var zf = activeTool === 'zoomin' ? 1.3 : 1 / 1.3;
            var zwx = wxp(sx), zwy = wyp(sy);
            env.get('scale') *= zf;
            env.set('scale', Math.max(2, Math.min(200000, env.get('scale'))));
            view.xmin = zwx - sx / env.get('scale');
            view.xmax = view.xmin + cssW / env.get('scale');
            view.ymin = zwy - (cssH - sy) / env.get('scale');
            view.ymax = view.ymin + cssH / env.get('scale');
          }
          render();
          clearTimeout(canvas._zw);
          canvas._zw = setTimeout(loadState, 180);
          resetTool();
          return;
        }
        if (activeTool === 'perp' || activeTool === 'parallel') {
          if (toolSel.length === 0) {
            var ll = hitObject(sx, sy, ['line', 'segment', 'ray']);
            if (!ll) { setMsg(lang === 'en' ? 'Click a line or segment' : '请点击直线或线段', true); return; }
            toolSel.push(ll);
            setToolStatus();
            return;
          }
          toolPointAt(sx, sy, function (ptLbl) {
            var cmd = activeTool === 'perp'
              ? 'PerpendicularLine[' + ptLbl + ',' + toolSel[0] + ']'
              : 'Line[' + ptLbl + ',' + toolSel[0] + ']';
            postInput(cmd, function (ok) { if (ok) resetTool(); });
          });
          return;
        }
        if (activeTool === 'tangent') {
          if (toolSel.length === 0) {
            var cl = hitObject(sx, sy, ['circle', 'conic', 'line', 'segment', 'arc', 'function']);
            if (!cl) { setMsg(lang === 'en' ? 'Click a circle or curve' : '请点击圆或曲线', true); return; }
            toolSel.push(cl);
            setToolStatus();
            return;
          }
          toolPointAt(sx, sy, function (ptLbl) {
            postInput('Tangent[' + toolSel[0] + ',' + ptLbl + ']', function (ok) { if (ok) resetTool(); });
          });
          return;
        }
        if (activeTool === 'polygon' || activeTool === 'rigidpolygon') {
          var firstLbl = toolSel.length ? toolSel[0] : null;
          // 宽容差命中第一个顶点 → 自动闭合（已选 ≥2 点；18px 屏幕半径，方便回到起点收口）
          if (firstLbl && toolSel.length >= 2) {
            // 与预览/建点一致：吸附开启时先修正点击落点（网格吸附可能远离鼠标原始位置）
            var plx = wxp(sx), ply = wyp(sy);
            if (snapOn || shiftKeyPressed) {
              var plsn = snapPoint(plx, ply, niceStep(), sx, sy);
              plx = plsn[0]; ply = plsn[1];
            }
            for (var fpi = 0; fpi < env.get('elements').length; fpi++) {
              var fpel = env.get('elements')[fpi];
              if (fpel.label !== firstLbl || fpel.kind !== 'point') continue;
              var fdx = (fpel.x - plx) * env.get('scale'), fdy = (fpel.y - ply) * env.get('scale');
              if (fdx * fdx + fdy * fdy <= 18 * 18) { finishPolygon(); return; }
              break;
            }
          }
          var hitLbl = hitAnyPoint(sx, sy);
          // 点击已选中的其他顶点 → 忽略（提示回起点闭合）
          if (hitLbl && toolSel.indexOf(hitLbl) !== -1) {
            setMsg(lang === 'en' ? 'Click the first point to close' : '点击第一个点闭合多边形', true);
            return;
          }
          toolPointAt(sx, sy, function (lbl) {
            if (toolSel.indexOf(lbl) !== -1) {
              setMsg(lang === 'en' ? 'Click the first point to close' : '点击第一个点闭合多边形', true);
              return;
            }
            toolSel.push(lbl);
            updateToolButtons();
            setToolStatus();
          });
          return;
        }
        // 通用多点收集工具（直线/半圆/圆弧/椭圆/双曲线）
        function toolCollectPoints(n, makeCmd, sx2, sy2) {
          toolPointAt(sx2, sy2, function (lbl) {
            toolSel.push(lbl);
            if (toolSel.length >= n) {
              var cmd = makeCmd(toolSel);
              postInput(cmd, function (ok) { if (ok) resetTool(); });
            } else setToolStatus();
          });
        }
        if (activeTool === 'conic5') {
          // 五点圆锥曲线：前 4 点击点，第 5 击落点（过程中虚线预览随鼠标变化）
          toolCollectPoints(5, function (s) { return 'Conic[' + s.join(',') + ']'; }, sx, sy);
          return;
        }
        if (activeTool === 'ray' || activeTool === 'vector' || activeTool === 'perpbis') {
          if (activeTool === 'perpbis' && toolSel.length === 0) {
            var sl = hitObject(sx, sy, ['segment', 'line', 'ray']);
            if (sl) { postInput('PerpendicularBisector[' + sl + ']', function (ok) { if (ok) resetTool(); }); return; }
          }
          toolCollectPoints(2, function (s) {
            if (activeTool === 'ray') return 'Ray[' + s.join(',') + ']';
            if (activeTool === 'vector') return 'Vector[' + s.join(',') + ']';
            return 'PerpendicularBisector[' + s.join(',') + ']';
          }, sx, sy);
          return;
        }
        if (activeTool === 'anglebis') {
          toolCollectPoints(3, function (s) { return 'AngleBisector[' + s.join(',') + ']'; }, sx, sy);
          return;
        }
        if (activeTool === 'regpoly') {
          toolPointAt(sx, sy, function (lbl) {
            toolSel.push(lbl);
            if (toolSel.length >= 2) {
              var nTxt = prompt(lang === 'en' ? 'Number of sides (3-100):' : '边数（3-100）：');
              if (nTxt === null || !nTxt.trim()) { resetTool(); return; }
              var nv = parseInt(nTxt, 10);
              if (!nv || nv < 3 || nv > 100) { setMsg(lang === 'en' ? 'Sides must be 3-100' : '边数需在 3~100', true); resetTool(); return; }
              postInput('RegularPolygon[' + toolSel.join(',') + ',' + nv + ']', function (ok) { if (ok) resetTool(); });
            } else setToolStatus();
          });
          return;
        }
        var TRANS_KINDS = ['point', 'segment', 'ray', 'circle', 'polygon', 'line', 'polyline', 'vector', 'conic'];
        if (activeTool === 'foot') {
          if (toolSel.length === 0) {
            toolPointAt(sx, sy, function (l) { toolSel.push(l); setToolStatus(); });
            return;
          }
          var fl = hitObject(sx, sy, ['line', 'segment', 'ray']);
          if (!fl) { setMsg(lang === 'en' ? 'Click a line/segment/ray' : '请点击直线/线段/射线', true); return; }
          postInput('Foot[' + toolSel[0] + ',' + fl + ']', function (ok) { if (ok) resetTool(); });
          return;
        }
        if (activeTool === 'incenter' || activeTool === 'centroid' || activeTool === 'incircle') {
          var poly = hitObject(sx, sy, ['polygon']);
          if (!poly) { setMsg(lang === 'en' ? 'Click a triangle polygon' : '请点击三角形多边形', true); return; }
          var ccmd = activeTool === 'incenter' ? 'Incenter[' + poly + ']'
            : activeTool === 'centroid' ? 'Centroid[' + poly + ']' : 'Incircle[' + poly + ']';
          postInput(ccmd, function (ok) { if (ok) resetTool(); });
          return;
        }
        if (activeTool === 'reflect') {
          if (toolSel.length === 0) {
            var ro = hitObject(sx, sy, TRANS_KINDS);
            if (!ro) { setMsg(lang === 'en' ? 'Click object to reflect' : '请点击要反射的对象', true); return; }
            toolSel.push(ro); setToolStatus(); return;
          }
          var axis = hitObject(sx, sy, ['line', 'segment', 'ray']);
          var center = hitAnyPoint(sx, sy);
          var mirror = axis || center;
          if (!mirror) { setMsg(lang === 'en' ? 'Click axis line or center point' : '请点击轴对称线或中心点', true); return; }
          postInput('Reflect[' + toolSel[0] + ',' + mirror + ']', function (ok) { if (ok) resetTool(); });
          return;
        }
        if (activeTool === 'rotate') {
          if (toolSel.length === 0) {
            var rlo = hitObject(sx, sy, TRANS_KINDS);
            if (!rlo) { setMsg(lang === 'en' ? 'Click object to rotate' : '请点击要旋转的对象', true); return; }
            toolSel.push(rlo); setToolStatus(); return;
          }
          toolPointAt(sx, sy, function (c) {
            var angTxt = prompt(lang === 'en' ? 'Rotation angle (degrees):' : '旋转角度（度）：');
            if (angTxt === null || angTxt.trim() === '') { resetTool(); return; }
            var av = parseFloat(angTxt);
            if (isNaN(av)) { setMsg(lang === 'en' ? 'Enter a number' : '请输入数字角度', true); resetTool(); return; }
            postInput('Rotate[' + toolSel[0] + ',' + av + ',' + c + ']', function (ok) { if (ok) resetTool(); });
          });
          return;
        }
        if (activeTool === 'translate') {
          if (toolSel.length === 0) {
            var tlo = hitObject(sx, sy, TRANS_KINDS);
            if (!tlo) { setMsg(lang === 'en' ? 'Click object to translate' : '请点击要平移的对象', true); return; }
            toolSel.push(tlo); setToolStatus(); return;
          }
          if (toolSel.length === 1) {
            // 优先：点击已有向量对象 → 直接平移
            var vHit = hitObject(sx, sy, ['vector']);
            if (vHit) {
              postInput('Translate[' + toolSel[0] + ',' + vHit + ']', function (ok) { if (ok) resetTool(); });
              return;
            }
            toolPointAt(sx, sy, function (p1) { toolSel.push(p1); setToolStatus(); });
            return;
          }
          toolPointAt(sx, sy, function (p2) {
            var p1 = toolSel[1], e1 = null, e2 = null;
            for (var ti = 0; ti < env.get('elements').length; ti++) {
              if (env.get('elements')[ti].label === p1 && env.get('elements')[ti].kind === 'point') e1 = env.get('elements')[ti];
              if (env.get('elements')[ti].label === p2 && env.get('elements')[ti].kind === 'point') e2 = env.get('elements')[ti];
            }
            if (!e1 || !e2) { resetTool(); return; }
            var tdx = e2.x - e1.x, tdy = e2.y - e1.y;
            postInput('Translate[' + toolSel[0] + ',(' + fmtW(tdx) + ',' + fmtW(tdy) + ')]', function (ok) { if (ok) resetTool(); });
          });
          return;
        }
        if (activeTool === 'dilate') {
          if (toolSel.length === 0) {
            var dlo = hitObject(sx, sy, TRANS_KINDS);
            if (!dlo) { setMsg(lang === 'en' ? 'Click object' : '请点击要位似的对象', true); return; }
            toolSel.push(dlo); setToolStatus(); return;
          }
          toolPointAt(sx, sy, function (c) {
            var kTxt = prompt(lang === 'en' ? 'Dilation ratio (k):' : '位似比例 k：');
            if (kTxt === null || kTxt.trim() === '') { resetTool(); return; }
            var kv = parseFloat(kTxt);
            if (isNaN(kv)) { setMsg(lang === 'en' ? 'Enter a number' : '请输入数字比例', true); resetTool(); return; }
            postInput('Dilate[' + toolSel[0] + ',' + kv + ',' + c + ']', function (ok) { if (ok) resetTool(); });
          });
          return;
        }
        if (activeTool === 'image') {
          if (!env.get('pendingImage')) { setMsg(lang === 'en' ? 'Choose an image file first' : '请先选择图片文件', true); cancelTool(); return; }
          toolPointAt(sx, sy, function (lbl) {
            toolSel.push(lbl);
            if (toolSel.length < 2) { updateToolButtons(); setToolStatus(); return; }
            var aLbl = toolSel[0], bLbl = toolSel[1];
            if (aLbl === bLbl) { setMsg(lang === 'en' ? 'Base points must differ' : '两个基点不能相同', true); return; }
            postInput('Image[' + aLbl + ',' + bLbl + ',' + env.get('pendingImage').id + ']', function () {
              env.set('pendingImage', null);
              cancelTool();   // 插入一张后结束工具（再插入需重新选文件）
            });
          });
          return;
        }
        if (activeTool === 'invert') {
          if (toolSel.length === 0) {
            var invObj = hitObject(sx, sy, ['point', 'line', 'segment', 'ray', 'circle', 'polygon', 'polyline', 'arc', 'vector', 'conic', 'function', 'parametric', 'polar', 'implicit', 'locus']);
            if (!invObj) { setMsg(lang === 'en' ? 'Click an object to invert' : '请点击要反演的对象', true); return; }
            toolSel.push(invObj); setToolStatus(); return;
          }
          var invC = hitObject(sx, sy, ['circle']);
          if (!invC) { setMsg(lang === 'en' ? 'Click the inversion circle' : '请点击反演圆', true); return; }
          postInput('Invert[' + toolSel[0] + ',' + invC + ']', function (ok) { if (ok) resetTool(); });
          return;
        }
        if (activeTool === 'pointoncircle') {
          var pc = hitObject(sx, sy, ['circle']);
          if (!pc) { setMsg(lang === 'en' ? 'Click a circle' : '请点击圆', true); return; }
          postInput('PointOnCircle[' + pc + ']', function (ok) { if (ok) resetTool(); });
          return;
        }
        if (activeTool === 'function') {
          var fTxt = prompt(lang === 'en' ? 'Function expression (e.g. x^2+1, sin(x)):' : '函数表达式（如 x^2+1、sin(x)）：');
          if (fTxt === null || !fTxt.trim()) { resetTool(); return; }
          fTxt = fTxt.trim();
          // 带完整定义（f(x)=...）则原样，否则补 (x)=expr 自动命名
          var fcmd = /^\s*[A-Za-z_][A-Za-z0-9_]*\s*\([^)]*\)\s*=/.test(fTxt) ? fTxt : '(x)=' + fTxt;
          postInput(fcmd, function (ok) { if (ok) resetTool(); });
          return;
        }
        if (activeTool === 'slider') {
          var sTxt = prompt(lang === 'en' ? 'min,max,step (e.g. 0,10,0.5):' : '最小值,最大值,增量（如 0,10,0.5）：', '0,10,0.1');
          if (sTxt === null || !sTxt.trim()) { resetTool(); return; }
          var sp = sTxt.split(','), slo = parseFloat(sp[0]), shi = parseFloat(sp[1] || '10'), sstep = parseFloat(sp[2]);
          if (isNaN(slo) || isNaN(shi) || shi <= slo) { setMsg(lang === 'en' ? 'Invalid min/max' : '无效的最小/最大值', true); resetTool(); return; }
          var scmd = 'Slider[' + slo + ',' + shi;
          if (!isNaN(sstep) && sstep > 0) scmd += ',' + sstep;
          scmd += ',(' + wxp(sx).toFixed(3) + ',' + wyp(sy).toFixed(3) + ')]';
          postInput(scmd, function (ok) { if (ok) resetTool(); });
          return;
        }
        if (activeTool === 'locus') {
          if (toolSel.length === 0) {
            var lq = hitAnyPoint(sx, sy);
            if (!lq) { setMsg(lang === 'en' ? 'Click driven point' : '请点击被驱动点（轨迹点）', true); return; }
            toolSel.push(lq); setToolStatus(); return;
          }
          var lp = hitAnyPoint(sx, sy);
          if (!lp) { setMsg(lang === 'en' ? 'Click driver point' : '请点击驱动点（圆上点）', true); return; }
          postInput('Locus[' + toolSel[0] + ',' + lp + ']', function (ok) { if (ok) resetTool(); });
          return;
        }
        if (CHART_TOOL_CMD[activeTool] || activeTool === 'histogram' || activeTool === 'scatterplot' ||
            activeTool === 'scatterplot3d' || activeTool === 'surfacechart3d') {
          chartToolPrompt(activeTool);
          return;
        }
        if (activeTool === 'ineq') {
          var iTxt = prompt(lang === 'en' ? 'Inequality (e.g. y<x^2, x^2+y^2<4):' : '不等式（如 y<x^2、x^2+y^2<4）：');
          if (iTxt === null || !iTxt.trim()) { resetTool(); return; }
          postInput(iTxt.trim(), function (ok) { if (ok) resetTool(); });
          return;
        }
        if (activeTool === 'compass') {
          toolPointAt(sx, sy, function (c) {
            var rTxt = prompt(lang === 'en' ? 'Radius length:' : '半径长度：', '3');
            if (rTxt === null || rTxt.trim() === '') { resetTool(); return; }
            var rv = parseFloat(rTxt);
            if (isNaN(rv) || rv <= 0) { setMsg(lang === 'en' ? 'Enter a positive radius' : '请输入正数半径', true); resetTool(); return; }
            postInput('Circle[' + c + ',' + rv + ']', function (ok) { if (ok) resetTool(); });
          });
          return;
        }
        if (activeTool === 'pointonpath') {
          var popObj = hitObject(sx, sy, ['line', 'segment', 'ray', 'circle', 'polygon', 'arc']);
          if (!popObj) { setMsg(lang === 'en' ? 'Click a line/segment/ray/circle/polygon/arc' : '请点击线/线段/射线/圆/多边形/圆弧', true); return; }
          postInput('PointOnPath[' + popObj + ']', function (ok) { if (ok) resetTool(); });
          return;
        }
        if (activeTool === 'polyline') {
          var plFirst = toolSel.length ? toolSel[0] : null;
          // 宽容差命中起点 → 完成折线（18px；与预览一致：吸附开启时按吸附后落点判定）
          if (plFirst && toolSel.length >= 2) {
            var plwx = wxp(sx), plwy = wyp(sy);
            if (snapOn || shiftKeyPressed) {
              var plsp = snapPoint(plwx, plwy, niceStep(), sx, sy);
              plwx = plsp[0]; plwy = plsp[1];
            }
            for (var pli2 = 0; pli2 < env.get('elements').length; pli2++) {
              var pfel = env.get('elements')[pli2];
              if (pfel.label !== plFirst || pfel.kind !== 'point') continue;
              var pdx = (pfel.x - plwx) * env.get('scale'), pdy = (pfel.y - plwy) * env.get('scale');
              if (pdx * pdx + pdy * pdy <= 18 * 18) { finishPolyline(); return; }
              break;
            }
          }
          var plHit = hitAnyPoint(sx, sy);
          // 点击已选中的其他顶点 → 提示回起点
          if (plHit && toolSel.indexOf(plHit) !== -1) {
            setMsg(lang === 'en' ? 'Click the first point to finish' : '点击第一个点完成折线', true);
            return;
          }
          // 点击已选中的其他顶点 → 提示回起点
          if (plHit && toolSel.indexOf(plHit) !== -1) {
            setMsg(lang === 'en' ? 'Click the first point to finish' : '点击第一个点完成折线', true);
            return;
          }
          toolPointAt(sx, sy, function (l) {
            if (toolSel.indexOf(l) !== -1) {
              setMsg(lang === 'en' ? 'Click the first point to finish' : '点击第一个点完成折线', true);
              return;
            }
            toolSel.push(l);
            updateToolButtons();
            setToolStatus();
          });
          return;
        }
        if (activeTool === 'circumcircle') {
          // 直接点击三角形（内部/边）→ 一步得到外接圆；否则收集三点
          var ccPoly = hitObject(sx, sy, ['polygon']);
          if (ccPoly) {
            postInput('Circumcircle[' + ccPoly + ']', function (ok) { if (ok) resetTool(); });
            return;
          }
          toolCollectPoints(3, function (s) { return 'Circumcircle[' + s.join(',') + ']'; }, sx, sy);
          return;
        }
        if (activeTool === 'line' || activeTool === 'semicircle') {
          toolCollectPoints(2, function (s) {
            return (activeTool === 'line' ? 'Line[' : 'Semicircle[') + s.join(',') + ']';
          }, sx, sy);
          return;
        }
        if (activeTool === 'arc' || activeTool === 'sector') {
          // 点击顺序：圆心,起点,终点（arc→Arc[起点,终点,圆心]；sector→Sector[起点,终点,圆心]）
          var seCmd = activeTool === 'arc' ? 'Arc' : 'Sector';
          toolCollectPoints(3, function (s) { return seCmd + '[' + s[1] + ',' + s[2] + ',' + s[0] + ']'; }, sx, sy);
          return;
        }
        if (activeTool === 'ellipse' || activeTool === 'hyperbola') {
          toolCollectPoints(3, function (s) {
            return (activeTool === 'ellipse' ? 'Ellipse[' : 'Hyperbola[') + s.join(',') + ']';
          }, sx, sy);
          return;
        }
        if (activeTool === 'parabola') {
          if (toolSel.length === 0) {
            toolPointAt(sx, sy, function (fLbl) {
              toolSel.push(fLbl);
              setToolStatus();
            });
            return;
          }
          var dLbl = hitObject(sx, sy, ['line', 'segment', 'ray']);
          if (!dLbl) { setMsg(lang === 'en' ? 'Click the directrix (line/segment)' : '请点击准线（直线/线段）', true); return; }
          postInput('Parabola[' + toolSel[0] + ',' + dLbl + ']', function (ok) { if (ok) resetTool(); });
          return;
        }
        if (activeTool === 'intersect') {
          var ixKinds = ['line', 'segment', 'ray', 'circle', 'conic', 'function', 'parametric', 'polar', 'implicit'];
          if (toolSel.length === 0) {
            var o1 = hitObject(sx, sy, ixKinds);
            if (!o1) { setMsg(lang === 'en' ? 'Click a line/circle/curve/function' : '请点击线/圆/曲线/函数等对象', true); return; }
            toolSel.push(o1);
            setToolStatus();
            return;
          }
          var o2 = hitObject(sx, sy, ixKinds);
          if (!o2) { setMsg(lang === 'en' ? 'Click the second object' : '请点击第二个对象', true); return; }
          createIntersections(toolSel[0], o2);
          return;
        }
        // 循环创建全部交点（Intersect[o1,o2,1..N]，直到新元素带 error 或无新元素）
        function createIntersections(a, b) {
          var k = 1;
          (function next() {
            var prev = {};
            for (var i = 0; i < env.get('elements').length; i++) prev[env.get('elements')[i].label] = true;
            api('POST', '/api/input', {
              text: 'Intersect[' + a + ',' + b + ',' + k + ']',
              xmin: view.xmin, xmax: view.xmax, ymin: view.ymin, ymax: view.ymax
            }, function (d) {
              if (!d) { resetTool(); return; }
              if (d.elements) { env.set('elements', d.elements); render(); }
              var bad = false;
              for (var j = 0; j < env.get('elements').length; j++) {
                if (!prev[env.get('elements')[j].label] && env.get('elements')[j].error) bad = true;
              }
              if (bad || !d.ok) { resetTool(); return; }
              k++;
              next();
            });
          })();
        }
        if (activeTool === 'text') {
          toolPointAt(sx, sy, function (posLbl) {
            var content = prompt(lang === 'en' ? 'Text content:' : '文本内容：');
            if (content === null || !content.trim()) { resetTool(); return; }
            postInput('Text["' + content.replace(/"/g, "'") + '",' + posLbl + ']', function (ok) { if (ok) resetTool(); });
          });
        }
      }

    return {
      viewParams: viewParams,
      chartDataPrompt: chartDataPrompt,
      resetTool: resetTool,
      snapHitLabel: snapHitLabel,
      toolPointAt: toolPointAt,
      toolCanvasClick: toolCanvasClick,
      widgetClick: widgetClick,
      widgetHit: widgetHit,
      widgetAct: widgetAct,
    };
  }

  return { create: create };
})();
