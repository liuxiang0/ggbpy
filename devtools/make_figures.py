#!/usr/bin/env python3
"""生成两幅 2D 合成图形（小猫 / 小屋·花园），用于展示 ggbpy 的 2D 能力。

注意：**点标签必须大写开头** —— `kernel/parser.py` 规定 `label=(x,y)` 且 label 首字母小写
会建成**向量**（GeoGebra 惯例），本轮踩过：`f1=(-1.6,-3.3)` 得到的不是点 ✗

覆盖：点、线段、多边形（面）、圆、圆锥曲线（椭圆/抛物线）、正多边形、
参数曲线、变换（Reflect/Rotate/Dilate）、文字、颜色、虚线隐藏辅助线。

产物（`share/figures/`）：
    <name>.svg   —— 矢量导出（由 `/api/export/svg` 按图形视口裁剪）
    <name>.ggk   —— 自有工程文件（可「加载」回 ggbpy，含视口）
    <name>.png   —— 预览位图（把 SVG 用 Chromium 渲染后截图；本机无 rsvg/cairosvg）

用法：python3 devtools/make_figures.py [--base http://127.0.0.1:8090] [--only cat|house]
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import re
import sys
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "share" / "figures"
DEFAULT_BASE = "http://127.0.0.1:8090"


def P(label: str, x: float, y: float) -> str:
    return "%s=(%.4f,%.4f)" % (label, x, y)


def circ(cx: float, cy: float, r: float, deg: float) -> tuple[float, float]:
    a = math.radians(deg)
    return (cx + r * math.cos(a), cy + r * math.sin(a))


# ---------------------------------------------------------------------------
# 图一：小猫（圆头 + 三角耳 + 椭圆身 + 参数曲线尾巴 + 正多边形铃铛）
# ---------------------------------------------------------------------------
def cat_script() -> list[str]:
    s: list[str] = []
    s += [P("O", 0, 0)]                                    # 记原点（供旋转/缩放中心用）
    # —— 地面阴影（先画，被身体压住）——
    s += [P("F1", -1.6, -3.35), P("F2", 1.6, -3.35), P("PS", 0, -3.15),
          "shadow=Ellipse[F1,F2,PS]", 'SetColor[shadow,"#e5e7eb"]']
    # —— 尾巴：参数曲线（t∈[0,1] 的 S 形）——
    s += ["tail=Parametric[2.0+1.15*sin(2*pi*t), -2.6+3.1*t+0.25*sin(4*pi*t), t, 0, 1]",
          'SetColor[tail,"#f97316"]']
    # —— 身体：椭圆（圆锥曲线，焦点法）——
    s += [P("BF1", -1.0, -1.75), P("BF2", 1.0, -1.75), P("BP", 0, -3.35),
          "body=Ellipse[BF1,BF2,BP]", 'SetColor[body,"#fb923c"]']
    # —— 前爪：半圆 ——
    s += [P("PW1", -1.35, -3.85), P("PW2", -0.45, -3.85), "pawL=Semicircle[PW1,PW2]",
          P("PW3", 0.45, -3.85), P("PW4", 1.35, -3.85), "pawR=Semicircle[PW3,PW4]",
          'SetColor[pawL,"#fdba74"]', 'SetColor[pawR,"#fdba74"]']
    # —— 头：圆 ——
    s += [P("H", 0, 1.15), "head=Circle[H,1.85]", 'SetColor[head,"#fb923c"]']
    # —— 耳朵：多边形 + 镜像（左耳造好 → Reflect）——
    s += [P("L1", -1.60, 2.05), P("L2", -0.62, 2.72), P("L3", -1.28, 4.05),
          "earL=Polygon[L1,L2,L3]", 'SetColor[earL,"#fb923c"]',
          "_ax=Line[(0,-6),(0,6)]", "SetVisible[_ax,false]",
          "earR=Reflect[earL,_ax]", 'SetColor[earR,"#fb923c"]',
          # 内耳（小三角，粉色）
          P("L4", -1.38, 2.48), P("L5", -1.02, 2.78), P("L6", -1.26, 3.45),
          "inL=Polygon[L4,L5,L6]", 'SetColor[inL,"#fda4af"]',
          "inR=Reflect[inL,_ax]", 'SetColor[inR,"#fda4af"]']
    # —— 眼睛：圆 + 瞳孔圆 + 高光点（点要素）——
    s += [P("EL", -0.62, 1.72), "eyeL=Circle[EL,0.34]", 'SetColor[eyeL,"#ffffff"]',
          P("ER", 0.62, 1.72), "eyeR=Circle[ER,0.34]", 'SetColor[eyeR,"#ffffff"]',
          P("PL", -0.62, 1.70), "pupL=Circle[PL,0.17]", 'SetColor[pupL,"#111827"]',
          P("PR", 0.62, 1.70), "pupR=Circle[PR,0.17]", 'SetColor[pupR,"#111827"]',
          P("HL", -0.70, 1.78), 'SetColor[HL,"#ffffff"]',
          P("HR", 0.54, 1.78), 'SetColor[HR,"#ffffff"]']
    # —— 鼻子（多边形）与嘴（圆弧：Arc[起点, 终点, 圆心]，圆心在最后）——
    s += [P("N1", -0.20, 1.02), P("N2", 0.20, 1.02), P("N3", 0, 0.78),
          "nose=Polygon[N1,N2,N3]", 'SetColor[nose,"#f472b6"]',
          P("M1", -0.46, 0.62), P("M2", 0.46, 0.62), P("MC", 0, 1.00),
          "mouth=Arc[M1,M2,MC]", 'SetColor[mouth,"#7c2d12"]']
    # —— 胡须：三条线段 + 镜像 ——
    w = [(-0.22, 0.92, -2.05, 1.28), (-0.22, 0.84, -2.15, 0.80), (-0.22, 0.76, -2.00, 0.32)]
    for i, (x1, y1, x2, y2) in enumerate(w):
        s += [P("W%dA" % i, x1, y1), P("W%dB" % i, x2, y2), "WL%d=Segment[W%dA,W%dB]" % (i, i, i),
              'SetColor[WL%d,"#78350f"]' % i, "WR%d=Reflect[WL%d,_ax]" % (i, i),
              'SetColor[WR%d,"#78350f"]' % i]
    # —— 项圈 + 铃铛（正五边形）——
    s += [P("C1", -1.05, -0.55), P("C2", 1.05, -0.55), "collar=Segment[C1,C2]",
          'SetColor[collar,"#dc2626"]',
          P("B1", -0.22, -0.95), P("B2", 0.22, -0.95), "bell=RegularPolygon[B1,B2,5]",
          'SetColor[bell,"#facc15"]']
    # —— 标题 ——
    s += ['Text["小猫 · ggbpy", (-5.5,5.1)]']
    return hide_points(s)


def hide_points(script: list[str]) -> list[str]:
    """隐藏所有辅助点：图里只留几何形体，**不显示 L1/W0B 这类点标签**（更干净）。"""
    out = list(script)
    for line in script:
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=\([^)]*\)$", line)
        if m:
            out.append("SetVisible[%s,false]" % m.group(1))
    return out


# ---------------------------------------------------------------------------
# 图二：小屋与花园（多边形房子 + 正多边形窗 + 旋转太阳光线 + 椭圆树冠 + 抛物线喷泉 + 旋转花瓣）
# ---------------------------------------------------------------------------
def house_script() -> list[str]:
    s: list[str] = []
    s += [P("O", 0, 0)]
    # —— 太阳：圆 + 8 条光线（Rotate 45° 复制）——
    s += [P("S", 6.0, 4.5), "sun=Circle[S,0.72]", 'SetColor[sun,"#fbbf24"]',
          P("R1", 6.0, 5.32), P("R2", 6.0, 5.86), "ray0=Segment[R1,R2]",
          'SetColor[ray0,"#f59e0b"]']
    for k in range(1, 8):
        s += ["ray%d=Rotate[ray0,%d,S]" % (k, 45 * k), 'SetColor[ray%d,"#f59e0b"]' % k]
    # —— 云：三个圆（互叠）——
    for i, (cx, cy, r) in enumerate([(-4.8, 4.5, 0.55), (-4.1, 4.8, 0.7), (-3.4, 4.5, 0.5)]):
        s += [P("CL%d" % i, cx, cy), "cloud%d=Circle[CL%d,%.2f]" % (i, i, r),
              'SetColor[cloud%d,"#e2e8f0"]' % i]
    # —— 草地（多边形，面）——
    s += [P("G1", -8, -4.6), P("G2", 8, -4.6), P("G3", 8, -1.35), P("G4", -8, -1.35),
          "grass=Polygon[G1,G2,G3,G4]", 'SetColor[grass,"#86efac"]']
    # —— 房身 / 屋顶 / 烟囱 ——
    s += [P("H1", -5.4, -1.35), P("H2", -1.0, -1.35), P("H3", -1.0, 1.55), P("H4", -5.4, 1.55),
          "walls=Polygon[H1,H2,H3,H4]", 'SetColor[walls,"#fef3c7"]',
          P("T1", -6.0, 1.55), P("T2", -3.2, 3.75), P("T3", -0.4, 1.55),
          "roof=Polygon[T1,T2,T3]", 'SetColor[roof,"#b45309"]',
          P("K1", -4.9, 2.35), P("K2", -4.2, 2.35), P("K3", -4.2, 3.55), P("K4", -4.9, 3.55),
          "chimney=Polygon[K1,K2,K3,K4]", 'SetColor[chimney,"#94a3b8"]',
          P("SU1", -4.9, 3.95), "smoke1=Circle[SU1,0.28]", 'SetColor[smoke1,"#e5e7eb"]',
          P("SU2", -4.35, 4.45), "smoke2=Circle[SU2,0.22]", 'SetColor[smoke2,"#f1f5f9"]']
    # —— 门 + 门把手 ——
    s += [P("D1", -4.4, -1.35), P("D2", -3.0, -1.35), P("D3", -3.0, 0.55), P("D4", -4.4, 0.55),
          "door=Polygon[D1,D2,D3,D4]", 'SetColor[door,"#92400e"]',
          P("DH", -3.25, -0.35), "knob=Circle[DH,0.09]", 'SetColor[knob,"#facc15"]']
    # —— 窗（正四边形）+ 窗棂 ——
    s += [P("V1", -2.5, 0.05), P("V2", -1.55, 0.05), "win=RegularPolygon[V1,V2,4]",
          'SetColor[win,"#93c5fd"]',
          P("V3", -2.44, 0.05), P("V4", -1.61, 0.05), "winH=Segment[V3,V4]",
          P("V5", -2.025, -0.42), P("V6", -2.025, 0.52), "winV=Segment[V5,V6]",
          'SetColor[winH,"#1e3a8a"]', 'SetColor[winV,"#1e3a8a"]']
    # —— 树：树干多边形 + 树冠椭圆（+ Dilate 出的亮面）——
    s += [P("B1", 1.5, -1.35), P("B2", 2.5, -1.35), P("TR3", 2.35, 0.85), P("TR4", 1.65, 0.85),
          "trunk=Polygon[B1,B2,TR3,TR4]", 'SetColor[trunk,"#92400e"]',
          P("CF1", 1.5, 2.0), P("CF2", 2.5, 2.0), P("CP", 2.0, 3.6),
          "canopy=Ellipse[CF1,CF2,CP]", 'SetColor[canopy,"#22c55e"]',
          P("CT", 2.6, 2.9), "canopy2=Dilate[canopy,0.62,CT]", 'SetColor[canopy2,"#4ade80"]']
    # —— 喷泉：水池椭圆 + 抛物线水柱（圆锥曲线）+ 水花 ——
    s += [P("PF1", 4.0, -2.85), P("PF2", 6.4, -2.85), P("PP", 5.2, -2.05),
          "pool=Ellipse[PF1,PF2,PP]", 'SetColor[pool,"#60a5fa"]',
          P("DL1", 3.0, -2.85), P("DL2", 7.4, -2.85), "_dl=Line[DL1,DL2]",
          "SetVisible[_dl,false]",
          P("PFOC", 5.2, -2.42), "jet=Parabola[PFOC,_dl]", 'SetColor[jet,"#38bdf8"]',
          P("SP1", 5.2, 0.35), "spray=Circle[SP1,0.22]", 'SetColor[spray,"#7dd3fc"]']
    # —— 花：椭圆花瓣 ×6（Rotate）+ 花心 ——
    s += [P("F", -1.4, -2.6), P("PFA1", -1.4, -3.75), P("PFA2", -1.4, -1.45), P("PPA", -1.62, -2.6),
          "petal0=Ellipse[PFA1,PFA2,PPA]", 'SetColor[petal0,"#f472b6"]']
    for k in range(1, 6):
        s += ["petal%d=Rotate[petal0,%d,F]" % (k, 60 * k), 'SetColor[petal%d,"#f9a8d4"]' % k]
    s += ["core=Circle[F,0.24]", 'SetColor[core,"#facc15"]']
    # —— 小路（折线）——
    s += [P("Q1", -2.6, -1.35), P("Q2", -1.9, -2.3), P("Q3", -2.4, -3.3), P("Q4", -1.5, -4.6),
          "path=Polyline[Q1,Q2,Q3,Q4]", 'SetColor[path,"#d6d3d1"]']
    # —— 标题 ——
    s += ['Text["小屋与花园 · ggbpy", (-7.8,5.35)]']
    return hide_points(s)


FIGURES = {
    "cat": {"script": cat_script, "view": (-6.4, 6.4, -4.9, 5.7), "title": "小猫（点/线/面/圆/椭圆/参数曲线/正多边形/镜像）"},
    "house": {"script": house_script, "view": (-8.2, 8.2, -4.9, 6.1), "title": "小屋与花园（多边形/正多边形/圆/椭圆/抛物线/旋转/缩放）"},
}


def req(base: str, path: str, sid: str, data=None, raw=False, timeout=30):
    url = base + path + ("&" if "?" in path else "?") + "sid=" + urllib.parse.quote(sid)
    body = json.dumps(data).encode() if data is not None else None
    r = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=timeout) as f:
        return f.read() if raw else json.loads(f.read().decode("utf-8"))


def build(base: str, name: str) -> dict:
    cfg = FIGURES[name]
    sid = "fig-" + name
    req(base, "/api/clear", sid, data={})
    script = cfg["script"]()
    res = req(base, "/api/batch", sid, data={"script": "\n".join(script)})
    bad = [r for r in res["results"] if not r["ok"]]
    if bad:
        for b in bad:
            print("  ✗ 第%d行 %s → %s" % (b["no"], b["line"], b["message"]))
        raise SystemExit("图形「%s」有 %d 行失败，未导出" % (name, len(bad)))
    st = req(base, "/api/state", sid)
    kinds: dict[str, int] = {}
    for e in st["elements"]:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    # 导出（按图形视口裁剪）
    xmin, xmax, ymin, ymax = cfg["view"]
    q = "xmin=%g&xmax=%g&ymin=%g&ymax=%g" % (xmin, xmax, ymin, ymax)
    svg = req(base, "/api/export/svg?" + q, sid, raw=True).decode("utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / (name + ".svg")).write_text(svg, encoding="utf-8")
    ggk = req(base, "/api/download?" + q, sid, raw=True).decode("utf-8")
    (OUT / (name + ".ggk")).write_text(ggk, encoding="utf-8")
    return {"name": name, "lines": len(script), "elements": st["count"], "kinds": kinds, "view": cfg["view"]}


def render_png(name: str) -> tuple[int, int]:
    """把导出的 SVG 渲染成 PNG 预览（本机无 rsvg/cairosvg → 用项目里的 Node playwright-core）。"""
    import subprocess
    svg_path = OUT / (name + ".svg")
    png_path = OUT / (name + ".png")
    svg2png = pathlib.Path(__file__).resolve().parent / "_svg2png.js"
    r = subprocess.run(["node", str(svg2png), str(svg_path), str(png_path), "2"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("PNG 渲染失败：\n" + (r.stderr or r.stdout)[-400:])
    info = json.loads(r.stdout.strip().split("\n")[-1])
    return int(info["w"]), int(info["h"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--only", default="", help="只生成某幅（cat / house）")
    a = ap.parse_args()
    names = [a.only] if a.only else list(FIGURES)
    print("服务：%s" % a.base)
    for name in names:
        info = build(a.base, name)
        w, h = render_png(name)
        print("\n【%s】%s" % (name, FIGURES[name]["title"]))
        print("  脚本 %d 行 / 元素 %d 个 / 类型 %s" % (info["lines"], info["elements"], info["kinds"]))
        print("  视口 %s → SVG+GGK+PNG 已写入 share/figures/（预览 %dx%d）" % (info["view"], w, h))
    return 0


if __name__ == "__main__":
    sys.exit(main())
