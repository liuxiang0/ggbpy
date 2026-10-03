/* ggbpy 对象/工具面板渲染（P2 前端拆分：从 app.js 抽出）。
 *
 * 用法（app.js）：
 *   var _panels = GGB_PANELS.create({
 *     get: function (k) { return <应用状态>; },     // 只读访问（elements/listEl/selected/…）
 *     set: function (k, v) { <应用状态> = v; },     // 仅 activeCat 需要
 *   });
 *   之后 17 个同名函数由 app.js 保留薄包装，调用点无需改动。
 *
 * 依赖极简：只读应用状态（17 个变量）+ 无任何组外函数依赖（已由耦合分析确认）。
 */
window.GGB_PANELS = (function () {
  'use strict';

  function create(env) {
      function t(key) {
        var I18N = env.get('I18N'), lang = env.get('lang');
        var d = I18N[lang] || I18N.zh;
        var v = d;
        var parts = key.split('.');
        for (var i = 0; i < parts.length; i++) {
          v = v ? v[parts[i]] : undefined;
        }
        return v !== undefined ? v : key;
      }

      function esc(s) {
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
      }

      function fmtNum(v) {
        var a = Math.abs(v);
        if (a >= 100000 || (a < 0.001 && a > 0)) return v.toExponential(1);
        if (a >= 100) return v.toFixed(0);
        if (a >= 1) return v.toFixed(1);
        return v.toFixed(2);
      }

      function findEl(label) {
        var elements = env.get('elements');
        for (var i = 0; i < elements.length; i++) {
          if (elements[i].label === label) return elements[i];
        }
        return null;
      }

      function findEl3d(label) {
        var els3d = env.get('els3d');
        for (var i = 0; i < els3d.length; i++) if (els3d[i].label === label) return els3d[i];
        return null;
      }

      function solidLabelName(e) {
        if (!e) return '3D';
        if (e.solid) {
          var nm = t('solid.' + e.solid);
          return nm !== ('solid.' + e.solid) ? nm : e.solid;
        }
        return e.objtype || '3D';
      }

      function applyLang() {
        var lang = env.get('lang');
        var nodes = document.querySelectorAll('[data-i18n]');
        for (var i = 0; i < nodes.length; i++) {
          nodes[i].textContent = t(nodes[i].getAttribute('data-i18n'));
        }
        var phs = document.querySelectorAll('[data-i18n-ph]');
        for (var j = 0; j < phs.length; j++) {
          phs[j].setAttribute('placeholder', t(phs[j].getAttribute('data-i18n-ph')));
        }
        var tts = document.querySelectorAll('[data-i18n-title]');
        for (var k2 = 0; k2 < tts.length; k2++) {
          tts[k2].setAttribute('title', t(tts[k2].getAttribute('data-i18n-title')));
        }
        document.documentElement.lang = lang;
      }

      function renderList() {
        var elements = env.get('elements'), lang = env.get('lang'), listCursor = env.get('listCursor'), listEl = env.get('listEl'), playState = env.get('playState'), selected = env.get('selected'), selectedMulti = env.get('selectedMulti');
        var s = '';
        if (!elements.length) {
          listEl.innerHTML = '<div class="obj-empty">' + (lang === 'en' ? 'No objects yet — type a command above (e.g. A=(1,2), Circle[A,B], f(x)=x^2)' : '暂无对象 — 在上方输入命令创建（如 A=(1,2)、Circle[A,B]、f(x)=x^2）') + '</div>';
          return;
        }
        for (var i = 0; i < elements.length; i++) {
          var e = elements[i];
          var selCls = (selected === e.label || selectedMulti.indexOf(e.label) !== -1) ? ' sel' : '';
          if (i === listCursor) selCls += ' cur';      // 键盘光标行
          if (e.visible === false) selCls += ' hid';   // 隐藏对象灰显
          s += '<div class="obj' + selCls + '" data-label="' + e.label + '"><span class="dh" draggable="true" title="' + (lang === 'en' ? 'Drag to reorder (drawing order)' : '拖拽调整叠放顺序') + '">⠿</span>';
          var kdName = e.kind === 'conic' ? t('kind.conic_' + (e.ctype || 'general')) : t('kind.' + e.kind);
          if (e.semicircle) kdName = t('kind.semicircle');
          if (e.visible === false) kdName += '(隐藏)';
          s += '<span class="lb">' + e.label + '</span><span class="kd">' + kdName + '</span>';
          if (e.kind === 'number' && e.min !== undefined && e.min !== null) {
            var pbSym = (playState && playState.label === e.label) ? '⏸' : '▶';
            s += '<button class="pb" data-pb="' + e.label + '">' + pbSym + '</button>';
            s += '<input type="range" class="slider" data-label="' + e.label + '" min="' + e.min + '" max="' + e.max + '" step="' + e.step + '" value="' + e.val + '">';
          } else if (e.value) s += '<span class="vl">' + esc(e.value) + '</span>';
          s += '<span class="df">' + esc(e.defn) + '</span>';
          if (e.error) s += '<span class="er">⚠ ' + esc(e.error) + '</span>';
          s += '</div>';
        }
        listEl.innerHTML = s;
      }

      function renderList3d() {
        var els3d = env.get('els3d'), lang = env.get('lang'), listCursor = env.get('listCursor'), listEl = env.get('listEl'), mode3d = env.get('mode3d'), selected3d = env.get('selected3d');
        if (!mode3d) return;
        var s = '';
        if (!els3d.length) {
          listEl.innerHTML = '<div class="obj-empty">' + (lang === 'en' ? 'No 3D objects yet — switch to 3D view and use tools or type e.g. A=(1,2,3)' : '暂无 3D 对象 — 用上方 3D 工具或输入 A=(1,2,3)') + '</div>';
          return;
        }
        for (var i = 0; i < els3d.length; i++) {
          var e = els3d[i];
          var selCls = (selected3d === e.label) ? ' sel' : '';
          if (i === listCursor) selCls += ' cur';
          var kindName = e.kind === 'point' ? t('kind.point') : solidLabelName(e);
          var defnTxt = e.defn || (e.label + '=' + solidLabelName(e));
          if (e.visible === false) selCls += ' hid';   // 隐藏对象灰显
          s += '<div class="obj' + selCls + '" data-label="' + e.label + '">'
            + '<span class="dh" draggable="true" title="' + (lang === 'en' ? 'Drag to reorder (drawing order)' : '拖拽调整叠放顺序') + '">⠿</span>'
            + '<span class="lb">' + esc(e.label) + '</span><span class="kd">' + esc(kindName) + '</span>'
            + (e.visible === false ? '<span class="kd">(隐藏)</span>' : '')
            + '<span class="df">' + esc(defnTxt) + '</span></div>';
        }
        listEl.innerHTML = s;
      }

      function renderToolsPanel() {
        var TOOL_CATS = env.get('TOOL_CATS'), lang = env.get('lang');
        var grid = document.getElementById('tools-grid');
        var html = '';
        for (var ci = 0; ci < TOOL_CATS.length; ci++) {
          var cat = TOOL_CATS[ci];
          html += '<div class="tool-cat">';
          html += '<div class="tool-cat-title"><img src="/static/toolsicon/' + cat.icon + '" alt=""><span>' + (lang === 'en' ? cat.en : cat.zh) + '</span></div>';
          html += '<div class="tool-cat-tools">';
          for (var ti = 0; ti < cat.tools.length; ti++) {
            var key = cat.tools[ti];
            html += '<button class="tool-btn" data-tool="' + key + '" title="' + t('tool_' + key) + '">' + t('tool_' + key) + '</button>';
          }
          if (!cat.tools.length) html += '<span class="tool-cat-empty">' + (lang === 'en' ? '(in toolbar)' : '(在工具栏)') + '</span>';
          html += '</div></div>';
        }
        // 完成按钮（多边形/折线）追加到末尾
        html += '<button id="tool-done" class="eb-del" data-i18n="tool_done" style="display:none">✓ 完成</button>';
        grid.innerHTML = html;
        applyLang();
      }

      function renderCas(cells) {
        var casCellsEl = env.get('casCellsEl'), lang = env.get('lang');
        var s = '';
        for (var i = 0; i < cells.length; i++) {
          var c = cells[i];
          s += '<div class="cas-cell">';
          s += '<div class="cas-in"><span class="cid" data-ref="' + c.id + '" title="' + (lang === 'en' ? 'Click to reference' : '点击引用该结果') + '">#' + c.id + '</span>' + esc(c.input) + '</div>';
          if (c.error) s += '<div class="cas-err">' + esc(c.error) + '</div>';
          else if (c.output) s += '<div class="cas-out">= ' + esc(c.output) + '</div>';
          s += '</div>';
        }
        casCellsEl.innerHTML = s;
        casCellsEl.scrollTop = casCellsEl.scrollHeight;
      }

      function renderCatbar() {
        var TOOL_CATS = env.get('TOOL_CATS'), lang = env.get('lang');
        var bar = document.getElementById('catbar');
        var html = '';
        for (var ci = 0; ci < TOOL_CATS.length; ci++) {
          var cat = TOOL_CATS[ci];
          html += '<button class="cat-icon" data-cat="' + cat.id + '" title="' + (lang === 'en' ? cat.en : cat.zh) + '">'
            + '<img src="/static/toolsicon/' + cat.icon + '" alt="">' + (lang === 'en' ? cat.en : cat.zh) + '</button>';
        }
        bar.innerHTML = html;
      }

      function showCat(id) {
        var TOOL_CATS = env.get('TOOL_CATS');
        env.set('activeCat', id);
        var cat = null;
        for (var i = 0; i < TOOL_CATS.length; i++) if (TOOL_CATS[i].id === id) cat = TOOL_CATS[i];
        if (!cat) return;
        var box = document.getElementById('cat-tools');
        var html = '';
        for (var ti = 0; ti < cat.tools.length; ti++) {
          var key = cat.tools[ti];
          html += '<button class="tool-btn" data-tool="' + key + '" title="' + t('tool_' + key) + '">' + t('tool_' + key) + '</button>';
        }
        if (cat.tools.indexOf('polygon') !== -1 || cat.tools.indexOf('polyline') !== -1) {
          html += '<button id="tool-done" class="eb-del" data-i18n="tool_done" style="display:none">✓ 完成</button>';
        }
        box.innerHTML = html;
        applyLang();
        // 高亮当前类
        var icons = document.querySelectorAll('.cat-icon');
        for (var ii = 0; ii < icons.length; ii++) icons[ii].classList.toggle('active', icons[ii].getAttribute('data-cat') === id);
        box.style.display = cat.tools.length ? 'block' : 'none';
        // 激活工具时更新完成按钮
        updateToolButtons();
      }

      function populateEditBar() {
        var selected = env.get('selected'), selectedMulti = env.get('selectedMulti');
        var bar = document.getElementById('editbar');
        if (selectedMulti.length > 1) {
          bar.style.display = 'flex';
          document.getElementById('eb-label').textContent = selectedMulti.length + ' 个对象';
          document.getElementById('eb-kind').textContent = '';
          return;
        }
        var el = selected ? findEl(selected) : null;
        if (!el) { bar.style.display = 'none'; return; }
        bar.style.display = 'flex';
        document.getElementById('eb-label').textContent = el.label;
        document.getElementById('eb-kind').textContent = t('kind.' + el.kind);
        document.getElementById('eb-vis').checked = el.visible !== false;
        document.getElementById('eb-lock').checked = el.locked === true;
        var wireWrap2d = document.getElementById('eb-wire-wrap');
        if (wireWrap2d) wireWrap2d.style.display = 'none';   // 线框仅 3D 物体
        var defnIn = document.getElementById('eb-defn');
        if (document.activeElement !== defnIn) defnIn.value = el.defn;
      }

      function populateEditBar3d() {
        var selected3d = env.get('selected3d');
        var bar = document.getElementById('editbar');
        var el = selected3d ? findEl3d(selected3d) : null;
        if (!el) { bar.style.display = 'none'; return; }
        bar.style.display = 'flex';
        document.getElementById('eb-label').textContent = el.label;
        document.getElementById('eb-kind').textContent = el.objtype || '3D';
        document.getElementById('eb-vis').checked = el.visible !== false;
        document.getElementById('eb-lock').checked = el.locked === true;
        // 线框仅 3D 物体可切换（点/线段不适用）
        var wireWrap = document.getElementById('eb-wire-wrap');
        var wireIn = document.getElementById('eb-wire');
        if (wireWrap && wireIn) {
          var isSolid = el.kind === 'geo3d' && (el.objtype === 'cube' || el.objtype === 'polyhedron' || el.objtype === 'sphere' || el.objtype === 'plane');
          wireWrap.style.display = isSolid ? 'inline-block' : 'none';
          wireIn.checked = el.wire === true;
        }
        // 3D 点：显示 x/y/z 数值输入（改值回车/失焦即更新）
        var xyzWrap = document.getElementById('eb-xyz-wrap');
        if (xyzWrap) {
          var isPt3d = el.kind === 'point';
          xyzWrap.style.display = isPt3d ? 'inline-block' : 'none';
          if (isPt3d) {
            var xi = document.getElementById('eb-xyz-x');
            var yi = document.getElementById('eb-xyz-y');
            var zi = document.getElementById('eb-xyz-z');
            if (document.activeElement !== xi) xi.value = fmtNum(el.x);
            if (document.activeElement !== yi) yi.value = fmtNum(el.y);
            if (document.activeElement !== zi) zi.value = fmtNum(el.z != null ? el.z : 0);
          }
        }
        var defnIn = document.getElementById('eb-defn');
        if (document.activeElement !== defnIn) defnIn.value = el.defn;
      }

      function updateToolButtons() {
        var activeTool = env.get('activeTool'), toolSel = env.get('toolSel');
        var btns = document.querySelectorAll('#cat-tools .tool-btn[data-tool], #tools-panel .tool-btn[data-tool]');
        for (var i = 0; i < btns.length; i++) {
          btns[i].classList.toggle('active', btns[i].getAttribute('data-tool') === activeTool);
        }
        var doneShown = (((activeTool === 'polygon' || activeTool === 'rigidpolygon') && toolSel.length >= 3) || (activeTool === 'polyline' && toolSel.length >= 2));
        var dones = document.querySelectorAll('#tool-done');
        for (var di = 0; di < dones.length; di++) dones[di].style.display = doneShown ? 'block' : 'none';
      }

      function updateToolButtons3d() {
        var tool3d = env.get('tool3d');
        var btns = document.querySelectorAll('#cat-tools .tool-btn');
        for (var i = 0; i < btns.length; i++) {
          var on = btns[i].getAttribute('data-tool') === tool3d;
          btns[i].classList.toggle('active', on);
          if (on && tool3d === 'pt3d') btns[i].style.display = 'inline-block';
        }
      }

    return {
      t: t,
      esc: esc,
      fmtNum: fmtNum,
      findEl: findEl,
      findEl3d: findEl3d,
      solidLabelName: solidLabelName,
      applyLang: applyLang,
      renderList: renderList,
      renderList3d: renderList3d,
      renderToolsPanel: renderToolsPanel,
      renderCas: renderCas,
      renderCatbar: renderCatbar,
      showCat: showCat,
      populateEditBar: populateEditBar,
      populateEditBar3d: populateEditBar3d,
      updateToolButtons: updateToolButtons,
      updateToolButtons3d: updateToolButtons3d,
    };
  }

  return { create: create };
})();
