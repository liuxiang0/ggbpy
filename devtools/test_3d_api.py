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

import gzip
import time
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


def _num_or_none(v):
    m = _re.search(r"-?\d+(?:\.\d+)?", str(v))
    return float(m.group(0)) if m else None


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
check(".ggb 3D 往返不再警告（无跳过头）", "x-ggb-skipped-3d" not in hdr,
      str({k: v for k, v in hdr.items() if "ggb" in k})[:120])
check(".ggb 含 3D 元素（A3 带真实 z）", b'label="A3"' in raw and b'z="3" w="1"' in raw, "")
check(".ggb 含 3D 派生对象（圆锥）", b'name="Cone"' in raw, "")
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
section("I. 第六批：OBJ/STL 导出 / 球×空间圆 / 空间圆×空间圆")
clear()
for t in ["O=(0,0,0)", "cc=Circle[O,2]", "cu=Cube[O,(2,0,0)]", "co=Cone[cc,3]",
          "sp=Sphere[O,2]", "pl=Plane[O,(1,0,0),(0,1,0)]", "sec=Intersect[pl,cu]"]:
    put(t)
st, hdrs, raw = http("/api/export/obj")
hdr = {k.lower(): v for k, v in hdrs.items()}
obj_txt = raw.decode("utf-8")
check("OBJ 导出 HTTP 200", st == 200, "HTTP %s" % st)
check("OBJ 含 v/f/o 行", obj_txt.count("\nv ") > 0 and "\nf " in obj_txt and "\no " in obj_txt,
      "v=%d f=%d" % (obj_txt.count("\nv "), obj_txt.count("\nf ")))
check("OBJ 提示跳过非网格对象", "x-mesh-warnings" in hdr, str([k for k in hdr if "mesh" in k]))
st2, h2, raw2 = http("/api/export/stl")
stl_txt = raw2.decode("utf-8")
check("STL 导出 HTTP 200", st2 == 200, "HTTP %s" % st2)
check("STL 含 facet normal / solid", "facet normal" in stl_txt and stl_txt.startswith("solid "),
      stl_txt.splitlines()[0][:40] if stl_txt else "")
check("STL 三角数 = 立方体 12 + 圆锥 94", stl_txt.count("facet normal") == 106, str(stl_txt.count("facet normal")))
# 球×空间圆 / 空间圆×空间圆
put("B=(1,0,1)")
put("sp14=Sphere[O,1.4]")
put("pz1=Plane[(0,0,1),(1,0,1),(0,1,1)]")
put("cc2=Intersect[sp14,pz1]")
put("sB=Sphere[B,0.5]")
put("sc=Intersect[sB,cc2]")
put("A=(2,0,0)")
put("s2=Sphere[A,2]")
put("cA=Intersect[sp,pl]")
put("cBc=Intersect[s2,pl]")
put("qq=Intersect[cA,cBc]")
els = state3d()
sc = find(els, "sc")
qq = find(els, "qq")
r0 = (1.4 ** 2 - 1.0) ** 0.5
check("球×空间圆 → 交点 x=(r²+1−R²)/2", sc is not None and abs(sc.get("x", 0) - (r0 * r0 + 1 - 0.25) / 2) < 1e-9,
      "(%s,%s,%s)" % (sc.get("x"), sc.get("y"), sc.get("z")) if sc else None)
check("空间圆×空间圆 → 交点 (1,√3,0)", qq is not None and abs(qq.get("x", 0) - 1.0) < 1e-9
      and abs(abs(qq.get("y", 0)) - 3 ** 0.5) < 1e-9, "(%s,%s,%s)" % (qq.get("x"), qq.get("y"), qq.get("z")) if qq else None)

# ---------------------------------------------------------------------------
section("J. 第七批：曲面 / 3D 点列表与 FitPlane / OBJ 导入")
clear()
for t in ["surf=Surface[x^2+y^2,-1,1,-1,1,8]", "A_s=Area[surf]",
          "L={(0,0,1),(1,0,1.5),(0,1,0.75),(1,1,1.25)}", "fp=FitPlane[L]"]:
    put(t)
els = state3d()
surf = find(els, "surf")
check("Surface 经 API 建成（81 顶点）",
      surf is not None and len((surf.get("data") or {}).get("verts", [])) == 81
      and surf.get("solid") == "surface",
      "%s/%s" % (surf.get("solid") if surf else None,
                 len((surf.get("data") or {}).get("verts", [])) if surf else None))
fp = find(els, "fp")
check("FitPlane 经 API 得平面元素", fp is not None and fp.get("objtype") == "plane",
      "%s" % (fp.get("objtype") if fp else None))
