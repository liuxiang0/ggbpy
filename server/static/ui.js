/* ggbpy 界面弹窗与提示（帮助弹窗等，P2 前端拆分）（P2 前端拆分：从 app.js 抽出）。
 *
 * 用法（app.js）：
 *   var _ui = GGB_UI.create({ get: _stateGet, esc: esc, renderCas: renderCas, translateMsg: translateMsg });
 *   之后同名函数由 app.js 保留薄包装，调用点无需改动。
 *
 * 状态：CAS_COMMANDS, casOpen, casPanel, lang
 */
window.GGB_UI = (function () {
  'use strict';

  function create(env) {
      var api = env.api;   // 由 app.js 注入（属于其他模块）

      var updateUndoBtns = env.updateUndoBtns;   // 由 app.js 注入（属于其他模块）

      var esc = env.esc;   // 由 app.js 注入（属于其他模块）

      var renderCas = env.renderCas;   // 由 app.js 注入（属于其他模块）

      var translateMsg = env.translateMsg;   // 由 app.js 注入（属于其他模块）

      var setMsg = env.setMsg;   // 由 app.js 注入（属于其他模块）

      var casInsert = env.casInsert;   // 由 app.js 注入（属于其他模块）

      function showHelpModal(commands, display, sigs) {
        var CAS_COMMANDS = env.get('CAS_COMMANDS'), casPanel = env.get('casPanel'), lang = env.get('lang');
        var ex = document.getElementById('help-pop');
        if (!ex) {
          ex = document.createElement('div');
          ex.id = 'help-pop';
          document.getElementById('app').appendChild(ex);
        }
        var head = lang === 'en' ? ('Commands (' + commands.length + ')') : ('可用命令（共 ' + commands.length + ' 条）');
        // PageUp/PageDown 翻页（弹窗内滚动；右下角亦可拖拽调整大小）
        if (ex._pgKey) document.removeEventListener('keydown', ex._pgKey);
        ex._pgKey = function (kev) {
          if (kev.key !== 'PageDown' && kev.key !== 'PageUp') return;
          var body = document.querySelector('#help-pop .help-body');
          if (!body) return;
          kev.preventDefault();
          body.scrollTop += (kev.key === 'PageDown' ? 1 : -1) * Math.max(80, body.clientHeight - 40);
        };
        document.addEventListener('keydown', ex._pgKey);
        var casChips = CAS_COMMANDS.map(function (c) {
          return '<span class="hc hc-cas" data-cas="' + c.name + '" title="' + esc(c.zh) + ' / ' + esc(c.en) + '">' + c.name + '</span>';
        }).join('');
        ex.innerHTML = '<div class="help-head"><span>' + head + '</span><button id="help-close" class="x" title="' + (lang === 'en' ? 'Close' : '关闭') + '">✕</button></div>'
          + '<div class="help-search"><input id="help-search" type="text" placeholder="'
          + (lang === 'en' ? 'Filter commands (e.g. surface, volume, fit)' : '筛选命令（如 surface / volume / 拟合 / 曲面）') + '"></div>'
          + '<div class="help-body" id="help-cmds">' + commands.map(function (c) {
              var cnm = (display && display[c]) || c;
              var sig = (sigs && sigs[c]) || (cnm + '[…]');
              // 只显示**命令名**（简洁、一屏放得下）；完整参数放在 title → 鼠标悬停即见
              return '<span class="hc hc-cmd" data-cmd="' + cnm + '" title="' + esc(sig) + '">' + esc(cnm) + '</span>';
            }).join('') + '</div>'
          + '<div class="help-sec">' + (lang === 'en' ? 'CAS symbolic commands (click to use in the CAS panel)' : 'CAS 符号命令（点击可直接在 CAS 面板使用）') + '</div>'
          + '<div class="help-body">' + casChips + '</div>'
          + '<div class="help-foot">' + (lang === 'en' ? 'Click a command to insert Name[] into the input bar; CAS commands run in the CAS panel.' : '点击命令即在输入框插入 Name[]；CAS 命令在 CAS 面板执行。') + '</div>';
        var searchEl = ex.querySelector('#help-search');
        if (searchEl) {
          searchEl.addEventListener('input', function () {
            var q = searchEl.value.trim().toLowerCase();
            var chips = ex.querySelectorAll('#help-cmds .hc-cmd');
            for (var i = 0; i < chips.length; i++) {
              var nm = (chips[i].getAttribute('data-cmd') || '').toLowerCase();
              chips[i].style.display = (!q || nm.indexOf(q) !== -1) ? '' : 'none';
            }
          });
          searchEl.focus();
        }
        ex.style.display = 'block';
        ex.querySelector('#help-close').addEventListener('click', function () { ex.style.display = 'none'; });
        if (!ex._wired) {          // 弹窗会被反复打开：委托监听只绑一次，否则点一次插多次
        ex._wired = true;
        ex.addEventListener('click', function (ev) {
                  var tc = ev.target.closest ? ev.target.closest('.hc-cmd') : null;
                  if (tc) {
                    var cname = tc.getAttribute('data-cmd') || '';   // 已是规范显示名（如 SurfacePoint）
                    var inp = document.getElementById('cmd');
                    if (inp) {
                      inp.value = cname + '[]';
                      inp.focus();
                      try { inp.setSelectionRange(cname.length + 1, cname.length + 1); } catch (e) {}
                    }
                    return;
                  }
                  var t = ev.target.closest ? ev.target.closest('.hc-cas') : null;
                  if (!t) return;
                  var nm = t.getAttribute('data-cas');
                  if (!env.get('casOpen')) {
                    env.set('casOpen', true);
                    casPanel.style.display = 'flex';
                    api('GET', '/api/cas', null, function (d) { renderCas(d.cells); });
                  }
                  casInsert(nm + '[]', 1);
                });
        }
      }

    return {
      showHelpModal: showHelpModal,
    };
  }

  return { create: create };
})();
