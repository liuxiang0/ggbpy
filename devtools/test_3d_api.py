"""ggbpy 3D 检测矩阵 —— API 层。

对运行中的 ggbpy 服务发 HTTP 请求，逐格校验 /api/state3d 的 3D 数据契约：
  A 服务与版本探针          B 各类 3D 对象的 state3d schema
  C 3D 点 z / 度量语义       D 错误传播（HTTP 200 + error 字段，不 500）
  E 生命周期（clear/undo/redo/shift dz）   F .ggb 导出警告与 .ggk 载入

用法:
  python3 -B devtools/test_3d_api.py [--base http://127.0.0.1:8091]
  GGBPY_BASE=http://127.0.0.1:8091 python3 -B devtools/test_3d_api.py
退出码: 0 全通过 / 1 有失败 / 2 服务不可用或代码过旧。
"""

import json
import math
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, ".")

BASE = os.environ.get("GGBPY_BASE", "http://127.0.0.1:8090")
if "--base" in sys.argv:
    BASE = sys.argv[sys.argv.index("--base") + 1]
VERBOSE = "-v" in sys.argv
FAILS = []
COUNT = [0]


def section(title):
    print("\n=== " + title + " ===")


def check(name, cond, detail=""):
    COUNT[0] += 1
    if cond:
        if VERBOSE:
            print("  PASS " + name + ("  " + detail if detail else ""))
    else:
        FAILS.append(name)
        print("  FAIL " + name + ("  " + detail if detail else ""))


def http(path, body=None, method=None, timeout=15):
    url = BASE + path
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, dict(r.headers), raw
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()
    except Exception as e:
        return 0, {}, ("连接失败: %s（%s）" % (e, BASE)).encode()


def jget(path):
    st, _h, raw = http(path)
    try:
        return st, json.loads(raw.decode("utf-8"))
    except Exception:
        return st, None


def jpost(path, body):
    st, _h, raw = http(path, body)
    try:
        return st, json.loads(raw.decode("utf-8"))
    except Exception:
        return st, None


def clear():
    http("/api/clear", {}, method="POST")


def put(text):
    return jpost("/api/input", {"text": text})


def state3d():
    st, d = jget("/api/state3d")
    return (d or {}).get("elements", [])


def find(els, label):
    for e in els:
        if e.get("label") == label:
            return e
    return None


def close(a, b, eps=1e-9):
    return abs(a - b) < eps


# ---------------------------------------------------------------------------
section("A. 服务与版本探针")
st, _h, raw = http("/")
check("服务可达 " + BASE, st == 200, "HTTP %s" % st)
check("返回 ggbpy 前端", b"ggbpy" in raw, raw[:80].decode("utf-8", "replace"))
if st != 200:
    print("\n服务不可用：请先启动（cd ggbpy && PORT=%s ./run.sh）" % (BASE.rsplit(":", 1)[-1]))
    sys.exit(2)
clear()
put("O=(0,0,0)")
put("Cc=Circle[O,2]")
put("probe=Cone[Cc,3]")
els = state3d()
probe = find(els, "probe")
if probe is None or "solid" not in probe:
    print("\n该服务未加载本轮 3D 检测所需的新代码（/api/state3d 缺 solid 字段）。")
    print("请重启服务或改用新实例：PORT=8091 ./run.sh")
    sys.exit(2)
check("state3d 暴露 solid 字段", probe.get("solid") == "cone", str(probe.get("solid")))