st, d = jget("/api/state")
vals = {e.get("label"): e.get("value") for e in (d or {}).get("elements", [])}
check("API Area[曲面] > 0", "A_s" in vals and vals["A_s"] and float(str(vals["A_s"]).split()[-1]) > 0,
      str(vals.get("A_s")))
# OBJ 导入
OBJ_TEXT = """v 0 0 0
v 2 0 0
v 2 2 0
v 0 2 0
v 0 0 2
v 2 0 2
v 2 2 2
v 0 2 2
f 1 2 3 4
f 5 6 7 8
f 1 2 6 5
f 2 3 7 6
f 3 4 8 7
f 4 1 5 8
"""
st, r = None, None
req = urllib.request.Request(BASE + "/api/mesh", data=OBJ_TEXT.encode("utf-8"),
                             headers={"Content-Type": "text/plain"}, method="POST")
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        r = json.loads(resp.read().decode("utf-8")); st = resp.status
except Exception as e:
    st, r = 0, {"ok": False, "message": str(e)}
check("POST /api/mesh 返回 id 与计数",
      st == 200 and (r or {}).get("ok") and r.get("verts") == 8 and r.get("faces") == 6,
      json.dumps(r, ensure_ascii=False)[:120])
mid = (r or {}).get("id")
if mid:
    put("m=Mesh[" + mid + "]")
    put("V_m=Volume[m]")
    els = state3d()
    m = find(els, "m")
    check("Mesh[导入 id] 元素 8/6/12",
          m is not None and (len((m.get("data") or {}).get("verts", [])),
                             len((m.get("data") or {}).get("faces", [])),
                             len((m.get("data") or {}).get("edges", []))) == (8, 6, 12),
          str([len((m.get("data") or {}).get(k, [])) for k in ("verts", "faces", "edges")]) if m else None)
    st2, _h2, raw2 = http("/api/export/obj")
    check("导入网格可再次导出为 OBJ", b"v 0 0 0" in raw2 and b"o m" in raw2, "len=%d" % len(raw2))
    st3, d3 = jget("/api/state")
    v3 = {e.get("label"): e.get("value") for e in (d3 or {}).get("elements", [])}
    check("导入立方体体积 = 8", "8" in str(v3.get("V_m")), str(v3.get("V_m")))

# ---------------------------------------------------------------------------
section("K. 第八批：参数曲面 / 隐式曲面 / STL 导入")
clear()
for t in ["tor=SurfaceParam[(2+cos(s))*cos(t),(2+cos(s))*sin(t),sin(s),s,t,0,2*pi,0,2*pi,20]",
          "A_tor=Area[tor]",
          "sph=ImplicitSurface[x^2+y^2+z^2-4=0,-2.2,2.2,-2.2,2.2,-2.2,2.2,20]",
          "A_sph=Area[sph]"]:
    put(t)
els = state3d()
tor = find(els, "tor")
sph = find(els, "sph")
check("参数曲面经 API 建成（21²=441 顶点）",
      tor is not None and len((tor.get("data") or {}).get("verts", [])) == 441 and tor.get("solid") == "surface",
      "%s/%s" % (tor.get("solid") if tor else None,
                 len((tor.get("data") or {}).get("verts", [])) if tor else None))
check("隐式曲面经 API 建成（顶点 > 300）",
      sph is not None and len((sph.get("data") or {}).get("verts", [])) > 300 and sph.get("solid") == "surface",
      "%s/%s" % (sph.get("solid") if sph else None,
                 len((sph.get("data") or {}).get("verts", [])) if sph else None))
st, d = jget("/api/state")
vals = {e.get("label"): e.get("value") for e in (d or {}).get("elements", [])}
def _num(v):
    m = _re.search(r"-?\d+(?:\.\d+)?", str(v))
    return float(m.group(0)) if m else None
check("API 环面面积 ≈ 78.96（±6%）",
      _num(vals.get("A_tor")) is not None and abs(_num(vals["A_tor"]) - 78.957) / 78.957 < 0.06,
      str(vals.get("A_tor")))
check("API 球面等值面面积 ≈ 50.27（±10%）",
      _num(vals.get("A_sph")) is not None and abs(_num(vals["A_sph"]) - 50.265) / 50.265 < 0.10,
      str(vals.get("A_sph")))
