"""双击判定改为「时间 + 位置」：不再要求第二次点击命中同一元素（重渲染会位移）。"""
from pathlib import Path

p = Path("server/static/app.js")
s = p.read_text(encoding="utf-8")
old = "  var rowClick = { label: null, t: 0 };"
assert s.count(old) == 1, ("state", s.count(old))
s = s.replace(old, "  var rowClick = { label: null, t: 0, x: 0, y: 0, df: false };   // 双击判定：目标 + 时间 + 位置", 1)

start = s.index("  listEl.addEventListener('pointerdown', function (ev) {\n    var t = ev.target;\n    var row = t && t.closest ? t.closest('.obj') : null;\n    if (!row) return;\n    var lab = row.getAttribute('data-label');")
end = s.index("  });", s.index("      rowClick.label = lab;", start)) + len("  });")
new = """  listEl.addEventListener('pointerdown', function (ev) {
    var t = ev.target;
    var row = t && t.closest ? t.closest('.obj') : null;
    if (!row) return;
    var lab = row.getAttribute('data-label');
    var isDf = !!(t.closest && t.closest('.df'));
    var rEl0 = isDf ? null : findEl(lab);
    var isWidget = !!rEl0 && (rEl0.kind === 'button' || rEl0.kind === 'checkbox' || rEl0.kind === 'inputbox');
    if (!isDf && !isWidget) return;
    var now = new Date().getTime();
    var sameSpot = Math.abs(ev.clientX - rowClick.x) <= 8 && Math.abs(ev.clientY - rowClick.y) <= 8;
    if (rowClick.label && now - rowClick.t < 450 && sameSpot) {
      // 双击：用**第一次点击时的目标**（第二次可能因选中重渲染而落到别的行/元素）
      var prev = rowClick;
      rowClick = { label: null, t: 0, x: 0, y: 0, df: false };
      ev.preventDefault();
      if (prev.df) {
        var pRow = listEl.querySelector('.obj[data-label="' + prev.label + '"]');
        var pDf = pRow && pRow.querySelector('.df');
        if (pDf) { defnEdit = { label: prev.label }; startDefnEdit(pDf); }
      } else {
        var pEl = findEl(prev.label);
        if (pEl) editWidget(pEl);
      }
      return;
    }
    rowClick = { label: lab, t: now, x: ev.clientX, y: ev.clientY, df: isDf };
  });"""
s = s[:start] + new + s[end:]
p.write_text(s, encoding="utf-8")
print("双击判定改为时间+位置（使用第一次的目标）")