# ---------------------------------------------------------------------------
section("B. 各类 3D 对象的 state3d schema")
clear()
SETUP = [
    "O=(0,0,0)", "A3=(1,2,3)", "B3=(4,5,6)", "cc=Circle[O,2]",
    "sg=Segment[A3,B3]", "ln=Line[A3,B3]", "pl=Plane[O,(1,0,0),(0,1,0)]",
    "sp=Sphere[O,2]", "cu=Cube[O,(2,0,0)]", "co=Cone[cc,3]", "cy=Cylinder[cc,3]",
    "sec=Intersect[pl,cu]", "spc=Intersect[sp,pl]",
    "pr=Prism[O,(2,0,0),(0,2,0)]", "py=Pyramid[O,(2,0,0),(0,2,0)]",
    "te=Tetrahedron[O,(2,0,0),(0,2,0)]", "oc=Octahedron[O,(2,0,0),(0,2,0)]",
    "he=Hexahedron[O,(2,0,0),(0,2,0)]", "ic=Icosahedron[O,(2,0,0),(0,2,0)]",
    "do=Dodecahedron[O,(2,0,0),(0,2,0)]",
]
ok_all = True
for t in SETUP:
    st1, r1 = put(t)
    if not (r1 or {}).get("ok", False) and not t.startswith(("sg=", "ln=")):
        ok_all = False
        check("API 创建 " + t, False, json.dumps(r1, ensure_ascii=False)[:120])
check("全部 3D 用例已创建", ok_all)
els = state3d()
check("state3d 元素数 = 20", len(els) == 20, str(len(els)))

tbl = [
    # label, kind, objtype, solid, 必需 data 键
    ("A3", "point", None, None, ["x", "y", "z"]),
    ("sg", "geo3d", "segment", "segment", ["x1", "y1", "z1", "x2", "y2", "z2"]),
    ("ln", "geo3d", "line3d", "line3d", ["x1", "y1", "z1", "x2", "y2", "z2"]),
    ("pl", "geo3d", "plane", "plane", ["a", "b", "c", "d"]),
    ("sp", "geo3d", "sphere", "sphere", ["cx", "cy", "cz", "r"]),
    ("cu", "geo3d", "cube", "cube", ["verts", "faces", "edges"]),
    ("co", "geo3d", "polyhedron", "cone", ["verts", "faces", "edges"]),
    ("cy", "geo3d", "polyhedron", "cylinder", ["verts", "faces", "edges"]),
    ("pr", "geo3d", "polyhedron", "prism", ["verts", "faces", "edges"]),
    ("py", "geo3d", "polyhedron", "pyramid", ["verts", "faces", "edges"]),
    ("te", "geo3d", "polyhedron", "tetrahedron", ["verts", "faces", "edges"]),
    ("oc", "geo3d", "polyhedron", "octahedron", ["verts", "faces", "edges"]),
    ("he", "geo3d", "polyhedron", "hexahedron", ["verts", "faces", "edges"]),
    ("ic", "geo3d", "polyhedron", "icosahedron", ["verts", "faces", "edges"]),
    ("do", "geo3d", "polyhedron", "dodecahedron", ["verts", "faces", "edges"]),
    ("sec", "geo3d", "section", None, ["pts", "normal", "count"]),
    ("spc", "geo3d", "circle3d", None, ["cx", "cy", "cz", "r", "normal", "u", "v"]),
]
for lbl, kind, objtype, solid, keys in tbl:
    e = find(els, lbl)
    good = e is not None and e.get("kind") == kind
    detail = "" if e is None else "%s/%s/%s" % (e.get("kind"), e.get("objtype"), e.get("solid"))
    if objtype is not None:
        good = good and e.get("objtype") == objtype
    if solid is not None:
        good = good and e.get("solid") == solid
    check("schema " + lbl, good, detail)
    if e is None:
        continue
    pool = e if kind == "point" else (e.get("data") or {})
    missing = [k for k in keys if k not in pool]
    check("字段 " + lbl, not missing, "缺 " + str(missing))
    if "verts" in keys:
        d = e["data"]
        check("网格 " + lbl, len(d["verts"]) > 0 and len(d["faces"]) > 0 and len(d["edges"]) > 0,
              "%d/%d/%d" % (len(d["verts"]), len(d["faces"]), len(d["edges"])))
        bad = [i for f in d["faces"] for i in f if not (0 <= i < len(d["verts"]))]
        check("面索引 " + lbl, not bad, str(bad[:5]))

# ---------------------------------------------------------------------------
section("C. 3D 点 z / 度量语义（透过 API）")
clear()
for t in ["O=(0,0,0)", "A3=(1,2,3)", "B3=(4,5,6)", "P=(1,2)", "Q=(4,5)",
          "T=Translate[A3,(3,3,3)]", "R=Rotate[A3,90,O]",
          "d3=Distance[A3,B3]", "d2=Distance[P,Q]", "an3=Angle[A3,B3,O]"]:
    put(t)