# STL 导入（ASCII）
STL_TEXT = """solid tetra
  facet normal 0 0 -1
    outer loop
      vertex 0 0 0
      vertex 2 0 0
      vertex 0 2 0
    endloop
  endfacet
  facet normal 0 -1 0
    outer loop
      vertex 0 0 0
      vertex 0 0 2
      vertex 2 0 0
    endloop
  endfacet
  facet normal -1 0 0
    outer loop
      vertex 0 0 0
      vertex 0 2 0
      vertex 0 0 2
    endloop
  endfacet
  facet normal 1 1 1
    outer loop
      vertex 2 0 0
      vertex 0 0 2
      vertex 0 2 0
    endloop
  endfacet
endsolid tetra
"""
req = urllib.request.Request(BASE + "/api/mesh", data=STL_TEXT.encode("utf-8"),
                             headers={"Content-Type": "application/octet-stream"}, method="POST")
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        rst = resp.status
        rm = json.loads(resp.read().decode("utf-8"))
except Exception as e:
    rst, rm = 0, {"ok": False, "message": str(e)}
check("POST /api/mesh 识别 ASCII STL",
      rst == 200 and (rm or {}).get("ok") and rm.get("format") == "stl-ascii"
      and rm.get("verts") == 4 and rm.get("faces") == 4,
      json.dumps(rm, ensure_ascii=False)[:120])
if (rm or {}).get("id"):
    put("mSTL=Mesh[" + rm["id"] + "]")
    put("V_mSTL=Volume[mSTL]")
    els = state3d()
    m = find(els, "mSTL")
    check("STL 导入 → Mesh 元素 4/4/6",
          m is not None and (len((m.get("data") or {}).get("verts", [])),
                             len((m.get("data") or {}).get("faces", [])),
                             len((m.get("data") or {}).get("edges", []))) == (4, 4, 6),
          str([len((m.get("data") or {}).get(k, [])) for k in ("verts", "faces", "edges")]) if m else None)
    st3, d3 = jget("/api/state")
    v3 = {e.get("label"): e.get("value") for e in (d3 or {}).get("elements", [])}
    check("STL 四面体体积 = 4/3", "1.333" in str(v3.get("V_mSTL")), str(v3.get("V_mSTL")))

# ---------------------------------------------------------------------------
section("L. 第九批：3D 统计 / 球×立体交线 / glTF 导出")
clear()
for t in ["L={(0,0,0),(2,0,0),(0,2,0),(0,0,2)}", "ce=Centroid[L]", "fs=FitSphere[L]",
          "cu=Cube[(0,0,0),(2,0,0)]", "sA=Sphere[(1,1,1),1.2]", "xA=Intersect[sA,cu]"]:
    put(t)
els = state3d()
ce = find(els, "ce")
fs = find(els, "fs")
xA = find(els, "xA")
check("API Centroid 三维点列表 → (0.5,0.5,0.5)",
      ce is not None and abs(ce.get("x", 0) - 0.5) < 1e-9 and abs(ce.get("z", 0) - 0.5) < 1e-9,
      "(%s,%s,%s)" % (ce.get("x"), ce.get("y"), ce.get("z")) if ce else None)
check("API FitSphere → 球心 (1,1,1) r=√3",
      fs is not None and fs.get("objtype") == "sphere"
      and abs((fs.get("data") or {}).get("r", 0) - 3 ** 0.5) < 1e-9,
      "%s/%s" % (fs.get("objtype") if fs else None, (fs.get("data") or {}).get("r") if fs else None))
check("API 球×立体 → 交线 curve3d（段数 > 100）",
      xA is not None and xA.get("objtype") == "curve3d" and (xA.get("data") or {}).get("count", 0) > 100,
      "%s/%s" % (xA.get("objtype") if xA else None, (xA.get("data") or {}).get("count") if xA else None))
# glTF 导出
st, hdrs, raw = http("/api/export/gltf")
hdr = {k.lower(): v for k, v in hdrs.items()}
check("glTF 导出 HTTP 200", st == 200, "HTTP %s" % st)
try:
    g = json.loads(raw.decode("utf-8"))
    ok_json = g.get("asset", {}).get("version") == "2.0"
except Exception as e:
    g, ok_json = None, False
check("glTF JSON 合法（asset.version=2.0）", ok_json, (raw[:60].decode("utf-8", "replace")))
if ok_json:
    import base64 as _b64
    blob = _b64.b64decode(g["buffers"][0]["uri"].split(",")[1])
    check("glTF buffer 长度一致", len(blob) == g["buffers"][0]["byteLength"],
          "%d vs %d" % (len(blob), g["buffers"][0]["byteLength"]))
    check("glTF 至少 1 个 node/mesh + POSITION accessor",
          len(g["nodes"]) >= 1 and len(g["meshes"]) >= 1
          and any(a["type"] == "VEC3" for a in g["accessors"]),
          "%d nodes / %d accessors" % (len(g["nodes"]), len(g["accessors"])))

