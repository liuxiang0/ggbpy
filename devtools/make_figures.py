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


def P3(label: str, x: float, y: float, z: float) -> str:
    """三维点：`label=(x,y,z)`（标签同样必须大写开头）。"""
    return "%s=(%.4f,%.4f,%.4f)" % (label, x, y, z)


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


# ---------------------------------------------------------------------------
# 图三：自行车（2D）—— 双圆轮 + Rorate 复制辐条 + 线段车架 + 正多边形脚踏 + 折线链条
# ---------------------------------------------------------------------------
def bike_script() -> list[str]:
    s: list[str] = [P("O", 0, 0)]
    RWH, FWH, WR = (-2.6, 0.0), (2.6, 0.0), 1.0
    # —— 轮圈 + 花鼓 ——
    s += [P("RW", *RWH), "rimR=Circle[RW,1.0]", 'SetColor[rimR,"#111827"]',
          P("FW", *FWH), "rimF=Circle[FW,1.0]", 'SetColor[rimF,"#111827"]',
          "hubR=Circle[RW,0.13]", 'SetColor[hubR,"#6b7280"]',
          "hubF=Circle[FW,0.13]", 'SetColor[hubF,"#6b7280"]']
    # —— 辐条：造 1 根 → Rotate 复制 11 根（每轮 12 根，30° 一步）——
    s += [P("SR", RWH[0] + WR, RWH[1]), "spokeR0=Segment[RW,SR]", 'SetColor[spokeR0,"#9ca3af"]',
          P("SF", FWH[0] + WR, FWH[1]), "spokeF0=Segment[FW,SF]", 'SetColor[spokeF0,"#9ca3af"]']
    for k in range(1, 12):
        s += ["spokeR%d=Rotate[spokeR0,%d,RW]" % (k, 30 * k), 'SetColor[spokeR%d,"#9ca3af"]' % k,
              "spokeF%d=Rotate[spokeF0,%d,FW]" % (k, 30 * k), 'SetColor[spokeF%d,"#9ca3af"]' % k]
    # —— 车架：钻石架（链支/座支/座管/下管/上管/头管/前叉）——
    s += [P("BB", -0.15, -0.55), P("ST", -1.45, 1.30), P("HB", 2.05, 0.60), P("HT", 1.85, 1.15)]
    frame = [("chainstay", "RW", "BB"), ("seatstay", "RW", "ST"), ("seattube", "BB", "ST"),
             ("downtube", "BB", "HB"), ("toptube", "ST", "HT"), ("headtube", "HB", "HT"),
             ("fork", "HB", "FW")]
    for lab, a, b in frame:
        s += ["%s=Segment[%s,%s]" % (lab, a, b), 'SetColor[%s,"#dc2626"]' % lab]
    # —— 鞍座（多边形）+ 座管 ——
    s += [P("SD", -1.55, 1.45), "seatpost=Segment[ST,SD]", 'SetColor[seatpost,"#dc2626"]',
          P("SA1", -2.05, 1.52), P("SA2", -1.05, 1.58), P("SA3", -1.12, 1.70), P("SA4", -2.02, 1.72),
          "saddle=Polygon[SA1,SA2,SA3,SA4]", 'SetColor[saddle,"#1f2937"]']
    # —— 车把（立管 + 横把 + 把套）——
    s += [P("H1", 1.92, 1.62), P("H2", 1.60, 1.66), "stem=Segment[HT,H1]", 'SetColor[stem,"#dc2626"]',
          "bar=Segment[H1,H2]", 'SetColor[bar,"#111827"]',
          "grip=Circle[H2,0.07]", 'SetColor[grip,"#1f2937"]',
          # 水壶（椭圆，挂在立管旁）
          P("BT1", 0.70, -0.05), P("BT2", 1.00, 0.10), P("BTP", 0.92, -0.06),
          "bottle=Ellipse[BT1,BT2,BTP]", 'SetColor[bottle,"#0ea5e9"]']
    # —— 传动：牙盘 + 飞轮 + 链条（上下两段）+ 曲柄 + 脚踏（正四边形，旋转 180° 出另一只）——
    s += ["chainring=Circle[BB,0.32]", 'SetColor[chainring,"#6b7280"]',
          "cog=Circle[RW,0.16]", 'SetColor[cog,"#6b7280"]',
          P("CH1", -0.15, -0.23), P("CH2", -2.60, 0.16), "chainT=Segment[CH1,CH2]",
          P("CH3", -0.15, -0.87), P("CH4", -2.60, -0.16), "chainB=Segment[CH3,CH4]",
          'SetColor[chainT,"#4b5563"]', 'SetColor[chainB,"#4b5563"]',
          P("PD1", 0.01, -0.27), "crank1=Segment[BB,PD1]", 'SetColor[crank1,"#374151"]',
          "crank2=Rotate[crank1,180,BB]", 'SetColor[crank2,"#374151"]',
          P("PA1", 0.01, -0.35), P("PA2", 0.17, -0.35), "pedal1=RegularPolygon[PA1,PA2,4]",
          'SetColor[pedal1,"#f59e0b"]',
          "pedal2=Rotate[pedal1,180,BB]", 'SetColor[pedal2,"#f59e0b"]']
    # —— 地面 + 标题 ——
    s += [P("GD1", -5.2, -1.05), P("GD2", 5.2, -1.05), "ground=Segment[GD1,GD2]",
          'SetColor[ground,"#9ca3af"]',
          'Text["自行车 · ggbpy", (-5.0,2.75)]']
    return hide_points(s)


