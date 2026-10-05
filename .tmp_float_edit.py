"""行内定义编辑改为浮层：脱离列表 DOM，免疫重渲染（真实双击可稳定测试）。"""
from pathlib import Path

p = Path("server/static/app.js")
s = p.read_text(encoding="utf-8")

old = """  function startDefnEdit(df) {
    if (!df || df.querySelector('input')) return;
    var row = df.closest('.obj');
    if (!row) return;
    var label = row.getAttribute('data-label');
    var original = df.textContent;
    df.textContent = '';
    var inp = document.createElement('input');
    inp.className = 'df-edit';
    inp.value = original;
    df.appendChild(inp);
    inp.focus();
    inp.select();
    var finish = function (commit) {
      defnEdit = null;
      if (inp.parentNode !== df) return;
      var val = inp.value.trim();
      try { inp.remove(); } catch (e) {}
      df.textContent = original;
      if (commit && val && val !== original) {
        postInput('Redefine[' + label + ', ' + val + ']');
      }
    };"""
new = """  function placeDefnInput(inp, df) {
    // 浮层定位到定义式单元格上（列表重渲染不影响它，只需跟随新位置）
    var r = df.getBoundingClientRect();
    inp.style.left = Math.round(r.x) + 'px';
    inp.style.top = Math.round(r.y) + 'px';
    inp.style.width = Math.max(96, Math.round(r.width) + 24) + 'px';
    inp.style.height = Math.max(20, Math.round(r.height) + 2) + 'px';
  }

  function startDefnEdit(df) {
    if (!df || defnEdit) return;                    // 同一时刻只允许一个浮层
    var row = df.closest('.obj');
    if (!row) return;
    var label = row.getAttribute('data-label');
    var original = df.textContent;
    var inp = document.createElement('input');
    inp.className = 'df-edit';
    inp.value = original;
    inp.style.position = 'fixed';
    inp.style.zIndex = '9999';
    inp.style.background = '#fff';
    placeDefnInput(inp, df);
    document.body.appendChild(inp);                 // 挂在 body：列表重建不会销毁它
    defnEdit = { label: label, inp: inp };
    inp.focus();
    inp.select();
    var finish = function (commit) {
      if (!defnEdit) return;
      var val = inp.value.trim();
      defnEdit = null;
      try { inp.remove(); } catch (e) {}
      if (commit && val && val !== original) {
        postInput('Redefine[' + label + ', ' + val + ']');
      }
    };"""
assert s.count(old) == 1, ("start", s.count(old))
s = s.replace(old, new, 1)

old2 = """  function reopenDefnEdit() {
    if (!defnEdit) return;
    var row = listEl.querySelector('.obj[data-label="' + defnEdit.label + '"]');
    var df = row && row.querySelector('.df');
    if (df && !df.querySelector('input')) startDefnEdit(df);
  }"""
new2 = """  function reopenDefnEdit() {
    if (!defnEdit) return;
    var row = listEl.querySelector('.obj[data-label="' + defnEdit.label + '"]');
    var df = row && row.querySelector('.df');
    if (!df) { try { defnEdit.inp.remove(); } catch (e) {} defnEdit = null; return; }
    placeDefnInput(defnEdit.inp, df);               // 行重建/滚动后跟随位置
  }"""
assert s.count(old2) == 1, ("reopen", s.count(old2))
s = s.replace(old2, new2, 1)
p.write_text(s, encoding="utf-8")
print("app.js：行内定义编辑改为 body 上的浮层")