# ---------------------------------------------------------------------------
section("M. 第十批：点云统计 / glTF 导入 / 大网格渲染预算")
clear()
for t in ["L={(0,0,0),(2,0,0),(0,3,0),(0,0,1),(2,3,1)}", "bb=BoundingBox[L]",
          "V_bb=Volume[bb]", "cov=Covariance[L]"]:
    put(t)
els = state3d()
bb = find(els, "bb")
check("API BoundingBox → 8/6/12 网格",
      bb is not None and (len((bb.get("data") or {}).get("verts", [])),
                          len((bb.get("data") or {}).get("faces", [])),
                          len((bb.get("data") or {}).get("edges", []))) == (8, 6, 12),
      str([len((bb.get("data") or {}).get(k, [])) for k in ("verts", "faces", "edges")]) if bb else None)
st, d = jget("/api/state")
vals = {e.get("label"): e.get("value") for e in (d or {}).get("elements", [])}
check("API 包围盒体积 = 6", "6" in str(vals.get("V_bb")), str(vals.get("V_bb")))
cov_el = [e for e in (d or {}).get("elements", []) if e.get("label") == "cov"]
check("API Covariance → 3×3 矩阵元素", bool(cov_el) and cov_el[0].get("kind") == "matrix",
      cov_el[0].get("kind") if cov_el else None)
# glTF 导入（服务端嗅探）
gltf_out, _w = None, None
from kernel.mesh_io import export_gltf as _exp_gltf  # noqa: E402
req = urllib.request.Request(BASE + "/api/clear", data=b"{}",
                             headers={"Content-Type": "application/json"}, method="POST")
urllib.request.urlopen(req, timeout=10).read()
for t in ["cu=Cube[(0,0,0),(2,0,0)]"]:
    put(t)
_local = Construction()
_local.process("cu=Cube[(0,0,0),(2,0,0)]")
gltf_text, _w = _exp_gltf(_local)
req2 = urllib.request.Request(BASE + "/api/mesh", data=gltf_text.encode("utf-8"),
                              headers={"Content-Type": "application/octet-stream"}, method="POST")
try:
    with urllib.request.urlopen(req2, timeout=15) as resp:
        rst2 = resp.status
        rm2 = json.loads(resp.read().decode("utf-8"))
except Exception as e:
    rst2, rm2 = 0, {"ok": False, "message": str(e)}
check("POST /api/mesh 识别 glTF", rst2 == 200 and (rm2 or {}).get("format") == "gltf"
      and rm2.get("verts") == 8 and rm2.get("faces") == 12,
      json.dumps(rm2, ensure_ascii=False)[:110])
if (rm2 or {}).get("id"):
    put("mG=Mesh[" + rm2["id"] + "]")
    put("V_mG=Volume[mG]")
    els = state3d()
    m = find(els, "mG")
    check("glTF 导入 → Mesh 元素（12 三角面）", m is not None and len((m.get("data") or {}).get("faces", [])) == 12,
          str(len((m.get("data") or {}).get("faces", []))) if m else None)
    st3, d3 = jget("/api/state")
    v3 = {e.get("label"): e.get("value") for e in (d3 or {}).get("elements", [])}
    check("glTF 导入立方体体积 ≈ 8", _num_or_none(v3.get("V_mG")) is not None
          and abs(_num_or_none(v3["V_mG"]) - 8.0) < 1e-4, str(v3.get("V_mG")))

# ---------------------------------------------------------------------------
section("N. 第十一批：.ggb 3D 往返 / 协方差椭球 / 曲面参数线")
clear()
for t in ["A3=(1,2,3)", "O=(0,0,0)", "P=(1,2)", "c=Circle[O,2]", "sp=Sphere[O,2]",
          "cu=Cube[O,(2,0,0)]", "co=Cone[c,3]"]:
    put(t)
st, hdrs, raw = http("/api/export/ggb")
hdr = {k.lower(): v for k, v in hdrs.items()}
xml = raw.decode("utf-8")
check(".ggb 导出 HTTP 200", st == 200, "HTTP %s" % st)
check(".ggb 不再警告跳过 3D", "x-ggb-warnings" not in hdr, str([k for k in hdr if "ggb" in k]))
check(".ggb 含三维点真实 z（w=\"1\"）", 'z="3" w="1"' in xml, xml[:80])
check(".ggb 含 3D 命令（Sphere/Cube/Cone）", 'name="Sphere"' in xml and 'name="Cube"' in xml and 'name="Cone"' in xml)
req = urllib.request.Request(BASE + "/api/load", data=xml.encode("utf-8"),
                             headers={"Content-Type": "text/plain"}, method="POST")
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        rl = json.loads(resp.read().decode("utf-8"))
except Exception as e:
    rl = {"ok": False, "message": str(e)}
