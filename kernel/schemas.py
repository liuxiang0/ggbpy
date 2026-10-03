"""元素 data 载荷 schema：集中定义 3D 元素的 ``objtype``/``solid``/``data`` 结构。

背景：REVIEW_12_BATCHES.md 指出 ``data`` 约定散落各处（内核里二十余处内联
``{"objtype": …}``），键名靠约定与记忆。这里统一构造，新增元素类型只改本模块；
``devtools/test_modules.py`` 会扫描 ``kernel/`` 源码，阻止再次内联 ``"objtype":`` 字面量
（读取 ``getattr(el, "objtype")`` 不受影响）。

键顺序刻意与历史输出保持一致（``objtype`` → ``solid`` → ``data``），避免无谓地
改变 ``/api/state3d`` 载荷与状态指纹。
"""

from __future__ import annotations

from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# 基础 3D 图元
# ---------------------------------------------------------------------------

def line3d(x1: float, y1: float, z1: float, x2: float, y2: float, z2: float) -> Dict:
    """无限直线（以两个端点表示延伸方向）。"""
    return {"objtype": "line3d",
            "data": {"x1": x1, "y1": y1, "z1": z1, "x2": x2, "y2": y2, "z2": z2}}


def segment3d(x1: float, y1: float, z1: float, x2: float, y2: float, z2: float) -> Dict:
    """三维线段。"""
    return {"objtype": "segment",
            "data": {"x1": x1, "y1": y1, "z1": z1, "x2": x2, "y2": y2, "z2": z2}}


def plane(nx: float, ny: float, nz: float, dd: float,
          ax: float, ay: float, az: float,
          ux: float, uy: float, uz: float,
          vx: float, vy: float, vz: float, **extra) -> Dict:
    """平面：法向 (nx,ny,nz,d) + 原点 (ax,ay,az) + 两正交基向量 u/v。

    ``extra`` 追加额外键（如 FitPlane 的 ``fit=True``）。
    """
    data = {"a": nx, "b": ny, "c": nz, "d": dd,
            "ax": ax, "ay": ay, "az": az, "ux": ux, "uy": uy, "uz": uz,
            "vx": vx, "vy": vy, "vz": vz}
    data.update(extra)
    return {"objtype": "plane", "solid": "plane", "data": data}


def sphere(cx: float, cy: float, cz: float, r: float) -> Dict:
    """球（圆心 + 半径）。"""
    return {"objtype": "sphere", "solid": "sphere",
            "data": {"cx": cx, "cy": cy, "cz": cz, "r": r}}


def circle3d(cx: float, cy: float, cz: float, r: float,
             normal: List[float], u: List[float], v: List[float]) -> Dict:
    """空间圆：圆心 + 半径 + 法向 + 平面内两基向量。"""
    return {"objtype": "circle3d",
            "data": {"cx": cx, "cy": cy, "cz": cz, "r": r,
                     "normal": list(normal), "u": list(u), "v": list(v)}}


def section(pts: List[List[float]], normal: List[float]) -> Dict:
    """截面（平面与立体的交集多边形）。"""
    return {"objtype": "section",
            "data": {"pts": pts, "normal": list(normal), "count": len(pts)}}


def curve3d(segs: List[List[float]]) -> Dict:
    """三维曲线（线段集合）。"""
    return {"objtype": "curve3d", "data": {"segs": segs, "count": len(segs)}}


# ---------------------------------------------------------------------------
# 多面体 / 网格 / 立方体 / 曲面 / 三维统计图
# ---------------------------------------------------------------------------

def polyhedron(verts: Optional[List] = None, faces: Optional[List] = None,
               edges: Optional[List] = None, solid: str = "",
               mesh: Optional[Dict] = None, **extra) -> Dict:
    """多面体/网格载荷。

    ``mesh`` 给出完整 data 字典（如体×体凸交已算好的 verts/faces/edges）时直接使用，
    否则由 ``verts/faces/edges`` 组成；``extra`` 追加额外键（lo/hi、points、grid、expr、
    param、center、axes、ranges 等），``solid`` 非空时写出（cube/hull/surface/mesh/chart_*）。
    """
    if mesh is not None:
        data = dict(mesh)
    else:
        data = {"verts": verts, "faces": faces, "edges": edges}
    data.update(extra)
    out: Dict = {"objtype": "polyhedron"}
    if solid:
        out["solid"] = solid
    out["data"] = data
    return out


def surface(verts: List, faces: List, edges: List, grid: int, **extra) -> Dict:
    """显式/参数/隐式曲面（polyhedron + solid=surface）。"""
    return polyhedron(verts, faces, edges, solid="surface", grid=grid, **extra)


def cube(verts: List, faces: List, edges: List) -> Dict:
    """立方体（真实 solid=cube，前端按 box 渲染）。"""
    return {"objtype": "cube", "solid": "cube",
            "data": {"verts": verts, "faces": faces, "edges": edges}}


def chart3d(solid: str, verts: List, faces: List, edges: List) -> Dict:
    """三维统计图网格（chart_bar3d / chart_scatter3d / chart_surface3d）。"""
    return polyhedron(verts, faces, edges, solid=solid)


__all__ = [
    "line3d", "segment3d", "plane", "sphere", "circle3d", "section", "curve3d",
    "polyhedron", "surface", "cube", "chart3d",
]