# ---------------------------------------------------------------------------
# 图四：3D 小屋与庭院（立方体房 + 三棱柱屋顶 + 圆柱/圆锥/球 + 平面地面 + 求交截面 + 正十二面体）
#    注意：3D 基元的真实语义与「多边形+高度」无关 ——
#      Cube[点,点]（棱长=|AB|，沿 +y+z 挤出）· Prism[点,点,点]（三棱柱，高=|AB|，沿 −y 挤出）
#      Cylinder[底心, 底半径点, 顶心] · Cone[底心, 底半径点, 顶点] · Sphere[球心, 半径]
# ---------------------------------------------------------------------------
def scene3d_script() -> list[str]:
    """一幅 3D「庭院陈列」：沿 x 轴一字排开，避免遮挡；机位由 FIGURES 的 yaw/pitch 定。"""
    s: list[str] = [P("O", 0, 0)]
    # —— 房身（立方体，棱长 2.6）+ 屋顶（三棱柱：截面三角形在 y=+1.3，向 −y 挤出 3.0 成双坡）——
    s += [P3("A", -4.2, -1.3, 0), P3("B", -1.6, -1.3, 0), "house=Cube[A,B]",
          'SetColor[house,"#fef3c7"]',
          P3("R1", -4.4, 1.3, 2.6), P3("R2", -1.4, 1.3, 2.6), P3("R3", -2.9, 1.3, 3.8),
          "roof=Prism[R1,R2,R3]", 'SetColor[roof,"#b45309"]',
          P3("K1", -3.35, -0.55, 2.95), P3("K2", -2.9, -0.55, 2.95), "chimney=Cube[K1,K2]",
          'SetColor[chimney,"#94a3b8"]']
    # —— 树（圆柱干 + 球冠）——
    s += [P3("T1", 0.6, 0.3, 0), P3("TR", 0.82, 0.3, 0), P3("T2", 0.6, 0.3, 1.3),
          "trunk=Cylinder[T1,TR,T2]", 'SetColor[trunk,"#92400e"]',
          P3("C1", 0.6, 0.3, 2.0), "canopy=Sphere[C1,0.95]", 'SetColor[canopy,"#22c55e"]']
    # —— 松树（圆锥）——
    s += [P3("P1", 2.6, 0.3, 0), P3("PR", 3.05, 0.3, 0), P3("P2", 2.6, 0.3, 2.2),
          "pine=Cone[P1,PR,P2]", 'SetColor[pine,"#15803d"]']
    # —— 喷泉（圆柱水池 + 圆锥水柱）——
    s += [P3("F1", 4.6, 0.3, 0), P3("FR", 5.25, 0.3, 0), P3("F2", 4.6, 0.3, 0.35),
          "basin=Cylinder[F1,FR,F2]", 'SetColor[basin,"#60a5fa"]',
          P3("J1", 4.6, 0.3, 0.35), P3("JR", 4.78, 0.3, 0.35), P3("J2", 4.6, 0.3, 1.5),
          "jet=Cone[J1,JR,J2]", 'SetColor[jet,"#7dd3fc"]']
    # —— 前排摆件：四种正多面体（正四面体 / 正八面体 / 正十二面体 / 正二十面体）——
    s += [P3("TA", -4.9, -3.2, 0), P3("TB", -4.3, -3.2, 0), P3("TC", -4.6, -2.9, 0.6),
          "tetra=Tetrahedron[TA,TB,TC]", 'SetColor[tetra,"#f472b6"]',
          P3("OA", -3.5, -3.2, 0.55), P3("OB", -3.1, -3.2, 0.55), P3("OC", -3.5, -2.8, 0.95),
          "octa=Octahedron[OA,OB,OC]", 'SetColor[octa,"#a855f7"]',
          P3("DA", -2.1, -3.2, 0.55), P3("DB", -1.7, -3.2, 0.55), P3("DC", -2.1, -2.8, 0.95),
          "dodeca=Dodecahedron[DA,DB,DC]", 'SetColor[dodeca,"#0ea5e9"]',
          P3("IA", -0.7, -3.2, 0.55), P3("IB", -0.3, -3.2, 0.55), P3("IC", -0.7, -2.8, 0.95),
          "icosa=Icosahedron[IA,IB,IC]", 'SetColor[icosa,"#f59e0b"]']
    # —— 太阳（球，高空）——
    s += [P3("U1", -5.2, 2.3, 3.2), "sun=Sphere[U1,0.6]", 'SetColor[sun,"#fbbf24"]']
    # —— 求交演示：水平切面 × 树冠球 → 空间圆（切面本身隐藏）——
    s += [P3("X1", 0.6, -3, 2.0), P3("X2", 0.6, 3, 2.0), P3("X3", 3, 0.3, 2.0), "cut=Plane[X1,X2,X3]",
          "SetVisible[cut,false]", "sect=Intersect[cut,canopy]", 'SetColor[sect,"#dc2626"]']
    # —— 地面（平面；尺寸要贴近场景，否则自动取景会被它撑大）——
    s += [P3("G1", -4.6, -3.5, 0), P3("G2", 5.4, -3.5, 0), P3("G3", 5.4, 2.4, 0),
          "ground=Plane[G1,G2,G3]", 'SetColor[ground,"#e5e7eb"]']
    return hide_points(s)