check(".ggb 载入 HTTP 正常", (rl or {}).get("ok") is True, str(rl)[:80])
els = state3d()
sp = find(els, "sp")
cu = find(els, "cu")
co = find(els, "co")
check(".ggb 往返后球 r=2 仍在", sp is not None and abs((sp.get("data") or {}).get("r", 0) - 2.0) < 1e-9,
      str((sp.get("data") or {}).get("r") if sp else None))
check(".ggb 往返后立方体 8 顶点 / 圆锥 49 顶点",
      cu is not None and len((cu.get("data") or {}).get("verts", [])) == 8
      and co is not None and len((co.get("data") or {}).get("verts", [])) == 49,
      "%s/%s" % (len((cu.get("data") or {}).get("verts", [])) if cu else None,
                 len((co.get("data") or {}).get("verts", [])) if co else None))
check(".ggb 往返后二维点仍无 z",
      find(els, "P") is not None and find(els, "P").get("z") in (0.0, None),
      str(find(els, "P").get("z") if find(els, "P") else None))
# 协方差椭球 + 参数线
clear()
for t in ["L={(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)}", "ell=CovarianceEllipsoid[L,2]",
          "cyl=SurfaceParam[cos(t),sin(t),s,s,t,0,2,0,2*pi,16]", "iso=SurfaceIsoline[cyl,1,1]"]:
    put(t)
els = state3d()
ell = find(els, "ell")
iso = find(els, "iso")
check("API 协方差椭球 → surface 网格（441 顶点）",
      ell is not None and ell.get("solid") == "surface" and len((ell.get("data") or {}).get("verts", [])) == 441,
      "%s/%s" % (ell.get("solid") if ell else None,
                 len((ell.get("data") or {}).get("verts", [])) if ell else None))
check("API 曲面参数线 → curve3d（120 段）",
      iso is not None and iso.get("objtype") == "curve3d" and (iso.get("data") or {}).get("count") == 120,
      "%s/%s" % (iso.get("objtype") if iso else None, (iso.get("data") or {}).get("count") if iso else None))

# ---------------------------------------------------------------------------
section("O. 第十二批：凸包 / 曲面取点投影 / 命令帮助")
clear()
for t in ["cube={(0,0,0),(2,0,0),(2,2,0),(0,2,0),(0,0,2),(2,0,2),(2,2,2),(0,2,2)}",
          "h1=ConvexHull[cube]", "V1=Volume[h1]",
          "cyl=SurfaceParam[cos(t),sin(t),s,s,t,0,2,0,2*pi,16]",
          "sp1=SurfacePoint[cyl,1,0]", "pr1=SurfaceProject[(5,0,1),cyl]"]:
    put(t)
els = state3d()
h1 = find(els, "h1")
sp1 = find(els, "sp1")
pr1 = find(els, "pr1")
check("API ConvexHull → 8 顶点 / 12 三角",
      h1 is not None and len((h1.get("data") or {}).get("verts", [])) == 8
      and len((h1.get("data") or {}).get("faces", [])) == 12,
      "%s/%s" % (len((h1.get("data") or {}).get("verts", [])) if h1 else None,
                 len((h1.get("data") or {}).get("faces", [])) if h1 else None))
check("API SurfacePoint[圆柱,1,0] = (1,0,1)",
      sp1 is not None and abs(sp1.get("x", 0) - 1) < 1e-9 and abs(sp1.get("z", 0) - 1) < 1e-9,
      "(%s,%s,%s)" % (sp1.get("x"), sp1.get("y"), sp1.get("z")) if sp1 else None)
check("API SurfaceProject → (1,0,1)",
      pr1 is not None and abs(pr1.get("x", 0) - 1) < 1e-5 and abs(pr1.get("z", 0) - 1) < 1e-5,
      "(%s,%s,%s)" % (pr1.get("x"), pr1.get("y"), pr1.get("z")) if pr1 else None)
st, d = jget("/api/state")
vals = {e.get("label"): e.get("value") for e in (d or {}).get("elements", [])}
check("API 凸包体积 = 8", _num_or_none(vals.get("V1")) is not None and abs(_num_or_none(vals["V1"]) - 8) < 1e-9,
      str(vals.get("V1")))
