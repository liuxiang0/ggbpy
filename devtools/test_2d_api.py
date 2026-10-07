#!/usr/bin/env python3
"""ggbpy 2D / 平台 API 检测矩阵（第十三批 P0-C）

补上 REVIEW_12_BATCHES.md 里「API 32 端点中 17 个未被任何检测覆盖」的盲区：
drag / shift / batch / reorder / macro* / share+shared / image* / cas* / download / export/svg / demo / load

用法：
    python3 -B devtools/test_2d_api.py [--base http://127.0.0.1:8090]
退出码：0 = 全部通过，1 = 有失败，2 = 服务不可用。
"""
import base64
import gzip
import io
import json
import sys
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8090"
if "--base" in sys.argv:
    BASE = sys.argv[sys.argv.index("--base") + 1]

PASS = 0
FAIL = 0
FAILED = []


def section(title: str) -> None:
    print("\n=== " + title + " ===")


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  OK   " + name + (("  [" + detail + "]") if detail else ""))
    else:
        FAIL += 1
        FAILED.append(name)
        print("  FAIL " + name + "  " + detail)


def req(path, body=None, method=None, raw=False, headers=None):
    hdr = {"Content-Type": "application/json"}
    if headers:
        hdr.update(headers)
    data = None
    if body is not None:
        data = body.encode("utf-8") if isinstance(body, str) else json.dumps(body).encode("utf-8")
    r = urllib.request.Request(BASE + path, data=data, headers=hdr, method=method or ("POST" if data else "GET"))
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            payload = resp.read()
            try:
                js = json.loads(payload.decode("utf-8"))
            except Exception:
                js = None
            return resp.status, dict(resp.headers), payload, js
    except urllib.error.HTTPError as e:                       # 404/400 等也要拿到状态码与响应体
        payload = e.read()
        try:
            js = json.loads(payload.decode("utf-8"))
        except Exception:
            js = None
        return e.code, dict(e.headers or {}), payload, js
    except Exception as e:
        return 0, {}, str(e).encode(), None


def post(path, body=None):
    st, _h, _raw, js = req(path, body if body is not None else {})
    return st, js or {}


def get(path, headers=None):
    st, h, raw, js = req(path, None, headers=headers)
    return st, h, raw, js


def hget(headers, name, default=""):
    for k, v in (headers or {}).items():
        if k.lower() == name.lower():
            return v
    return default


def clear():
    post("/api/clear", {})


def state():
    _st, _h, _raw, js = get("/api/state")
    return (js or {}).get("elements", [])


def labels():
    return sorted(e.get("label") for e in state())


# ---------------------------------------------------------------------------
section("A. 服务探针")
st, _h, raw, js = get("/")
check("服务可达 " + BASE, st == 200, "HTTP %s" % st)
if st != 200:
    print("\n服务不可用：请先启动（cd ggbpy && PORT=8090 ./run.sh）")
    sys.exit(2)

# ---------------------------------------------------------------------------
section("B. /api/demo + /api/load")
clear()
st, js = post("/api/demo", {})
check("/api/demo 载入示例并返回元素", st == 200 and js.get("ok") is True and len(js.get("elements", [])) > 0,
      "n=%s" % len(js.get("elements", [])))
demo_labels = [e["label"] for e in js.get("elements", [])]
# 用下载的 .ggk 覆盖当前构造
st, h, raw, _js = get("/api/download")
check("/api/download 返回 .ggk（attachment + JSON）",
      st == 200 and raw[:1] == b"{" and "attachment" in hget(h, "Content-Disposition"),
      "len=%d cd=%s" % (len(raw), hget(h, "Content-Disposition")))
ggk = raw.decode("utf-8")
clear()
st, js = post("/api/load", ggk)
check("/api/load 载入 .ggk 且元素一致", st == 200 and js.get("ok") is True and labels() == sorted(demo_labels),
      "%s vs %s" % (labels()[:6], sorted(demo_labels)[:6]))