els = state3d()
check("Translate 3D 点 z=6", close((find(els, "T") or {}).get("z", 0), 6.0), str((find(els, "T") or {}).get("z")))
check("Rotate 3D 点 z=3", close((find(els, "R") or {}).get("z", 0), 3.0), str((find(els, "R") or {}).get("z")))
st, d = jget("/api/state")
vals = {e.get("label"): e.get("value") for e in (d or {}).get("elements", [])}
check("API 3D 距离=√27", "5.196152" in str(vals.get("d3")), str(vals.get("d3")))
check("API 2D 距离=√18", "4.242641" in str(vals.get("d2")), str(vals.get("d2")))
check("API 3D 夹角（9.2745°）", "9.2745" in str(vals.get("an3")), str(vals.get("an3")))

# ---------------------------------------------------------------------------
section("D. 错误传播（HTTP 200 + error 字段）")
clear()
for t in ["O=(0,0,0)", "E1=(1,0,0)", "E2=(0,1,0)",
          "bad1=Sphere[O,-1]", "bad2=Segment[O,O]", "bad3=Tetrahedron[O,O,E1]",
          "pl=Plane[O,E1,E2]", "bad4=Intersect[Plane[O,(1,0,0),(0,1,0)],E1]"]:
    put(t)
els = state3d()
for lbl in ("bad1", "bad2", "bad3"):
    e = find(els, lbl)
    check("错误元素 " + lbl + " 带 error", e is not None and e.get("error"), str(e.get("error") if e else None))
st, r = put("bad5=Sphere[O,NoSuchCmd[1]]")
check("命令级错误 HTTP 200", st == 200, "HTTP %s" % st)
check("命令级错误 ok=false + 可操作消息",
      (r or {}).get("ok") is False and "嵌套命令中不支持命令" in str((r or {}).get("message")),
      str((r or {}).get("message"))[:80])
st, r = put("bad6=Sphere[O,-1]")
els = state3d()
e6 = find(els, "bad6")
check("元素级错误 ok=true + error 字段",
      (r or {}).get("ok") is True and e6 is not None and e6.get("error"),
      str(e6.get("error") if e6 else r))

# ---------------------------------------------------------------------------
section("E. 生命周期（clear / undo / redo / shift dz）")
clear()
els = state3d()
check("clear 清空", len(els) == 0, str(len(els)))
put("A3=(1,2,3)")
put("cc=Circle[(0,0),2]")
put("co=Cone[cc,3]")
els = state3d()
check("创建 3 个对象", len(els) == 3, str(len(els)))
http("/api/undo", {}, method="POST")
els = state3d()
check("undo 移除圆锥", find(els, "co") is None and len(els) == 2, str(len(els)))
http("/api/redo", {}, method="POST")
els = state3d()
e = find(els, "co")
check("redo 恢复且 solid=cone", e is not None and e.get("solid") == "cone", str(e.get("solid") if e else None))
st, r = jpost("/api/shift", {"label": "A3", "dx": 2.0, "dy": -1.0, "dz": 3.0})
els = state3d()
a3 = find(els, "A3")
check("shift 带 dz 改 z：3→6", a3 is not None and close(a3.get("z", 0), 6.0), str(a3.get("z") if a3 else None))
check("shift 后 x/y 同步", a3 is not None and close(a3.get("x", 0), 3.0) and close(a3.get("y", 0), 1.0),
      "(%s,%s)" % (a3.get("x"), a3.get("y")))

# ---------------------------------------------------------------------------
section("F. .ggb 导出警告 / .ggk 载入")
clear()
put("A=(1,2)")
put("A3=(1,2,3)")
put("cc=Circle[(0,0),2]")
put("co=Cone[cc,3]")
st, hdrs, raw = http("/api/export/ggb")
hdr = {k.lower(): v for k, v in hdrs.items()}
check(".ggb 导出 HTTP 200", st == 200, "HTTP %s" % st)
check(".ggb 提示跳过 3D（响应头）", "x-ggb-warnings" in hdr and "x-ggb-skipped-3d" in hdr,
      str({k: v for k, v in hdr.items() if "ggb" in k})[:120])