# 命令列表包含本轮新命令（帮助面板/补全数据源）
st_c, dc = jget("/api/commands")
cmds = set((dc or {}).get("commands", []))
need = {"convexhull", "surfacepoint", "surfaceproject", "covarianceellipsoid", "surfaceisoline",
        "boundingbox", "covariance", "mesh", "surfaceparam", "implicitsurface", "gltf"}
missing = sorted(need - cmds - {"gltf"})
check("API 命令列表含本轮新增命令", not missing, "缺 " + str(missing))

# ---------------------------------------------------------------------------
section("P. 第十三批（P0）：state3d 增量 / gzip / 并发串行化")
clear()
put("cu=Cube[(0,0,0),(2,0,0)]")
put("sp=Sphere[(1,1,1),2]")
full = jget("/api/state3d")[1]
rev0 = full.get("rev")
check("state3d 全量首屏带 rev", isinstance(rev0, int) and "elements" in full and full.get("count") == 2,
      "rev=%s count=%s" % (rev0, full.get("count")))
again = jget("/api/state3d?since=%d" % rev0)[1]
check("同一 rev 再请求 → unchanged（零重传）",
      again.get("unchanged") is True and "elements" not in again and again.get("rev") == rev0,
      json.dumps(again, ensure_ascii=False)[:90])
put("co=Cone[Circle[(0,0),1],2]")
d1 = jget("/api/state3d?since=%d" % rev0)[1]
labels1 = sorted(e.get("label") for e in (d1.get("changed") or []))
check("新增对象后只回增量（changed=[co]）",
      d1.get("unchanged") is False and labels1 == ["co"] and not d1.get("removed")
      and d1.get("rev") > rev0, json.dumps({"changed": labels1, "removed": d1.get("removed")})[:90])
# 合并增量 == 全量
merged = {}
for e in full["elements"]:
    merged[e["label"]] = e
for e in d1.get("changed") or []:
    merged[e["label"]] = e
for lab in d1.get("removed") or []:
    merged.pop(lab, None)
full2 = jget("/api/state3d")[1]
check("增量合并结果 == 全量结果（标签集合）",
      sorted(merged.keys()) == sorted(e["label"] for e in full2["elements"]),
      "%s vs %s" % (sorted(merged.keys()), sorted(e["label"] for e in full2["elements"])))
# 删除对象 → removed
rev_now = d1["rev"]
jpost("/api/input", {"text": "Delete[co]"})
d2 = jget("/api/state3d?since=%d" % rev_now)[1]
check("删除后返回 removed=[co]", "co" in (d2.get("removed") or []),
      json.dumps({"removed": d2.get("removed"), "changed": [e.get("label") for e in (d2.get("changed") or [])]})[:90])
# rev 过期 → 全量兜底
stale = jget("/api/state3d?since=-999")[1]
check("rev 过期（历史已淘汰/未知）→ 全量兜底", "elements" in stale and len(stale["elements"]) >= 2,
      "keys=%s" % sorted(stale.keys()))
# gzip：大网格载荷
clear()
put("big=ImplicitSurface[x^2+y^2+z^2-4=0,-2.2,2.2,-2.2,2.2,-2.2,2.2,24]")
req = urllib.request.Request(BASE + "/api/state3d", headers={"Accept-Encoding": "gzip"})
with urllib.request.urlopen(req, timeout=30) as resp:
    gz = resp.read()
    enc = (resp.headers.get("Content-Encoding") or "").lower()
    raw = gzip.decompress(gz) if enc == "gzip" else gz
check("大 state3d 响应启用 gzip", enc == "gzip", "Content-Encoding=%s" % enc)
check("gzip 压缩后体积显著减小（< 40%）", len(gz) < 0.4 * len(raw),
      "%.0f KB → %.0f KB（%.0f%%）" % (len(raw) / 1024, len(gz) / 1024, 100.0 * len(gz) / max(1, len(raw))))
try:
    payload = json.loads(raw.decode("utf-8"))
    ok_json = payload.get("count", 0) == 1
except Exception:
    ok_json = False
check("gzip 解压后 JSON 可解析", ok_json)
# 并发串行化：两个请求同时改构造，不能丢元素/破坏顺序
clear()
import concurrent.futures as _cf  # noqa: E402

def _post(t):
    _st, _d = jpost("/api/input", {"text": t})
    return _d or {}

with _cf.ThreadPoolExecutor(max_workers=2) as ex:
    r1, r2 = [f.result() for f in [ex.submit(_post, "A1=(1,1)"), ex.submit(_post, "B1=(2,2)")]]