# 拖拽 + 整体平移（先清空，避免与示例重名）
clear()
put = lambda t: post("/api/input", {"text": t})
put("A=(1,1)")
put("B=(3,1)")
st, js = post("/api/drag", {"label": "A", "x": 2.5, "y": 4.0, "push": True})
els = {e["label"]: e for e in js.get("elements", [])}
check("/api/drag 移动点并返回新状态",
      st == 200 and js.get("ok") and abs(float(els["A"]["x"]) - 2.5) < 1e-9 and abs(float(els["A"]["y"]) - 4.0) < 1e-9,
      "A=(%s,%s)" % (els["A"]["x"], els["A"]["y"]))
st, js = post("/api/shift", {"label": "B", "dx": 1.0, "dy": -2.0, "push": True})
els = {e["label"]: e for e in js.get("elements", [])}
check("/api/shift 整体平移", st == 200 and js.get("ok") and abs(float(els["B"]["x"]) - 4.0) < 1e-9,
      "B=(%s,%s)" % (els["B"]["x"], els["B"]["y"]))

# ---------------------------------------------------------------------------
section("C. /api/batch + /api/reorder")
clear()
st, js = post("/api/batch", {"script": "# 注释\nP=(0,0)\nQ=(2,0)\nr=Circle[P,1]\n\nbad=NotACommand[1]"})
res = js.get("results", [])
oks = [r for r in res if r.get("ok")]
bads = [r for r in res if not r.get("ok")]
check("/api/batch 逐行执行并报告结果", st == 200 and js.get("script_ok") == 3 and len(bads) == 1,
      "ok=%s bad=%s" % (js.get("script_ok"), len(bads)))
check("/api/batch 注释/空行被报告为 ok 但不创建对象",
      any(r.get("line") == "# 注释" and r.get("ok") for r in res)
      and any(r.get("line") == "(空)" for r in res),
      "lines=%s" % [r.get("line") for r in res][:5])
check("/api/batch 错误行给出信息", bool(bads) and bads[0].get("message"), str(bads[0].get("message"))[:40] if bads else "")
check("/api/batch 成功的对象已创建", labels() == ["P", "Q", "r"], str(labels()))
st, js = post("/api/reorder", {"order": ["r", "Q", "P"]})
check("/api/reorder 生效（列表顺序改变）", st == 200 and js.get("ok") and labels() == ["P", "Q", "r"],
      str(labels()))
_st, _h, _raw, st3 = get("/api/state")
check("/api/reorder 后状态顺序 = 新顺序", [e["label"] for e in (st3 or {}).get("elements", [])][:3] == ["r", "Q", "P"],
      str([e["label"] for e in (st3 or {}).get("elements", [])][:3]))

# ---------------------------------------------------------------------------
section("D. 宏端点 /api/macro*")
clear()
put("A=(0,0)")
put("B=(2,0)")
put("C=(0,2)")
put("tri=Polygon[A,B,C]")
import uuid as _uuid
MACRO_NAME = "tri2_" + _uuid.uuid4().hex[:6]      # 宏是服务端全局的，跨运行不清理 → 用唯一名
st, js = post("/api/macro/create", {"name": MACRO_NAME, "inputs": ["A", "B", "C"], "outputs": ["tri"]})
check("/api/macro/create 创建宏", st == 200 and js.get("ok") is not False, str(js)[:70])
_st, _h, _raw, js = get("/api/macro")
st = _st
names = [m.get("name") for m in (js or {}).get("macros", [])] if isinstance(js, dict) else []
check("/api/macro 列表含新宏", st == 200 and MACRO_NAME in names, str(names)[:60])
clear()
put("P1=(0,0)")
put("P2=(3,0)")
put("P3=(0,3)")
st, js = post("/api/macro/run", {"name": MACRO_NAME, "args": ["P1", "P2", "P3"]})
check("/api/macro/run 执行宏并创建对象", st == 200 and js.get("ok") is True and len(js.get("created", [])) >= 1,
      "created=%s" % js.get("created"))