warn = urllib.parse.unquote(hdr.get("x-ggb-warnings", ""))
check(".ggb 警告含中文提示", "不支持 3D" in warn, warn[:80])
check(".ggb 跳过 3D 元素", b'label="A3"' not in raw and b'label="co"' not in raw, "")
check(".ggb 保留 2D 元素", b'label="A"' in raw, "")
import xml.etree.ElementTree as ET  # noqa: E402
try:
    ET.fromstring(raw.decode("utf-8"))
    check(".ggb XML 合法", True)
except Exception as e:
    check(".ggb XML 合法", False, str(e))

# .ggk 载入（用内核本地生成含 3D 的 .ggk，再以纯文本 body POST /api/load）
from kernel.construction import Construction  # noqa: E402
tmp = Construction()
for t in ["O=(0,0,0)", "cc=Circle[O,2]", "co=Cone[cc,3]", "A3=(1,2,3)"]:
    tmp.process(t)
req = urllib.request.Request(BASE + "/api/load", data=tmp.save_json().encode("utf-8"),
                             headers={"Content-Type": "text/plain"}, method="POST")
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        r = json.loads(resp.read().decode("utf-8"))
        st = resp.status
except Exception as e:
    st, r = 0, {"ok": False, "message": str(e)}
check(".ggk 载入 HTTP 200", st == 200, "HTTP %s" % st)
els = state3d()
check(".ggk 载入后 3D 元素齐全", find(els, "co") is not None and find(els, "A3") is not None, str(len(els)))
e = find(els, "co")
check(".ggk 载入后 solid 保留", e is not None and e.get("solid") == "cone", str(e.get("solid") if e else None))
check(".ggk 载入后 z 保留", close((find(els, "A3") or {}).get("z", 0), 3.0), str((find(els, "A3") or {}).get("z")))

# ---------------------------------------------------------------------------
section("G. 功能验收：嵌套命令 / Volume·Area / 3D 求交截面")
clear()
for t in ["O=(0,0,0)", "c=Circle[O,2]", "pl=Plane[O,(1,0,0),(0,1,0)]",
          "cu=Cube[O,(2,0,0)]", "sp=Sphere[O,2]", "ln=Line[(1,2,3),(4,5,6)]",
          "k=Cone[Circle[O,2],3]", "V=Volume[k]", "A=Area[sp]",
          "sec=Intersect[pl,cu]", "ix=Intersect[ln,pl]"]:
    put(t)
els = state3d()
k = find(els, "k")
check("嵌套命令经 API 生效（solid=cone / 49 顶点）",
      k is not None and k.get("solid") == "cone" and len((k.get("data") or {}).get("verts", [])) == 49,
      "%s/%s" % (k.get("solid") if k else None, len((k.get("data") or {}).get("verts", [])) if k else None))
sec = find(els, "sec")
check("平面×立体 → section 元素", sec is not None and sec.get("objtype") == "section"
      and (sec.get("data") or {}).get("count", 0) >= 3,
      "%s/%s" % (sec.get("objtype") if sec else None, (sec.get("data") or {}).get("count") if sec else None))
ix = find(els, "ix")
check("直线×面 → 带 z 的交点", ix is not None and ix.get("kind") == "point" and abs(ix.get("z", 0)) < 1e-9,
      "z=%s" % (ix.get("z") if ix else None))
st, d = jget("/api/state")
vals = {e.get("label"): e.get("value") for e in (d or {}).get("elements", [])}
check("API Volume[Cone[Circle[O,2],3]] = 4π", "12.566371" in str(vals.get("V")), str(vals.get("V")))
check("API Area[Sphere[O,2]] = 16π", "50.265482" in str(vals.get("A")), str(vals.get("A")))
# 第四批：面×球（3D 圆）/ 体×体 / 截面周长
for t in ["Q1=(1,1,1)", "Q2=(3,1,1)", "cu2=Cube[Q1,Q2]", "cap=Intersect[cu,cu2]",
          "capV=Volume[cap]", "spc=Intersect[sp,pl]", "secP=Perimeter[sec]"]:
    put(t)
