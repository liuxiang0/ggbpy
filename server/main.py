"""ggbpy P0 —— FastAPI 服务。

API：
  GET  /                   前端页面
  GET  /api/state          当前构造（含函数采样，需传视口范围）
  POST /api/input          执行一条代数输入
  POST /api/drag           拖动自由点（增量重算）
  POST /api/undo /api/redo /api/clear /api/demo
  GET  /api/download       导出 .ggb（XML）
  POST /api/load           导入（.ggb XML 或自有 JSON）
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from kernel.construction import Construction, DEFAULT_VIEW
from kernel.cas import CASEngine

from server.sessions import (SessionMiddleware, current_session, get_session,
                             resolve_sid, session_stats, sweep)

app = FastAPI(title="ggbpy · Python 动态几何")
# 大网格 state3d 载荷可达 1–2 MB：>1KB 自动 gzip（浏览器 fetch 默认带 Accept-Encoding）
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(SessionMiddleware)

import hashlib as _hashlib
import json as _json
import threading as _threading

# ---- /api/state3d 增量协议 -------------------------------------------------
# rev 由服务端在请求时惰性分配：指纹变化 → rev+1，并留存最近若干 rev 的指纹表。
# 客户端带 ?since=<上次 rev>：返回 changed/removed 增量；rev 未变返回 unchanged。
class _SessProxy:
    """按当前请求会话解析属性的代理（端点代码保持 `cons.xxx` / `cas.xxx` 写法不变）。"""

    def __init__(self, attr: str) -> None:
        object.__setattr__(self, "_attr", attr)

    def __getattr__(self, name):
        return getattr(getattr(current_session(), object.__getattribute__(self, "_attr")), name)


class _SdProxy:
    """state3d 增量状态（per-session）：支持 `_SD["rev"] += 1` 这样的读写。"""

    def __getitem__(self, k):
        return current_session().sd[k]

    def __setitem__(self, k, v):
        current_session().sd[k] = v

    def get(self, k, default=None):
        return current_session().sd.get(k, default)


_SD = _SdProxy()
# 全局构造是共享单例：所有变更串行化，避免并发请求交错破坏 DAG
_cons_lock = _threading.Lock()


def _mut(fn, *a, **kw):
    """在当前会话的构造上串行执行一次变更（端点跑在线程池里，不阻塞事件循环）。

    锁按会话划分：不同会话互不阻塞；同一会话的并发写仍被串行化，避免交错破坏 DAG。
    """
    return current_session().mut(fn, *a, **kw)
_SD_HIST_MAX = 64


def _fp_walk(obj, out, depth=0):
    """把任意 JSON 结构折成紧凑指纹片段：字典按键、列表记长度 + 数值校验和。"""
    if depth > 6 or len(out) > 400:
        return
    if isinstance(obj, dict):
        for k in sorted(obj.keys()):
            out.append(str(k))
            _fp_walk(obj[k], out, depth + 1)
    elif isinstance(obj, (list, tuple)):
        out.append("n" + str(len(obj)))
        s = 0.0
        n = 0
        for item in obj[:5000]:
            if isinstance(item, (int, float)) and not isinstance(item, bool):
                s += float(item)
                n += 1
            elif isinstance(item, (list, tuple)):
                for x in item[:4]:
                    if isinstance(x, (int, float)) and not isinstance(x, bool):
                        s += float(x)
                        n += 1
            else:
                _fp_walk(item, out, depth + 1)
        out.append("%.6f/%d" % (s, n))
    else:
        out.append(repr(obj)[:40])


def _state3d_fp(d):
    out = []
    _fp_walk(d, out)
    return _hashlib.md5("|".join(out).encode("utf-8", "replace")).hexdigest()[:12]
STATIC = Path(__file__).parent / "static"
# 注意：这两个名字现在是「当前会话」的代理；真正的对象在 server/sessions.py 里按会话创建
cons = _SessProxy("cons")
cas = _SessProxy("cas")


class InputBody(BaseModel):
    text: str
    xmin: float = -10.0
    xmax: float = 10.0
    ymin: float = -10.0
    ymax: float = 10.0


class DragBody(BaseModel):
    label: str
    x: float = 0.0
    y: float = 0.0
    z: float = None
    xmin: float = -10.0
    xmax: float = 10.0
    ymin: float = -10.0
    ymax: float = 10.0
    push: bool = False


class CasBody(BaseModel):
    text: str
    xmin: float = -10.0
    xmax: float = 10.0
    ymin: float = -10.0
    ymax: float = 10.0


class ShareBody(BaseModel):
    xmin: float = -10.0
    xmax: float = 10.0
    ymin: float = -10.0
    ymax: float = 10.0


class BatchBody(BaseModel):
    script: str
    xmin: float = -10.0
    xmax: float = 10.0
    ymin: float = -10.0
    ymax: float = 10.0


class ShiftBody(BaseModel):
    label: str
    dx: float = 0.0
    dy: float = 0.0
    dz: float = 0.0
    xmin: float = -10.0
    xmax: float = 10.0
    ymin: float = -10.0
    ymax: float = 10.0
    push: bool = False


class ImageBody(BaseModel):
    data: str
    w: int = 0
    h: int = 0


class ReorderBody(BaseModel):
    order: list = []
    xmin: float = -10.0
    xmax: float = 10.0
    ymin: float = -10.0
    ymax: float = 10.0


SHARE_DIR = ROOT / "share"


def _view(b) -> tuple:
    return (b.xmin, b.xmax, b.ymin, b.ymax)


import math


def _clean(o):
    """JSON 序列化前把 NaN/Inf 替换为 None（函数采样中的断点分隔符）。"""
    if isinstance(o, float):
        return None if (math.isnan(o) or math.isinf(o)) else o
    if isinstance(o, list):
        return [_clean(x) for x in o]
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    return o


def _state(view):
    return {"elements": _clean(cons.to_serializable(view)), "count": len(cons.order),
            "can_undo": len(cons._undo) > 0, "can_redo": len(cons._redo) > 0}


@app.get("/")
def index():
    return FileResponse(str(STATIC / "index.html"))


class _NoCacheStatic(StaticFiles):
    """静态资源仍带 ETag/Last-Modified，但要求浏览器每次校验（no-cache → 命中则 304）。

    否则浏览器可能用启发式缓存长期显示旧 JS/CSS：服务端改了前端、用户却"看起来还是老样子"。
    """

    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        resp.headers["Cache-Control"] = "no-cache, must-revalidate"
        return resp


app.mount("/static", _NoCacheStatic(directory=str(STATIC)), name="static")


@app.get("/api/session")
def session_info():
    """当前会话信息 + 全部会话概览（多会话隔离用）。"""
    cur = current_session()
    return {"ok": True, "session": cur.info(), "sessions": session_stats()}


@app.post("/api/session/sweep")
def session_sweep():
    """清理过期会话，返回清理数量。"""
    return {"ok": True, "dropped": sweep(), "sessions": session_stats()}


@app.get("/api/commands")
def commands_list():
    """命令名列表（前端自动补全/帮助）。"""
    from kernel.commands import COMMANDS, DISPLAY_NAMES
    from kernel.signatures import all_signatures
    disp = {k: DISPLAY_NAMES.get(k, k[:1].upper() + k[1:]) for k in COMMANDS}
    return {"commands": sorted(COMMANDS.keys()), "display": disp,
            "sigs": all_signatures(COMMANDS.keys(), disp)}


@app.get("/api/state")
def state(xmin: float = -10.0, xmax: float = 10.0, ymin: float = -10.0, ymax: float = 10.0):
    return _state((xmin, xmax, ymin, ymax))


@app.post("/api/input")
def do_input(b: InputBody):
    msg = _mut(cons.process, b.text)
    return {"ok": msg.startswith("OK"), "message": msg, **_state(_view(b))}


@app.post("/api/drag")
def do_drag(b: DragBody):
    try:
        if b.push:
            # 每次拖拽成为独立撤销步（首条请求带 push）
            _mut(cons.push_history)
        _mut(cons.move, b.label, b.x, b.y, b.z)
        return {"ok": True, "message": "", **_state(_view(b))}
    except Exception as e:  # 防御性捕获：该分支失败不应中断用户操作
        return {"ok": False, "message": str(e), **_state(_view(b))}


@app.post("/api/undo")
def do_undo():
    ok = _mut(cons.undo)
    return {"ok": ok, "message": "已撤销" if ok else "没有可撤销的操作", **_state((-10, 10, -10, 10))}


@app.post("/api/redo")
def do_redo():
    ok = _mut(cons.redo)
    return {"ok": ok, "message": "已重做" if ok else "没有可重做的操作", **_state((-10, 10, -10, 10))}


@app.post("/api/clear")
def do_clear():
    _mut(cons.clear)
    return {"ok": True, "message": "已清空", **_state((-10, 10, -10, 10))}


DEMO_FIGURES = {"cat": "小猫", "house": "小屋与花园", "bike": "自行车", "scene3d": "3D 小屋与庭院"}


@app.post("/api/demo")
def do_demo(name: str = ""):
    """载入示例：不带 name → 内置入门示例；带 name → share/figures/<name>.ggk。

    可用 name：cat / house / bike / scene3d（3D 示例会附带 switch3d 标记，前端据此切到 3D 视图）。
    """
    nm = (name or "").strip()
    if not nm:
        _mut(cons.load_demo)
        return {"ok": True, "message": "已载入示例（拖动 A 观察依赖重算）", **_state((-10, 10, -10, 10))}
    path = ROOT / "share" / "figures" / (nm + ".ggk")
    if nm not in DEMO_FIGURES or not path.exists():
        return {"ok": False, "message": "未知示例：%s（可用：%s）" % (nm, " / ".join(DEMO_FIGURES)),
                **_state((-10, 10, -10, 10))}
    try:
        view = _mut(cons.load_json, path.read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError, TypeError) as e:  # 文件缺失 / JSON 坏数据 / 结构不符：给可读错误
        return {"ok": False, "message": "示例载入失败: " + str(e), **_state((-10, 10, -10, 10))}
    return {"ok": True, "message": "已载入示例：%s" % DEMO_FIGURES[nm], "view": view,
            "switch3d": nm == "scene3d", **_state((-10, 10, -10, 10))}


@app.get("/api/export/svg")
def export_svg(xmin: float = -10.0, xmax: float = 10.0, ymin: float = -10.0, ymax: float = 10.0,
               view3d: int = 0, yaw: float = -0.62, pitch: float = -0.52):
    """SVG 导出：默认 2D 视图；view3d=1 输出 3D 场景的正交投影（画家算法）。

    view3d=1 时可用 `yaw` / `pitch`（弧度）指定观察角；`pitch < 0` 为俯视（默认 −0.52）。
    """
    if view3d:
        from kernel.elements import GeoError
        from kernel.svg_io import export_svg3d as _exp3
        try:
            svg3 = _exp3(cons, yaw=yaw, pitch=pitch)
        except GeoError as e:
            return Response(content=str(e), media_type="text/plain", status_code=400)
        return Response(
            content=svg3,
            media_type="image/svg+xml",
            headers={"Content-Disposition": 'attachment; filename="ggbpy-3d.svg"',
                     "X-Svg-Mode": "3d"},
        )
    from kernel.svg_io import export_svg as _exp
    svg = _exp(cons, (xmin, xmax, ymin, ymax))
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Content-Disposition": 'attachment; filename="ggbpy.svg"',
                 "X-Svg-Mode": "2d"},
    )


@app.get("/api/export/obj")
def export_obj():
    """3D 网格导出：Wavefront OBJ（按对象分组，保留多边形面）。"""
    from urllib.parse import quote
    from kernel.mesh_io import export_obj as _exp
    text, warnings = _exp(cons)
    headers = {"Content-Disposition": 'attachment; filename="ggbpy.obj"'}
    if warnings:
        headers["X-Mesh-Warnings"] = quote(" | ".join(warnings), safe="")
    return Response(content=text, media_type="model/obj", headers=headers)


@app.get("/api/export/stl")
def export_stl():
    """3D 网格导出：ASCII STL（三角形面片 + 面法向，按对象分 solid 块）。"""
    from urllib.parse import quote
    from kernel.mesh_io import export_stl as _exp
    text, warnings = _exp(cons)
    headers = {"Content-Disposition": 'attachment; filename="ggbpy.stl"'}
    if warnings:
        headers["X-Mesh-Warnings"] = quote(" | ".join(warnings), safe="")
    return Response(content=text, media_type="model/stl", headers=headers)


@app.get("/api/export/gltf")
def export_gltf():
    """3D 网格导出：glTF 2.0（单文件 .gltf，几何内嵌 base64 buffer）。"""
    from urllib.parse import quote
    from kernel.mesh_io import export_gltf as _exp
    text, warnings = _exp(cons)
    headers = {"Content-Disposition": 'attachment; filename="ggbpy.gltf"'}
    if warnings:
        headers["X-Mesh-Warnings"] = quote(" | ".join(warnings), safe="")
    return Response(content=text, media_type="model/gltf+json", headers=headers)


@app.get("/api/download")
def download(xmin: float = -10.0, xmax: float = 10.0, ymin: float = -10.0, ymax: float = 10.0):
    """保存：自有 .ggk 格式（JSON，含样式与视口）。"""
    data = cons.save_ggk((xmin, xmax, ymin, ymax))
    return Response(
        content=data,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="ggbpy.ggk"'},
    )


# ---------------------------------------------------------------------------
# 自定义宏（Macro）
# ---------------------------------------------------------------------------

class MacroCreateBody(BaseModel):
    name: str
    inputs: list = []
    outputs: list = []
    xmin: float = -10.0
    xmax: float = 10.0
    ymin: float = -10.0
    ymax: float = 10.0


class MacroRunBody(BaseModel):
    name: str
    args: list = []
    xmin: float = -10.0
    xmax: float = 10.0
    ymin: float = -10.0
    ymax: float = 10.0


@app.get("/api/macro")
def macro_list():
    from kernel import macro
    return {"macros": macro.list_macros(cons)}


@app.post("/api/macro/create")
def macro_create(b: MacroCreateBody):
    from kernel import macro
    try:
        m = macro.create_macro(cons, b.name, b.inputs, b.outputs)
        return {"ok": True, "message": "宏 " + b.name + " 已创建", "macro": m, **_state(_view(b))}
    except ValueError as e:
        return {"ok": False, "message": "错误: " + str(e), **_state(_view(b))}


@app.post("/api/macro/delete")
def macro_delete(b: MacroRunBody):
    from kernel import macro
    ok = macro.delete_macro(b.name, cons)
    return {"ok": ok, "message": ("宏 " + b.name + " 已删除" if ok else "宏不存在: " + b.name), **_state(_view(b))}


@app.post("/api/macro/run")
def macro_run(b: MacroRunBody):
    from kernel import macro
    try:
        created = _mut(macro.run_macro, cons, b.name, b.args)
        if created is None:
            return {"ok": False, "message": "宏不存在: " + b.name, **_state(_view(b))}
        return {"ok": True, "message": "宏 " + b.name + " 执行成功", "created": [e.label for e in created],
                **_state(_view(b))}
    except Exception as e:  # 防御性捕获：该分支失败不应中断用户操作
        return {"ok": False, "message": "错误: " + str(e), **_state(_view(b))}


@app.post("/api/shift")
def do_shift(b: ShiftBody):
    """整体平移选中对象。"""
    try:
        if b.push:
            _mut(cons.push_history)
        _mut(cons.shift, b.label, b.dx, b.dy, getattr(b, "dz", 0.0))
        return {"ok": True, "message": "", **_state(_view(b))}
    except Exception as e:  # 防御性捕获：该分支失败不应中断用户操作
        return {"ok": False, "message": str(e), **_state(_view(b))}


@app.post("/api/reorder")
def do_reorder(b: ReorderBody):
    """对象列表拖拽后按新顺序重排（Z 叠放序）。"""
    try:
        _mut(cons.reorder, b.order)
        return {"ok": True, "message": "已调整对象顺序", **_state(_view(b))}
    except Exception as e:  # 防御性捕获：该分支失败不应中断用户操作
        return {"ok": False, "message": str(e), **_state(_view(b))}


@app.post("/api/image")
def image_upload(b: ImageBody):
    """上传图片（data URL）→ 返回短 id，供 Image[基点A, 基点B, id] 使用。"""
    from kernel import image_store
    try:
        iid = image_store.put(b.data, b.w, b.h)
        return {"ok": True, "id": iid}
    except Exception as e:  # 正则解析失败：按未匹配处理
        return {"ok": False, "message": str(e)}


@app.post("/api/mesh")
async def import_mesh(request: Request):
    """导入 OBJ 网格文本 → 存入网格仓库，返回 id（前端随后输入 m=Mesh[id]）。"""
    try:
        from kernel.mesh_io import parse_mesh
        from kernel import mesh_store
        raw = await request.body()
        verts, faces, warnings, fmt = parse_mesh(raw)
        mid = mesh_store.put(verts, faces)
        rec = mesh_store.get(mid)
        return {"ok": True, "id": mid, "format": fmt, "verts": len(rec["verts"]), "faces": len(rec["faces"]),
                "edges": len(mesh_store.edges_of(rec["faces"])), "warnings": warnings,
                "message": "已导入 %s 网格 %d 顶点 / %d 面" % (fmt, len(rec["verts"]), len(rec["faces"]))}
    except Exception as e:  # 可选依赖缺失：功能降级
        return {"ok": False, "message": "导入失败: " + str(e)}


@app.get("/api/image/{iid}")
def image_get(iid: str):
    """按 id 返回图片原始字节（浏览器缓存由 <img> 处理）。"""
    from kernel import image_store
    dec = image_store.decode(iid)
    if dec is None:
        return Response(status_code=404)
    mime, raw = dec
    return Response(content=raw, media_type=mime)


@app.post("/api/batch")
def do_batch(b: BatchBody):
    """批量执行命令序列（每行一条命令；# 注释/空行跳过；整体一个撤销步）。"""
    from kernel import commands as C

    def _run_batch():
        cons.push_history()
        out = []
        okn = 0
        for ln_no, line in enumerate(b.script.splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                out.append({"no": ln_no, "line": line or "(空)", "ok": True, "message": ""})
                continue
            try:
                created = C.process_line(cons, line)
                labels = [e.label for e in created]
                out.append({"no": ln_no, "line": line, "ok": True,
                            "message": ("已创建 " + ", ".join(labels)) if labels else "OK"})
                okn += 1
            except Exception as e:  # 防御性捕获：该分支失败不应中断用户操作
                out.append({"no": ln_no, "line": line, "ok": False, "message": str(e)})
        return out, okn

    results, ok_count = _mut(_run_batch)
    st = _state(_view(b))
    return {"ok": True, "script_ok": ok_count, "results": results, "elements": st["elements"], "count": st["count"]}


@app.post("/api/share")
def do_share(b: ShareBody):
    """生成分享链接：把当前构造（含视口）存为 share/<id>.ggk，返回短 ID。"""
    import re
    import secrets
    SHARE_DIR.mkdir(exist_ok=True)
    data = cons.save_ggk((b.xmin, b.xmax, b.ymin, b.ymax))
    sid = secrets.token_hex(3)
    (SHARE_DIR / (sid + ".ggk")).write_text(data, encoding="utf-8")
    return {"ok": True, "id": sid}


@app.get("/api/shared/{sid}")
def do_shared(sid: str):
    """按短 ID 取回分享内容（.ggk JSON 文本）。"""
    import re
    if not re.fullmatch(r"[0-9a-f]{6,12}", sid):
        return {"ok": False, "message": "无效的分享 ID"}
    p = SHARE_DIR / (sid + ".ggk")
    if not p.exists():
        return {"ok": False, "message": "分享不存在或已过期"}
    return {"ok": True, "content": p.read_text(encoding="utf-8")}


@app.get("/api/export/ggb")
def export_ggb():
    """兼容导出：GeoGebra XML 格式。

    .ggb 子集不支持 3D：这些元素会被跳过，警告写入响应头 X-GGB-Warnings
    （percent-encoded）并作为 XML 注释写入文件首部。
    """
    warnings = []
    xml = cons.save_ggb(warnings)
    headers = {"Content-Disposition": 'attachment; filename="ggbpy.ggb"'}
    if warnings:
        from urllib.parse import quote
        headers["X-GGB-Warnings"] = quote(" | ".join(warnings), safe="")
        headers["X-GGB-Skipped-3D"] = "1"
    return Response(
        content=xml,
        media_type="application/xml",
        headers=headers,
    )


@app.post("/api/load")
async def do_load(request: Request):
    try:
        text = (await request.body()).decode("utf-8", errors="replace")
        view = None
        if text.strip().startswith("{"):
            view = _mut(cons.load_json, text)
        else:
            _mut(cons.load_text, text)
        return {"ok": True, "message": "已加载", "view": view, **_state((-10, 10, -10, 10))}
    except Exception as e:  # 坏数据（JSON/base64 解码失败）：跳过该记录或字段
        return {"ok": False, "message": "加载失败: " + str(e), **_state((-10, 10, -10, 10))}


def _cas_cells():
    """返回可 JSON 序列化的单元列表（剔除内部 sympy 对象）。"""
    return [{k: v for k, v in c.items() if k != "sym"} for c in cas.cells]


def _state3d_full():
    """3D 视图数据：geo3d 对象 + 所有点/线段/圆/多边形等（2D 对象视为 z=0，在 xoy 平面显示）。"""
    out = []
    for lab in cons.order:
        el = cons.elements[lab]
        vis = el.visible is not False
        if el.kind == "geo3d":
            d = el.draw((0, 0, 0, 0))
            if d is None:
                out.append({"label": lab, "kind": "geo3d", "objtype": getattr(el, "objtype", ""),
                            "wire": getattr(el, "wire", False), "visible": False, "defn": el.defn})
            else:
                out.append(d)
        elif el.kind == "point":
            z = el.z if el.z is not None else 0.0
            if not vis:
                out.append({"label": lab, "kind": "point", "free": el.free, "visible": False,
                            "defn": el.defn, "x": el.x, "y": el.y, "z": z})
            else:
                out.append({"label": lab, "kind": "point", "free": el.free,
                            "x": el.x, "y": el.y, "z": z, "defn": el.defn})
        elif el.kind == "segment":
            d = el.draw((0, 0, 0, 0))
            if d is None:
                out.append({"label": lab, "kind": "geo3d", "objtype": "segment", "visible": False, "defn": el.defn})
            else:
                out.append({"label": lab, "kind": "geo3d", "objtype": "segment",
                            "visible": True, "defn": el.defn,
                            "data": {"x1": d.get("x1", 0), "y1": d.get("y1", 0), "z1": 0,
                                     "x2": d.get("x2", 0), "y2": d.get("y2", 0), "z2": 0}})
        elif el.kind == "line":
            d = el.draw(DEFAULT_VIEW)   # 用默认视口裁剪直线（view=(0,0,0,0) 会退化）
            seg = d.get("seg") if d else None
            if not vis:
                out.append({"label": lab, "kind": "geo3d", "objtype": "line2d", "visible": False, "defn": el.defn})
            elif seg:
                out.append({"label": lab, "kind": "geo3d", "objtype": "line2d", "visible": True,
                            "defn": el.defn,
                            "data": {"x1": seg[0], "y1": seg[1], "z1": 0, "x2": seg[2], "y2": seg[3], "z2": 0}})
        elif el.kind == "ray":
            d = el.draw(DEFAULT_VIEW)
            seg = d.get("seg") if d else None
            if not vis:
                out.append({"label": lab, "kind": "geo3d", "objtype": "line2d", "visible": False, "defn": el.defn})
            elif seg:
                out.append({"label": lab, "kind": "geo3d", "objtype": "line2d", "visible": True,
                            "defn": el.defn,
                            "data": {"x1": seg[0], "y1": seg[1], "z1": 0, "x2": seg[2], "y2": seg[3], "z2": 0}})
        elif el.kind == "circle":
            d = el.draw((0, 0, 0, 0))
            if d is None:
                out.append({"label": lab, "kind": "geo3d", "objtype": "circle2d", "visible": False, "defn": el.defn})
            else:
                out.append({"label": lab, "kind": "geo3d", "objtype": "circle2d", "visible": True,
                            "defn": el.defn,
                            "data": {"cx": d.get("cx", 0), "cy": d.get("cy", 0), "cz": 0, "r": d.get("r", 0)}})
        elif el.kind == "polygon":
            d = el.draw((0, 0, 0, 0))
            if d is None:
                out.append({"label": lab, "kind": "geo3d", "objtype": "polygon2d", "visible": False, "defn": el.defn})
            else:
                pts = d.get("pts", [])
                out.append({"label": lab, "kind": "geo3d", "objtype": "polygon2d", "visible": True,
                            "defn": el.defn,
                            "data": {"pts": [[p[0], p[1], 0] for p in pts]}})
        elif el.kind == "vector":
            if not vis:
                out.append({"label": lab, "kind": "geo3d", "objtype": "vector2d", "visible": False, "defn": el.defn})
            else:
                out.append({"label": lab, "kind": "geo3d", "objtype": "vector2d", "visible": True,
                            "defn": el.defn,
                            "data": {"sx": el.sx, "sy": el.sy, "sz": 0, "dx": el.dx, "dy": el.dy, "dz": 0}})
        elif el.kind == "polyline":
            d = el.draw((0, 0, 0, 0))
            if d is None:
                out.append({"label": lab, "kind": "geo3d", "objtype": "polyline2d", "visible": False, "defn": el.defn})
            else:
                pts = d.get("pts", [])
                out.append({"label": lab, "kind": "geo3d", "objtype": "polyline2d", "visible": True,
                            "defn": el.defn,
                            "data": {"pts": [[p[0], p[1], 0] for p in pts]}})
    return {"elements": out, "count": len(out)}     # 原始 dict；响应时只 _clean 实际发送的部分


@app.get("/api/state3d")
def state3d(since: int = -1):
    """3D 视图数据（增量）：?since=<上次 rev>
    返回 {rev, unchanged:true} / {rev, changed, removed} / {rev, elements}（全量兜底）。"""
    res = _state3d_full()          # {"elements": [...], "count": n}
    full = res.get("elements") if isinstance(res, dict) else res
    fp = {}
    for d in full:
        lab = d.get("label")
        if lab:
            fp[lab] = _state3d_fp(d)
    with _SD["lock"]:
        if fp != _SD["fp"]:
            _SD["rev"] += 1
            _SD["fp"] = fp
            _SD["hist"][_SD["rev"]] = dict(fp)
            if len(_SD["hist"]) > _SD_HIST_MAX:
                for old in sorted(_SD["hist"].keys())[:-_SD_HIST_MAX]:
                    _SD["hist"].pop(old, None)
        rev = _SD["rev"]
        if since == rev:
            return {"rev": rev, "unchanged": True, "count": len(full)}
        prev = _SD["hist"].get(since)
        if prev is None:
            return {"rev": rev, "elements": _clean(full), "count": len(full)}
        changed = [d for d in full if prev.get(d.get("label")) != fp[d["label"]]]
        removed = [lab for lab in prev if lab not in fp]
        return {"rev": rev, "changed": _clean(changed), "removed": removed,
                "count": len(full), "unchanged": False}


@app.get("/api/cas")
def cas_state():
    return {"cells": _cas_cells(), "count": len(cons.order)}


@app.post("/api/cas/eval")
def cas_eval(b: CasBody):
    cell = cas.evaluate(b.text)
    serial = {k: v for k, v in cell.items() if k != "sym"}
    return {
        "ok": cell["error"] is None,
        "cell": serial,
        "cells": _cas_cells(),
        "state": _clean(cons.to_serializable(_view(b))),
        "count": len(cons.order),
    }


@app.post("/api/cas/clear")
def cas_clear():
    cas.clear()
    return {"ok": True, "cells": [], "count": len(cons.order)}


if __name__ == "__main__":
    import sys
    import uvicorn

    port = 8090
    if "--port" in sys.argv:
        try:
            port = int(sys.argv[sys.argv.index("--port") + 1])
        except (ValueError, IndexError):
            pass
    uvicorn.run("server.main:app", host="127.0.0.1", port=port, reload=False)
