/* ggbpy 三维坐标轴与刻度绘制（P2 前端拆分：render3d 第二步）（P2 前端拆分：从 app.js 抽出）。
 *
 * 用法（app.js）：
 *   var _axes3d = GGB_AX3.create({ get: _stateGet, fmtNum: fmtNum, proj3: proj3, line3: line3 });
 *   之后同名函数由 app.js 保留薄包装，调用点无需改动。
 *
 * 状态：C, COARSE, axisTicks3d, cam, cssH, cssW, ctx3
 */
window.GGB_AX3 = (function () {
  'use strict';

  function create(env) {
      var fmtNum = env.fmtNum;   // 由 app.js 注入（属于其他模块）

      var proj3 = env.proj3;   // 由 app.js 注入（属于其他模块）

      var line3 = env.line3;   // 由 app.js 注入（属于其他模块）

      function saveAxisTicks3d() { var axisTicks3d = env.get('axisTicks3d'); try { localStorage.setItem('ggb_axisticks3d', JSON.stringify(axisTicks3d)); } catch (e) {} }

      function niceStep3d() {
        var cam = env.get('cam'), cssH = env.get('cssH'), cssW = env.get('cssW');
        var ps = Math.min(cssW, cssH) * 0.42 / cam.r;
        var target = 55 / ps;
        var pow = Math.pow(10, Math.floor(Math.log(target) / Math.LN10));
        var m = target / pow;
        var step = (m < 1.5) ? 1 : (m < 3.5) ? 2 : (m < 7.5) ? 5 : 10;
        return step * pow;
      }

      function drawAxes3d() {
        var C = env.get('C'), axisTicks3d = env.get('axisTicks3d'), ctx3 = env.get('ctx3');
        var axLen = 18;   // 轴长（世界单位，斜二测/扩大一倍）
        // 先画负半轴（淡色），再画正半轴（亮色 + 箭头）
        line3([-axLen, 0, 0], [0, 0, 0], 'rgba(225,29,72,.30)', 1);
        line3([0, -axLen, 0], [0, 0, 0], 'rgba(5,150,105,.30)', 1);
        line3([0, 0, -axLen], [0, 0, 0], 'rgba(37,99,235,.30)', 1);
        line3([0, 0, 0], [axLen, 0, 0], '#e11d48', 2.2);
        line3([0, 0, 0], [0, axLen, 0], '#059669', 2.2);
        line3([0, 0, 0], [0, 0, axLen], '#2563eb', 2.2);
        // 箭头
        arrowHead3([axLen, 0, 0], [0, 0, 0], '#e11d48');
        arrowHead3([0, axLen, 0], [0, 0, 0], '#059669');
        arrowHead3([0, 0, axLen], [0, 0, 0], '#2563eb');
        // 刻度：沿三轴画短线 + 整数标注（随 zoom 实时匹配步长）
        if (axisTicks3d.show) {
          var tstep = niceStep3d();
          var axColors = ['#e11d48', '#059669', '#2563eb'];
          // 轴方向单位向量（世界）与刻度线垂直方向（屏幕）：用小偏移保证垂直
          var axisDefs = [
            { dir: [1, 0, 0], off: [0, 0, 1], len: axLen },
            { dir: [0, 1, 0], off: [0, 0, 1], len: axLen },
            { dir: [0, 0, 1], off: [1, 0, 0], len: axLen }
          ];
          for (var ai = 0; ai < 3; ai++) {
            var ad = axisDefs[ai], dir = ad.dir, off = ad.off;
            ctx3.fillStyle = axisTicks3d.labelColor;
            ctx3.font = axisTicks3d.font;
            for (var t = Math.ceil(-ad.len / tstep) * tstep; t <= ad.len + 0.001; t += tstep) {
              if (Math.abs(t) < tstep / 2) continue;   // 跳过原点附近：三条轴交汇处不标 0（避免重叠）
              var pA = [dir[0] * t, dir[1] * t, dir[2] * t];
              var pA2 = [dir[0] * t + off[0] * axisTicks3d.tickLen * 0.06, dir[1] * t + off[1] * axisTicks3d.tickLen * 0.06, dir[2] * t + off[2] * axisTicks3d.tickLen * 0.06];
              var pr1 = proj3(pA), pr2 = proj3(pA2);
              // 刻度短线：沿屏幕方向延伸（用投影后偏移）
              var dx2 = pr2.x - pr1.x, dy2 = pr2.y - pr1.y;
              var dl = Math.hypot(dx2, dy2) || 1;
              var tl = axisTicks3d.tickLen;
              ctx3.strokeStyle = axisTicks3d.color;
              ctx3.lineWidth = 1;
              ctx3.beginPath();
              ctx3.moveTo(pr1.x, pr1.y);
              ctx3.lineTo(pr1.x - (dy2 / dl) * tl, pr1.y + (dx2 / dl) * tl);
              ctx3.stroke();
              // 整数标注（1/2/5 系步长下取整数）
              var lbl = fmtNum(t);
              ctx3.fillText(lbl, pr1.x - (dy2 / dl) * tl - 3, pr1.y + (dx2 / dl) * tl + 3);
            }
          }
        }
        // 轴标签（投影后画在箭头稍外侧；x 左移、y 下移避免与刻度/箭头重叠）
        var lx = proj3([axLen + 0.6, 0, 0]), ly = proj3([0, axLen + 0.6, 0]), lz = proj3([0, 0, axLen + 0.6]);
        ctx3.fillStyle = '#e11d48';
        ctx3.font = 'bold 15px sans-serif';
        ctx3.textAlign = 'center';
        ctx3.textBaseline = 'middle';
        ctx3.fillText('x', lx.x - 16, lx.y - 6);
        ctx3.fillStyle = '#059669';
        ctx3.fillText('y', ly.x - 4, ly.y + 18);
        ctx3.fillStyle = '#2563eb';
        ctx3.fillText('z', lz.x + 8, lz.y + 6);
        ctx3.textAlign = 'left';
        ctx3.textBaseline = 'alphabetic';
        // 原点**不标记**（三条轴交汇处保持干净）：需要 (0,0,0) 时用「吸附」或按坐标输入
        // （旧实现在此画圆点 + 字母 O，用户反馈多余 ✗ —— 第九十一批移除）
      }

      function arrowHead3(tip, base, color) {
        var COARSE = env.get('COARSE'), ctx3 = env.get('ctx3');
        var pBase = proj3(base), pTip = proj3(tip);
        var dx = pTip.x - pBase.x, dy = pTip.y - pBase.y;
        var len = Math.sqrt(dx * dx + dy * dy);
        if (len < COARSE) return;
        var ux = dx / len, uy = dy / len;   // 朝外单位方向（屏幕）
        var size = 9;
        var spread = 0.55;   // ~31.5° 半张角
        var wx = -ux, wy = -uy;              // 向后（朝 base）
        ctx3.fillStyle = color;
        ctx3.beginPath();
        ctx3.moveTo(pTip.x, pTip.y);
        ctx3.lineTo(pTip.x + (wx * Math.cos(spread) - wy * Math.sin(spread)) * size,
                    pTip.y + (wx * Math.sin(spread) + wy * Math.cos(spread)) * size);
        ctx3.lineTo(pTip.x + (wx * Math.cos(spread) + wy * Math.sin(spread)) * size,
                    pTip.y + (-wx * Math.sin(spread) + wy * Math.cos(spread)) * size);
        ctx3.closePath();
        ctx3.fill();
      }

      function drawMiniAxes3d() {
        var cssH = env.get('cssH'), ctx3 = env.get('ctx3');
        var mx = 60, my = cssH - 58;   // 左下角锚点
        var len = 34;
        // 把世界轴向量 (1,0,0)/(0,1,0)/(0,0,1) 用 proj3 的方向投影成屏幕方向（平移不变部分）
        var o = proj3([0, 0, 0]);
        var ex = proj3([1, 0, 0]), ey = proj3([0, 1, 0]), ez = proj3([0, 0, 1]);
        var ux = ex.x - o.x, uy = ex.y - o.y;
        var vx = ey.x - o.x, vy = ey.y - o.y;
        var wx2 = ez.x - o.x, wy2 = ez.y - o.y;
        // 归一化并固定长度
        var lux = Math.hypot(ux, uy) || 1, lvx = Math.hypot(vx, vy) || 1, lwx = Math.hypot(wx2, wy2) || 1;
        var ax1 = mx + ux / lux * len, ay1 = my + uy / lux * len;
        var ax2 = mx + vx / lvx * len, ay2 = my + vy / lvx * len;
        var ax3 = mx + wx2 / lwx * len, ay3 = my + wy2 / lwx * len;
        ctx3.lineWidth = 2.5;
        ctx3.strokeStyle = '#e11d48'; ctx3.beginPath(); ctx3.moveTo(mx, my); ctx3.lineTo(ax1, ay1); ctx3.stroke();
        ctx3.strokeStyle = '#059669'; ctx3.beginPath(); ctx3.moveTo(mx, my); ctx3.lineTo(ax2, ay2); ctx3.stroke();
        ctx3.strokeStyle = '#2563eb'; ctx3.beginPath(); ctx3.moveTo(mx, my); ctx3.lineTo(ax3, ay3); ctx3.stroke();
        ctx3.fillStyle = '#e11d48'; ctx3.font = 'bold 12px sans-serif';
        ctx3.fillText('x', ax1 + 4, ay1 + 4);
        ctx3.fillStyle = '#059669';
        ctx3.fillText('y', ax2 + 4, ay2 + 4);
        ctx3.fillStyle = '#2563eb';
        ctx3.fillText('z', ax3 + 4, ay3 + 4);
        // 轴交点小点
        ctx3.fillStyle = '#374151';
        ctx3.beginPath(); ctx3.arc(mx, my, 3, 0, Math.PI * 2); ctx3.fill();
      }

    return {
      fmtNum: fmtNum,
      proj3: proj3,
      line3: line3,
      saveAxisTicks3d: saveAxisTicks3d,
      niceStep3d: niceStep3d,
      drawAxes3d: drawAxes3d,
      arrowHead3: arrowHead3,
      drawMiniAxes3d: drawMiniAxes3d,
    };
  }

  return { create: create };
})();