els = state3d()
cap = find(els, "cap")
check("体×体 → 凸多面体 8/6/12",
      cap is not None and (len((cap.get("data") or {}).get("verts", [])),
                           len((cap.get("data") or {}).get("faces", [])),
                           len((cap.get("data") or {}).get("edges", []))) == (8, 6, 12),
      str([len((cap.get("data") or {}).get(k, [])) for k in ("verts", "faces", "edges")]) if cap else None)
spc = find(els, "spc")
check("面×球 → circle3d r=2", spc is not None and spc.get("objtype") == "circle3d"
      and abs((spc.get("data") or {}).get("r", 0) - 2.0) < 1e-9,
      "%s/%s" % (spc.get("objtype") if spc else None, (spc.get("data") or {}).get("r") if spc else None))
st, d = jget("/api/state")
vals = {e.get("label"): e.get("value") for e in (d or {}).get("elements", [])}
import re as _re  # noqa: E402
_m = _re.search(r"-?\d+(?:\.\d+)?", str(vals.get("capV")))
check("API Volume[立方体交] = 1", _m is not None and abs(float(_m.group(0)) - 1.0) < 1e-9,
      str(vals.get("capV")))
check("API Perimeter[截面] = 8", "8" in str(vals.get("secP")), str(vals.get("secP")))

# ---------------------------------------------------------------------------
section("H. 第五批：球×球 / 空间圆求交 / 样式快照（undo/redo 保留 wire·locked）")
clear()
for t in ["O=(0,0,0)", "A=(2,0,0)", "c=Circle[O,2]", "co=Cone[c,3]",
          "s1=Sphere[O,2]", "s2=Sphere[A,2]"]:
    put(t)
put("sc=Intersect[s1,s2]")
els = state3d()
sc = find(els, "sc")
check("球×球 → circle3d（r=√3）", sc is not None and sc.get("objtype") == "circle3d"
      and abs((sc.get("data") or {}).get("r", 0) - 3 ** 0.5) < 1e-9,
      "%s/%s" % (sc.get("objtype") if sc else None, (sc.get("data") or {}).get("r") if sc else None))
put("sp=Sphere[O,1.4]")
put("pz=Plane[(0,0,1),(1,0,1),(0,1,1)]")
put("cc=Intersect[sp,pz]")
put("px=Plane[(0.5,0,0),(0.5,1,0),(0.5,0,1)]")
put("cp=Intersect[cc,px]")
els = state3d()
cp = find(els, "cp")
check("空间圆×平面 → 交点", cp is not None and cp.get("kind") == "point"
      and abs(cp.get("x", 0) - 0.5) < 1e-9, "(%s,%s,%s)" % (cp.get("x"), cp.get("y"), cp.get("z")) if cp else None)
# 样式：SetWire/SetLocked → undo → redo 后仍保留
put("SetWire[co,true]")
put("SetLocked[co,true]")
put("trigger=Sphere[O,1]")
http("/api/undo", {}, method="POST")
els = state3d()
co = find(els, "co")
check("API undo 后 wire 保留", co is not None and co.get("wire") is True, str(co.get("wire") if co else None))
check("API undo 后 locked 保留", co is not None and co.get("locked") is True, str(co.get("locked") if co else None))
http("/api/redo", {}, method="POST")
els = state3d()
co = find(els, "co")
check("API redo 后 wire/locked 保留",
      co is not None and co.get("wire") is True and co.get("locked") is True,
      "%s/%s" % (co.get("wire") if co else None, co.get("locked") if co else None))

# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print("3D API 检测矩阵 @ %s：%d 项断言，%d 失败" % (BASE, COUNT[0], len(FAILS)))
for f in FAILS:
    print("  FAILED: " + f)
print("结果:", "ALL PASS" if not FAILS else "FAILED")
sys.exit(0 if not FAILS else 1)