FIGURES = {
    "cat": {"script": cat_script, "view": (-6.4, 6.4, -4.9, 5.7), "title": "小猫（点/线/面/圆/椭圆/参数曲线/正多边形/镜像）"},
    "house": {"script": house_script, "view": (-8.2, 8.2, -4.9, 6.1), "title": "小屋与花园（多边形/正多边形/圆/椭圆/抛物线/旋转/缩放）"},
    "bike": {"script": bike_script, "view": (-5.3, 5.3, -1.5, 3.1), "title": "自行车（圆/线段车架/正多边形脚踏/Rotate 复制辐条/折线链条）"},
    "scene3d": {"script": scene3d_script, "view": None, "yaw": -0.72, "pitch": -0.45,
                "title": "3D 小屋与庭院（立方体+三棱柱屋顶 / 圆柱+球 / 圆锥 / 平面 / 四种正多面体 / 平面×球求交）"},
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
    # 导出：2D 按图形视口裁剪；3D 走正交投影（view3d=1）
    if cfg["view"]:
        xmin, xmax, ymin, ymax = cfg["view"]
        q = "xmin=%g&xmax=%g&ymin=%g&ymax=%g" % (xmin, xmax, ymin, ymax)
    else:
        q = "view3d=1&yaw=%g&pitch=%g" % (cfg.get("yaw", -0.62), cfg.get("pitch", -0.52))
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
    ap.add_argument("--only", default="", help="只生成某幅（cat / house / bike / scene3d）")
    a = ap.parse_args()
    names = [a.only] if a.only else list(FIGURES)
    print("服务：%s" % a.base)
    for name in names:
        info = build(a.base, name)
        w, h = render_png(name)
        print("\n【%s】%s" % (name, FIGURES[name]["title"]))
        print("  脚本 %d 行 / 元素 %d 个 / 类型 %s" % (info["lines"], info["elements"], info["kinds"]))
        where = ("视口 %s" % (info["view"],)) if info["view"] else "3D 正交投影（view3d=1）"
        print("  %s → SVG+GGK+PNG 已写入 share/figures/（预览 %dx%d）" % (where, w, h))
    return 0


if __name__ == "__main__":
    sys.exit(main())