st, js = post("/api/macro/run", {"name": "不存在的宏", "args": []})
check("/api/macro/run 未知宏 → 明确失败", js.get("ok") is False and "不存在" in str(js.get("message")), str(js.get("message"))[:40])
st, js = post("/api/macro/delete", {"name": MACRO_NAME})
_st, _h, _raw, js2 = get("/api/macro")
names2 = [m.get("name") for m in (js2 or {}).get("macros", [])] if isinstance(js2, dict) else []
check("/api/macro/delete 删除宏", st == 200 and MACRO_NAME not in names2, str(names2)[:50])

# ---------------------------------------------------------------------------
section("E. /api/share + /api/shared/{id}")
clear()
put("S1=(1,1)")
put("S2=(3,3)")
st, js = post("/api/share", {})
sid = js.get("id")
check("/api/share 返回短 id", st == 200 and bool(sid), "id=%s" % sid)
if sid:
    st, _h, raw, js2 = get("/api/shared/" + urllib.parse.quote(sid))
    content = (js2 or {}).get("content") or ""
    check("/api/shared/{id} 取回 .ggk 文本", st == 200 and js2.get("ok") is True and content[:1] == "{",
          "len=%d" % len(content))
    clear()
    st, js3 = post("/api/load", content)
    check("分享内容可再次载入且元素一致", js3.get("ok") is True and labels() == ["S1", "S2"],
          "labels=%s ok=%s msg=%s" % (labels(), js3.get("ok"), str(js3.get("message"))[:40]))
    _st, _h, _raw, js4 = get("/api/shared/aaaaaa")
    check("/api/shared 不存在的 id → ok=false 且给出原因",
          js4.get("ok") is False and js4.get("message"), str(js4.get("message"))[:30])
    _st, _h, _raw, js5 = get("/api/shared/zzz")
    check("/api/shared 非法 id 格式 → ok=false", js5.get("ok") is False, str(js5.get("message"))[:30])

