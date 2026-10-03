/* ggbpy 虚拟数学键盘面板（P2 前端 panels 拆分：从 app.js 抽出）。
 *
 * 面板按钮的 HTML 仍在 index.html（#mathkb，49 个 .kb-key，data-k 表示按键值）；
 * 本模块只负责行为，由 app.js 调用 GGB_KB.init() 装配，避免 app.js 继续膨胀。
 *
 * 行为：点工具栏 ⌨ 展开/收起；按键插入到「当前输入框」（#cas-cmd 优先，否则 #cmd）；
 *       bs 退格、clear 清空、enter 触发 Enter、其余按 data-k 原样插入。
 */
window.GGB_KB = (function () {
  'use strict';

  function create(doc) {
    var panel = doc.getElementById('mathkb');
    var button = doc.getElementById('btn-kbd');

    function target() {
      var ae = doc.activeElement;
      if (ae && ae.id === 'cas-cmd') return ae;
      return doc.getElementById('cmd');
    }

    function notify(el) {
      el.dispatchEvent(new Event('input', { bubbles: true }));
    }

    function insert(txt) {
      var el = target();
      el.focus();
      var st = el.selectionStart || el.value.length;
      var en = el.selectionEnd || el.value.length;
      el.value = el.value.slice(0, st) + txt + el.value.slice(en);
      var pos = st + txt.length;
      if (el.setSelectionRange) el.setSelectionRange(pos, pos);
      notify(el);
    }

    function backspace() {
      var el = target();
      el.focus();
      var st = el.selectionStart || el.value.length;
      var en = el.selectionEnd || el.value.length;
      if (st === en && st > 0) st = st - 1;
      el.value = el.value.slice(0, st) + el.value.slice(en);
      if (el.setSelectionRange) el.setSelectionRange(st, st);
      notify(el);
    }

    function clear() {
      var el = target();
      el.focus();
      el.value = '';
      if (el.setSelectionRange) el.setSelectionRange(0, 0);
      notify(el);
    }

    function enter() {
      var el = target();
      el.focus();
      el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    }

    function isOpen() {
      return !!panel && panel.style.display !== 'none';
    }

    function setOpen(show) {
      if (!panel) return;
      panel.style.display = show ? 'block' : 'none';
      if (button) button.classList.toggle('active', !!show);
      if (show) target().focus();
    }

    function onKey(name) {
      if (name === 'bs') backspace();
      else if (name === 'clear') clear();
      else if (name === 'enter') enter();
      else if (name === 'pi') insert('pi');
      else insert(name);
    }

    function init() {
      if (button && panel) {
        button.addEventListener('click', function () { setOpen(!isOpen()); });
      }
      if (panel) {
        panel.addEventListener('pointerdown', function (ev) {
          ev.preventDefault();                      // 保持输入框焦点
          var b = ev.target.closest ? ev.target.closest('button.kb-key') : null;
          if (!b) return;
          onKey(b.getAttribute('data-k'));
        });
      }
      return api;
    }

    var api = {
      init: init, insert: insert, backspace: backspace, clear: clear, enter: enter,
      target: target, isOpen: isOpen, setOpen: setOpen, onKey: onKey,
    };
    return api;
  }

  return {
    init: function (opts) {
      var doc = (opts && opts.document) || window.document;
      var api = create(doc).init();
      window.__ggbpyKb = api;                       // 检测/诊断用
      return api;
    },
    create: create,
  };
})();