check("并发写入均成功", r1.get("ok") and r2.get("ok"), "%s / %s" % (r1.get("ok"), r2.get("ok")))
st3, d3 = jget("/api/state")
labs3 = sorted(e.get("label") for e in (d3 or {}).get("elements", []))
check("并发后两个对象都在（无丢失更新）", labs3 == ["A1", "B1"], str(labs3))

# ---------------------------------------------------------------------------
section("Q. P1-D：撤销/重做增量与计算记忆")
clear()
put("cu=Cube[(0,0,0),(2,0,0)]")
put("imp=ImplicitSurface[x^2+y^2+z^2-4=0,-2.2,2.2,-2.2,2.2,-2.2,2.2,32]")
put("A1=Area[imp]")
els = state3d()
imp0 = find(els, "imp")
v0 = len((imp0.get("data") or {}).get("verts", []))
_st, d0 = jget("/api/state")
a0 = None
for e in (d0 or {}).get("elements", []):
    if e.get("label") == "A1":
        a0 = _num_or_none(e.get("value"))
check("重做性能用例就绪（等值面 11978 顶点）", v0 == 11978 and a0 is not None, "v=%d area=%s" % (v0, a0))
st, j1 = jpost("/api/undo", {})
st, j2 = jpost("/api/undo", {})
els = state3d()
check("两次撤销后重对象从 3D 状态移除", find(els, "imp") is None and find(els, "A1") is None,
      str([e.get("label") for e in els]))
_t0 = time.time()
st, j3 = jpost("/api/redo", {})
_dt = time.time() - _t0
check("redo 走计算记忆（HTTP 往返 < 500 ms，原约 1.2 s）", _dt < 0.5, "%.0f ms" % (_dt * 1000))
els = state3d()
imp1 = find(els, "imp")
check("redo 后网格顶点数一致", imp1 is not None and len((imp1.get("data") or {}).get("verts", [])) == v0,
      "%s vs %d" % (len((imp1.get("data") or {}).get("verts", [])) if imp1 else None, v0))
st, j4 = jpost("/api/redo", {})
_st2, d2 = jget("/api/state")
a2 = None
for e in (d2 or {}).get("elements", []):
    if e.get("label") == "A1":
        a2 = _num_or_none(e.get("value"))
check("redo 后依赖元素结果一致", a2 is not None and a0 is not None and abs(a2 - a0) < 1e-9,
      "%s vs %s" % (a2, a0))
_st3, d3 = jget("/api/state")
check("重做栈状态正确（can_redo=False）", (d3 or {}).get("can_redo") is False, str((d3 or {}).get("can_redo")))

# ---------------------------------------------------------------------------
section("R. P2：.ggb 内嵌网格/图片数据")
clear()
OBJ_R = """v 0 0 0
v 2 0 0
v 2 2 0
v 0 2 0
v 0 0 2
v 2 0 2
v 2 2 2
v 0 2 2
f 1 2 3 4
f 5 6 7 8
f 1 2 6 5
f 2 3 7 6
f 3 4 8 7
f 4 1 5 8
"""
req_m = urllib.request.Request(BASE + "/api/mesh", data=OBJ_R.encode("utf-8"),
                               headers={"Content-Type": "application/octet-stream"}, method="POST")
with urllib.request.urlopen(req_m, timeout=30) as resp:
    rm = json.loads(resp.read().decode("utf-8"))