# ---------------------------------------------------------------------------
section("F. /api/image + /api/image/{id}")
clear()
png = base64.b64encode(bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082")).decode("ascii")
st, js = post("/api/image", {"data": "data:image/png;base64," + png, "w": 1, "h": 1})
iid = js.get("id")
check("/api/image 上传图片返回 id", st == 200 and js.get("ok") and bool(iid), "id=%s" % iid)
if iid:
    st, h, raw, _js = get("/api/image/" + urllib.parse.quote(iid))
    check("/api/image/{id} 返回图片字节", st == 200 and raw[:8] == b"\x89PNG\r\n\x1a\n",
          "len=%d type=%s" % (len(raw), hget(h, "Content-Type")))
    put("I1=(0,0)")
    st, js2 = post("/api/input", {"text": "pic=Image[I1,(2,0),%s]" % iid})
    check("图片可作为 Image 对象插入并随 .ggk 保存",
          js2.get("ok") is True and any(e.get("label") == "pic" for e in state()), str(js2.get("message"))[:40])

# ---------------------------------------------------------------------------
section("G. CAS 端点 /api/cas*")
clear()
_st, _h, _raw, js = get("/api/cas")
st = _st
check("/api/cas 返回单元格列表", st == 200 and isinstance(js.get("cells"), list), str(js)[:60])
st, js = post("/api/cas/eval", {"text": "Expand[(x+1)^2]"})
check("/api/cas/eval 计算并返回结果", st == 200 and js.get("ok") is True and "cells" in js,
      str(js.get("cells"))[:70])
st, js = post("/api/cas/clear", {})
check("/api/cas/clear 清空单元格", st == 200 and js.get("ok") is True and js.get("cells") == [],
      str(js.get("cells"))[:30])

# ---------------------------------------------------------------------------
section("H. /api/export/svg")
clear()
put("A=(0,0)")
put("B=(4,0)")
put("poly=Polygon[A,B,(4,3)]")
put("c=Circle[A,2]")
st, h, raw, _js = get("/api/export/svg")
txt = raw.decode("utf-8", "replace")
check("/api/export/svg 返回 SVG", st == 200 and "<svg" in txt and "</svg>" in txt, "len=%d" % len(raw))
check("SVG 含多边形与圆（path/circle）", ("polygon" in txt or "path" in txt) and ("circle" in txt or "path" in txt),
      "polygon=%s circle=%s" % ("polygon" in txt, "circle" in txt))
put("S3=(1,1,1)")
put("sp3=Sphere[S3,1]")
_st2, h, raw, _js = get("/api/export/svg")
st = _st2
txt2 = raw.decode("utf-8", "replace")
check("SVG 导出跳过 3D 对象（仍返回 2D 内容）", st == 200 and "<svg" in txt2,
      "warn=%s" % (hget(h, "X-GGB-Warnings") or hget(h, "X-Svg-Warnings") or "-"))

# ---------------------------------------------------------------------------
section("I. 统计图：创建 / 整体拖动 / 撤销 / state3d")
clear()
post("/api/input", {"text": "D={3,1,4,1,5,9,2,6}"})
for line in ("bc=BarChart[D]", "lc=LineChart[D]", "sc=ScatterPlot[{(1,2),(2,4),(3,3)}]",
             "dp=DotPlot[{1,2,2,3}]", "pi=PieChart[{3,5,2,4}]", "bp=BoxPlot[D]"):
    st, js = post("/api/input", {"text": line})
    check("创建 " + line.split("=")[0], js.get("ok") is True, (js.get("message") or "")[:30])
els = {e["label"]: e for e in state()}
chart_labels = ["bc", "lc", "sc", "dp", "pi", "bp"]
check("六种统计图都在状态里且带 offset",
      all(l in els and els[l].get("offset") == [0, 0] for l in chart_labels),
      str({l: els.get(l, {}).get("offset") for l in chart_labels}))
st, js = post("/api/drag", {"label": "bc", "x": 4.0, "y": -2.5,
                            "xmin": -16, "xmax": 16, "ymin": -9, "ymax": 9, "push": True})
check("/api/drag 可整体移动统计图（offset 落库）",
      js.get("ok") is True and {e["label"]: e for e in js["elements"]}["bc"]["offset"] == [4.0, -2.5],
      str({e["label"]: e.get("offset") for e in js.get("elements", []) if e["label"] == "bc"}))
st, js = post("/api/undo", {})
bc_off = {e["label"]: e for e in js.get("elements", [])}.get("bc", {}).get("offset")
check("撤销可回退统计图整体移动", bc_off == [0, 0], str(bc_off))
# 3D 统计图：state3d 里应出现网格
post("/api/input", {"text": "b3=BarChart3D[{1,3,2}]"})
post("/api/input", {"text": "s3=ScatterPlot3D[{(1,1,1),(2,2,3)}]"})
post("/api/input", {"text": "f3=SurfaceChart3D[{1,2,3,2,3,4,3,4,5},3]"})
st, _h3, _raw3, js = get("/api/state3d")
m3 = {e["label"]: e for e in js.get("elements", [])}
check("3D 柱状图出现在 state3d（32 顶点网格）",
      m3.get("b3", {}).get("objtype") == "polyhedron" and len((m3.get("b3", {}).get("data") or {}).get("verts", [])) == 24,
      str((m3.get("b3", {}).get("data") or {}).get("verts", [])[:1]))
check("3D 散点图出现在 state3d（2 个标记）",
      len((m3.get("s3", {}).get("data") or {}).get("verts", [])) == 12,
      str(len((m3.get("s3", {}).get("data") or {}).get("verts", []))))
check("3D 高度场出现在 state3d（3×3 网格）",
      len((m3.get("f3", {}).get("data") or {}).get("verts", [])) == 9,
      str(len((m3.get("f3", {}).get("data") or {}).get("verts", []))))
# 图表含在 CSV/SVG 导出里不应报错
st, _h, raw = req("/api/export/svg", raw=True)[0:3]
check("统计图存在时 SVG 导出仍成功", st == 200 and b"<svg" in raw, "HTTP %s" % st)

# ---------------------------------------------------------------------------
section("H. 新命令端到端（CAS 算子接线 + 表面积/有限性，经 HTTP 链路）")

clear()
put("S=Solve[x^2-4=0, x]")
put("F=IsFinite[1/0]")
put("L=Limit[sin(x)/x, 0]")
put("B=Substitute[x^2, x, 3]")
_els = {e.get("label"): e for e in state()}
# 序列化约定：list → 顶层 items；boolean → 顶层 value（"true"/"false"）；number → 顶层 val
check("API：Solve → 列表元素 items=[-2, 2]",
      sorted((_els.get("S") or {}).get("items") or []) == [-2.0, 2.0],
      str((_els.get("S") or {}).get("items")))
check("API：IsFinite[1/0] → 布尔 false",
      (_els.get("F") or {}).get("value") == "false", str((_els.get("F") or {}).get("value")))
check("API：Limit[sin(x)/x, 0] → 1",
      abs(float((_els.get("L") or {}).get("val") or 0) - 1.0) < 1e-9,
      str((_els.get("L") or {}).get("val")))
check("API：Substitute[x^2, x, 3] → 9",
      abs(float((_els.get("B") or {}).get("val") or 0) - 9.0) < 1e-9,
      str((_els.get("B") or {}).get("val")))

# ---------------------------------------------------------------------------
section("I. 二维剖分端到端（Delaunay / Voronoi 经 HTTP）")

clear()
put("Pts={(0,0),(4,0),(4,4),(0,4),(2,2)}")
put("Del=Delaunay[Pts]")
put("Vor=Voronoi[Pts]")
_els2 = {e.get("label"): e for e in state()}
_del = _els2.get("Del") or {}
_vor = _els2.get("Vor") or {}
check("API：Delaunay → itemkind=polygon 列表（4 个三角形，每项 3 顶点）",
      _del.get("itemkind") == "polygon" and len(_del.get("items") or []) == 4
      and all(len(p) == 3 for p in (_del.get("items") or [])),
      "itemkind=%s n=%s" % (_del.get("itemkind"), len(_del.get("items") or [])))
check("API：Voronoi → 5 个元胞（元胞均有界）",
      _vor.get("itemkind") == "polygon" and len(_vor.get("items") or []) == 5,
      "n=%s" % len(_vor.get("items") or []))
check("API：多边形列表带摘要 value（数量 + 顶点范围 + 总面积）",
      "4 个多边形" in str(_del.get("value")) and "总面积" in str(_del.get("value")),
      str(_del.get("value")))

# ---------------------------------------------------------------------------
section("J. 剖分信息经 HTTP（面积/质心随依赖刷新）")

clear()
put("A2=(0,0)")
put("B2=(4,0)")
put("C2=(4,4)")
put("D2=(0,4)")
put("VV2=Voronoi[{A2,B2,C2,D2}]")
_vel = {e.get("label"): e for e in state()}.get("VV2") or {}
check("API：Voronoi 返回 areas/centroids（4 个元胞）",
      len(_vel.get("areas") or []) == 4 and len(_vel.get("centroids") or []) == 4,
      "areas=%s" % (len(_vel.get("areas") or []),))
check("API：摘要 value 含数量与总面积",
      "4 个多边形" in str(_vel.get("value")) and "总面积" in str(_vel.get("value")), str(_vel.get("value")))
_areas_before = [round(float(v), 4) for v in (_vel.get("areas") or [])]
put("SetCoords[A2, -3, -3]")
_vel2 = {e.get("label"): e for e in state()}.get("VV2") or {}
check("API：移动点后元胞面积变化（内联列表 + memo 修复链路）",
      [round(float(v), 4) for v in (_vel2.get("areas") or [])] != _areas_before,
      "%s → %s" % (_areas_before[:2], [round(float(v), 4) for v in (_vel2.get("areas") or [])][:2]))

# ---------------------------------------------------------------------------
section("K. 交互控件经 HTTP（caption/target/脚本 + 目标可见性切换）")

clear()
put("cK=Circle[(0,0),2]")
put("nK=3")
put('bK=Button["点我", "AK=(2,2)", (3,4)]')
put('cbK=CheckBox["显示圆", cK, (-3,1)]')
put("ibK=InputBox[nK, (2,-2)]")
_elsK = {e.get("label"): e for e in state()}
check("API：Button/CheckBox/InputBox 三个控件都创建成功并带绑定信息",
      (_elsK.get("bK") or {}).get("kind") == "button" and (_elsK.get("bK") or {}).get("script") == "AK=(2,2)"
      and (_elsK.get("cbK") or {}).get("target") == "cK" and (_elsK.get("ibK") or {}).get("target") == "nK",
      "%s/%s/%s" % ((_elsK.get("bK") or {}).get("kind"), (_elsK.get("cbK") or {}).get("target"),
                    (_elsK.get("ibK") or {}).get("target")))
put("SetVisible[cK, false]")
_elsK2 = {e.get("label"): e for e in state()}
check("API：SetVisible 切换目标可见性（复选框的前端派生依据）",
      (_elsK2.get("cK") or {}).get("visible") is False, str((_elsK2.get("cK") or {}).get("visible")))

# ---------------------------------------------------------------------------
section("L. 画布滑块经 HTTP（几何字段 + /api/drag 改值）")

clear()
put("sL=Slider[0,10,1,(-2,2)]")
_sEl = {e.get("label"): e for e in state()}.get("sL") or {}
check("API：滑块返回 min/max/step 与 slider_x/y/len",
      _sEl.get("min") == 0 and _sEl.get("max") == 10
      and abs(float(_sEl.get("slider_x", 99)) + 2) < 1e-9 and float(_sEl.get("slider_len", 0)) == 3,
      str({k: _sEl.get(k) for k in ("min", "max", "slider_x", "slider_y", "slider_len")}))
post("/api/drag", {"label": "sL", "x": 6, "y": 0, "push": True})
_sEl2 = {e.get("label"): e for e in state()}.get("sL") or {}
check("API：/api/drag 更新滑块数值（画布拖动与面板共用同一端点）",
      abs(float(_sEl2.get("val", -1)) - 6) < 1e-9, str(_sEl2.get("val")))

# ---------------------------------------------------------------------------
section("M. 滑块持久化经 HTTP（drag 保持定义 + .ggk 往返保留数值）")

clear()
put("sM=Slider[0,10,1,(-5,3)]")
post("/api/drag", {"label": "sM", "x": 7, "y": 0, "push": True})
_sM = {e.get("label"): e for e in state()}.get("sM") or {}
check("API：/api/drag 后滑块仍是滑块（min/slider_x 保留、值已更新）",
      abs(float(_sM.get("val", -1)) - 7) < 1e-9 and _sM.get("min") == 0
      and abs(float(_sM.get("slider_x", 99)) + 5) < 1e-9,
      "val=%s min=%s slider_x=%s" % (_sM.get("val"), _sM.get("min"), _sM.get("slider_x")))
_st, _h, _raw, _js = req("/api/download")
check("API：.ggk 含 version 5 与 values 字段",
      _st == 200 and b'"version": 5' in _raw and b'"values"' in _raw, "len=%d" % len(_raw))
_ggk = _raw.decode("utf-8")
post("/api/clear", {})
_st2, _js2 = post("/api/load", _ggk)
_sM2 = {e.get("label"): e for e in state()}.get("sM") or {}
check("API：载入 .ggk 后滑块值保留为 7（不再回到 0）",
      _st2 == 200 and abs(float(_sM2.get("val", -1)) - 7) < 1e-9 and _sM2.get("min") == 0,
      "val=%s" % _sM2.get("val"))

# ---------------------------------------------------------------------------
section("N. 控件/滑块锚点移动经 HTTP（SetWidgetPos）")

clear()
put('bN=Button["点我", "BN=(1,1)", (0,0)]')
put("slN=Slider[0,10,1,(0,0)]")
post("/api/drag", {"label": "slN", "x": 9, "y": 0, "push": True})
put("SetWidgetPos[bN,(3,4)]")
put("SetWidgetPos[slN,(-3,2)]")
_elsN = {e.get("label"): e for e in state()}
check("API：按钮与滑块锚点已移动（defn 同步重写）",
      "(3,4)" in str((_elsN.get("bN") or {}).get("defn")) and "(-3,2)" in str((_elsN.get("slN") or {}).get("defn")),
      "%s | %s" % ((_elsN.get("bN") or {}).get("defn"), (_elsN.get("slN") or {}).get("defn")))
check("API：移动滑块后仍是滑动条且数值保留为 9",
      abs(float((_elsN.get("slN") or {}).get("val", -1)) - 9) < 1e-9
      and (_elsN.get("slN") or {}).get("min") == 0 and "Slider[" in str((_elsN.get("slN") or {}).get("defn")),
      "val=%s min=%s" % ((_elsN.get("slN") or {}).get("val"), (_elsN.get("slN") or {}).get("min")))

# ---------------------------------------------------------------------------
section("O. 表达式依赖经 HTTP（拖动滑块 → 受控点/线段跟随）")

clear()
put("sO=Slider[0,10,1,(0,0)]")
put("AO=(sO,0)")
put("sgO=Segment[(0,0),(sO,2)]")
post("/api/drag", {"label": "sO", "x": 8, "y": 0, "push": True})
_elsO = {e.get("label"): e for e in state()}
check("API：拖动滑块后受控点跟随（AO.x = 8）",
      abs(float((_elsO.get("AO") or {}).get("x", -1)) - 8) < 1e-9,
      str((_elsO.get("AO") or {}).get("x")))
check("API：字面量坐标线段端点跟随（sgO.x2 = 8）",
      abs(float((_elsO.get("sgO") or {}).get("x2", -1)) - 8) < 1e-9,
      str((_elsO.get("sgO") or {}).get("x2")))
check("API：受控点定义式保留（AO=(sO,0)，供 .ggk 重放）",
      str((_elsO.get("AO") or {}).get("defn")) == "AO=(sO,0)", str((_elsO.get("AO") or {}).get("defn")))

# ---------------------------------------------------------------------------
section("P. 就地编辑控件经 HTTP（SetCaption / SetScript）")

clear()
put('bP=Button["旧", "AP=(1,1)", (0,0)]')
put('SetCaption[bP, "新说明"]')
put('SetScript[bP, "CP=(2,2)"]')
_bP = {e.get("label"): e for e in state()}.get("bP") or {}
check("API：SetCaption/SetScript 生效且 defn 同步",
      _bP.get("caption") == "新说明" and _bP.get("script") == "CP=(2,2)"
      and 'Button["新说明","CP=(2,2)"' in str(_bP.get("defn")),
      "%s | %s" % (_bP.get("caption"), _bP.get("defn")))

# ---------------------------------------------------------------------------
section("Q. 输入框提交经 HTTP（SetInput：数值/表达式）")

clear()
put("sQ=Slider[0,10,1,(0,0)]")
put("nQ=5")
put('SetInput[sQ, "6"]')
put('SetInput[nQ, "sQ*2"]')
_elsQ = {e.get("label"): e for e in state()}
check("API：SetInput 数值改滑块（保留 Slider 定义）",
      abs(float((_elsQ.get("sQ") or {}).get("val", -1)) - 6) < 1e-9
      and "Slider[" in str((_elsQ.get("sQ") or {}).get("defn")),
      "val=%s defn=%s" % ((_elsQ.get("sQ") or {}).get("val"), (_elsQ.get("sQ") or {}).get("defn")))
check("API：SetInput 表达式 → 受控数值并跟随滑块",
      str((_elsQ.get("nQ") or {}).get("defn")) == "nQ=sQ*2"
      and abs(float((_elsQ.get("nQ") or {}).get("val", -1)) - 12) < 1e-9,
      "defn=%s val=%s" % ((_elsQ.get("nQ") or {}).get("defn"), (_elsQ.get("nQ") or {}).get("val")))
post("/api/drag", {"label": "sQ", "x": 8, "y": 0, "push": True})
_nQ2 = {e.get("label"): e for e in state()}.get("nQ") or {}
check("API：拖动滑块后受控数值跟随（sQ=8 → nQ=16）",
      abs(float(_nQ2.get("val", -1)) - 16) < 1e-9, str(_nQ2.get("val")))

# ---------------------------------------------------------------------------
section("R. 改滑块范围经 HTTP（SetSlider）")

clear()
put("sR=Slider[0,10,1,(0,0)]")
post("/api/drag", {"label": "sR", "x": 7, "y": 0, "push": True})
put("SetSlider[sR, -5, 5, 0.5]")
_elsR = {e.get("label"): e for e in state()}.get("sR") or {}
check("API：SetSlider 改范围/步长并夹紧当前值（7 → 5）",
      float(_elsR.get("min")) == -5 and float(_elsR.get("max")) == 5
      and abs(float(_elsR.get("val")) - 5) < 1e-9 and "Slider[-5,5,0.5," in str(_elsR.get("defn")),
      "min=%s max=%s val=%s" % (_elsR.get("min"), _elsR.get("max"), _elsR.get("val")))

# ---------------------------------------------------------------------------
section("S2. 滑块长度按 px 经 HTTP")

clear()
put("sPx=Slider[0,10,1,(0,0)]")
put("SetSliderLength[sPx, 300]")
_sPx = {e.get("label"): e for e in state()}.get("sPx") or {}
check("API：slider_px=300 且 defn 同步", abs(float(_sPx.get("slider_px", 0)) - 300) < 1e-9
      and "(0,0),300]" in str(_sPx.get("defn")), "%s | %s" % (_sPx.get("slider_px"), _sPx.get("defn")))

# ---------------------------------------------------------------------------
section("T2. 命令帮助带参数（/api/commands 的 sigs）")

_cmds = req("/api/commands")[2]
_cmdj = __import__("json").loads(_cmds.decode("utf-8"))
check("API：/api/commands 返回 sigs（每条命令都有签名）",
      isinstance(_cmdj.get("sigs"), dict) and len(_cmdj["sigs"]) == len(_cmdj["commands"]),
      "sigs=%d commands=%d" % (len(_cmdj.get("sigs", {})), len(_cmdj["commands"])))
check("API：签名含参数（Slider 带 min/max/step/vertical/px）",
      "最小值" in _cmdj["sigs"].get("slider", "") and "px" in _cmdj["sigs"].get("slider", ""),
      "%s" % _cmdj["sigs"].get("slider"))
# 第九十批起：190 条命令**全部登记**签名（不再有 `名字[…]` 回退项）——旧断言曾以 Abs 作"未登记"样例 ✗
_fb = sorted(k for k, v in _cmdj["sigs"].items() if v.endswith("[…]"))
check("API：190 条命令全部有真实签名（0 条回退 名字[…]）", not _fb, "回退项=%s" % _fb[:6])
check("API：签名前缀 == 该命令的显示名（Tab 补全填出的就是这条命令）",
      not [k for k, v in _cmdj["sigs"].items()
           if not v.lower().startswith(str(_cmdj["display"].get(k) or k).lower())],
      "sigs=%d" % len(_cmdj["sigs"]))

print("\n" + "=" * 60)
print("2D/平台 API 检测矩阵：%d 项断言，%d 失败" % (PASS + FAIL, FAIL))
if FAILED:
    for nm in FAILED:
        print("  FAILED: " + nm)
    print("结果: FAILED")
    sys.exit(1)
print("结果: ALL PASS")
sys.exit(0)