mid_r = (rm or {}).get("id")
check("准备：导入 OBJ 网格", bool(mid_r), str(rm)[:60])
if mid_r:
    put("m2=Mesh[" + mid_r + "]")
    put("V2=Volume[m2]")
    png_b64 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAACklEQVR4nGMAAQAABQABDQottAAAAABJRU5ErkJggg==")
    _st_img, r_img = jpost("/api/image", {"data": "data:image/png;base64," + png_b64, "w": 1, "h": 1})
    iid_r = (r_img or {}).get("id")
    check("准备：上传图片", bool(iid_r), str(r_img)[:50])
    if iid_r:
        put("I1=(0,0)")
        put("I2=(3,0)")
        put("pic2=Image[I1,I2," + iid_r + "]")
    _st, h_r, raw_r = http("/api/export/ggb")
    xml_r = raw_r.decode("utf-8")
    hdr_r = {k.lower(): v for k, v in h_r.items()}
    check(".ggb 响应不再带跳过警告头", not hdr_r.get("x-ggb-warnings"),
          str(hdr_r.get("x-ggb-warnings"))[:60])
    check(".ggb 含内嵌数据块 ggbpyData", "<ggbpyData" in xml_r, "len=%d" % len(xml_r))
    req_l = urllib.request.Request(BASE + "/api/load", data=xml_r.encode("utf-8"),
                                   headers={"Content-Type": "text/plain"}, method="POST")
    try:
        with urllib.request.urlopen(req_l, timeout=30) as resp_l:
            _st_l = resp_l.status
            rl_r = json.loads(resp_l.read().decode("utf-8"))
    except Exception as e:
        _st_l, rl_r = 0, {"ok": False, "message": str(e)}
    check(".ggb 载入成功", rl_r.get("ok") is True, str(rl_r)[:60])
    els_r = state3d()
    m2r = find(els_r, "m2")
    check(".ggb 往返后网格 8 顶点/6 面仍在",
          m2r is not None and len((m2r.get("data") or {}).get("verts", [])) == 8
          and len((m2r.get("data") or {}).get("faces", [])) == 6,
          "%s/%s" % (len((m2r.get("data") or {}).get("verts", [])) if m2r else None,
                     len((m2r.get("data") or {}).get("faces", [])) if m2r else None))
    _st_s, d_r = jget("/api/state")
    vals_r = {e.get("label"): e.get("value") for e in (d_r or {}).get("elements", [])}
    check(".ggb 往返后依赖体积仍为 8", _num_or_none(vals_r.get("V2")) is not None
          and abs(_num_or_none(vals_r["V2"]) - 8.0) < 1e-9, str(vals_r.get("V2")))
    if iid_r:
        _st_i, _h_i, raw_i = http("/api/image/" + iid_r)
        check(".ggb 往返后图片数据可用（可再次取图）", raw_i[:8] == b"\x89PNG\r\n\x1a\n",
              "len=%d" % len(raw_i))

# ---------------------------------------------------------------------------
section("S. P2：SVG 3D 投影导出")
clear()
put("O=(0,0,0)")
put("cu=Cube[O,(2,0,0)]")
put("P=(1,1,1)")
put("sp=Sphere[(1,1,1),1.5]")
_st, h3, raw3 = http("/api/export/svg?view3d=1")
svg3 = raw3.decode("utf-8", "replace")
hdr3 = {k.lower(): v for k, v in h3.items()}
check("view3d=1 返回 SVG", _st == 200 and svg3.startswith("<?xml") and "<svg" in svg3,
      "HTTP %s len=%d" % (_st, len(raw3)))
check("响应头标记 3D 模式与文件名", hdr3.get("x-svg-mode") == "3d"
      and "ggbpy-3d.svg" in hdr3.get("content-disposition", ""),
      str({k: hdr3.get(k) for k in ("x-svg-mode", "content-disposition")}))
check("含多边形（立方体 6 面）与折线（球经纬线）",
      svg3.count("<polygon") >= 6 and svg3.count("<polyline") >= 4,
      "polygon=%d polyline=%d" % (svg3.count("<polygon"), svg3.count("<polyline")))
_st4, _h4, raw4 = http("/api/export/svg?view3d=1&yaw=-0.72&pitch=-0.45")
_svg4 = raw4.decode("utf-8", "replace")
check("view3d 支持 yaw/pitch 机位参数（换角度输出不同）",
      _st4 == 200 and _svg4.startswith("<?xml") and _svg4 != svg3,
      "HTTP %s len=%d" % (_st4, len(raw4)))
check("默认 3D 机位为俯视（desc 里标注 pitch 取负值为俯视）",
      "pitch 取负值即俯视" in svg3, "")
check("含点标签", svg3.count("<circle") >= 1 and "<text" in svg3,
      "circle=%d" % svg3.count("<circle"))
_st2, h2d, raw2d = http("/api/export/svg")
hdr2d = {k.lower(): v for k, v in h2d.items()}
check("默认 2D 模式仍可用（X-Svg-Mode: 2d，无 polygon）",
      _st2 == 200 and hdr2d.get("x-svg-mode") == "2d" and "<svg" in raw2d.decode("utf-8", "replace"),
      "mode=%s" % hdr2d.get("x-svg-mode"))
clear()
put("A=(0,0)")
_st3, _h3, raw3b = http("/api/export/svg?view3d=1")
check("无 3D 对象时给出明确错误（HTTP 400 + 说明）",
      _st3 == 400 and "3D" in raw3b.decode("utf-8", "replace"), "HTTP %s" % _st3)

# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print("3D API 检测矩阵 @ %s：%d 项断言，%d 失败" % (BASE, COUNT[0], len(FAILS)))
for f in FAILS:
    print("  FAILED: " + f)
print("结果:", "ALL PASS" if not FAILS else "FAILED")
sys.exit(0 if not FAILS else 1)
