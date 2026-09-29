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
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from kernel.construction import Construction, DEFAULT_VIEW
from kernel.cas import CASEngine

app = FastAPI(title="ggbpy · Python 动态几何")
STATIC = Path(__file__).parent / "static"
cons = Construction()
cas = CASEngine(cons)


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


app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/api/commands")
def commands_list():
    """命令名列表（前端自动补全/帮助）。"""
    from kernel.commands import COMMANDS
    return {"commands": sorted(COMMANDS.keys())}


@app.get("/api/state")
def state(xmin: float = -10.0, xmax: float = 10.0, ymin: float = -10.0, ymax: float = 10.0):
    return _state((xmin, xmax, ymin, ymax))


@app.post("/api/input")
def do_input(b: InputBody):
    msg = cons.process(b.text)
    return {"ok": msg.startswith("OK"), "message": msg, **_state(_view(b))}


@app.post("/api/drag")
def do_drag(b: DragBody):
    try:
        if b.push:
            # 每次拖拽成为独立撤销步（首条请求带 push）
            cons.push_history()
        cons.move(b.label, b.x, b.y, b.z)
        return {"ok": True, "message": "", **_state(_view(b))}
    except Exception as e:
        return {"ok": False, "message": str(e), **_state(_view(b))}


@app.post("/api/undo")
def do_undo():
    ok = cons.undo()
    return {"ok": ok, "message": "已撤销" if ok else "没有可撤销的操作", **_state((-10, 10, -10, 10))}


@app.post("/api/redo")
def do_redo():
    ok = cons.redo()
    return {"ok": ok, "message": "已重做" if ok else "没有可重做的操作", **_state((-10, 10, -10, 10))}


@app.post("/api/clear")
def do_clear():
    cons.clear()
    return {"ok": True, "message": "已清空", **_state((-10, 10, -10, 10))}


@app.post("/api/demo")
def do_demo():
    cons.load_demo()
    return {"ok": True, "message": "已载入示例（拖动 A 观察依赖重算）", **_state((-10, 10, -10, 10))}


@app.get("/api/export/svg")
def export_svg(xmin: float = -10.0, xmax: float = 10.0, ymin: float = -10.0, ymax: float = 10.0):
    from kernel.svg_io import export_svg as _exp
    svg = _exp(cons, (xmin, xmax, ymin, ymax))
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Content-Disposition": 'attachment; filename="ggbpy.svg"'},
    )


@app.get("/api/export/svg")
def export_svg(xmin: float = -10.0, xmax: float = 10.0, ymin: float = -10.0, ymax: float = 10.0):
    from kernel.svg_io import export_svg as _exp
    svg = _exp(cons, (xmin, xmax, ymin, ymax))
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Content-Disposition": 'attachment; filename="ggbpy.svg"'},
    )


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
    return {"macros": macro.list_macros()}


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
    ok = macro.delete_macro(b.name)
    return {"ok": ok, "message": ("宏 " + b.name + " 已删除" if ok else "宏不存在: " + b.name), **_state(_view(b))}


@app.post("/api/macro/run")
def macro_run(b: MacroRunBody):
    from kernel import macro
    try:
        created = macro.run_macro(cons, b.name, b.args)
        if created is None:
            return {"ok": False, "message": "宏不存在: " + b.name, **_state(_view(b))}
        return {"ok": True, "message": "宏 " + b.name + " 执行成功", "created": [e.label for e in created],
                **_state(_view(b))}
    except Exception as e:
        return {"ok": False, "message": "错误: " + str(e), **_state(_view(b))}


@app.post("/api/shift")
def do_shift(b: ShiftBody):
    """整体平移选中对象。"""
    try:
        if b.push:
            cons.push_history()
        cons.shift(b.label, b.dx, b.dy, getattr(b, "dz", 0.0))
        return {"ok": True, "message": "", **_state(_view(b))}
    except Exception as e:
        return {"ok": False, "message": str(e), **_state(_view(b))}


@app.post("/api/reorder")
def do_reorder(b: ReorderBody):
    """对象列表拖拽后按新顺序重排（Z 叠放序）。"""
    try:
        cons.reorder(b.order)
        return {"ok": True, "message": "已调整对象顺序", **_state(_view(b))}
    except Exception as e:
        return {"ok": False, "message": str(e), **_state(_view(b))}


@app.post("/api/image")
def image_upload(b: ImageBody):
    """上传图片（data URL）→ 返回短 id，供 Image[基点A, 基点B, id] 使用。"""
    from kernel import image_store
    try:
        iid = image_store.put(b.data, b.w, b.h)
        return {"ok": True, "id": iid}
    except Exception as e:
        return {"ok": False, "message": str(e)}


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
    cons.push_history()
    results = []
    ok_count = 0
    for ln_no, line in enumerate(b.script.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            results.append({"no": ln_no, "line": line or "(空)", "ok": True, "message": ""})
            continue
        try:
            created = C.process_line(cons, line)
            labels = [e.label for e in created]
            results.append({"no": ln_no, "line": line, "ok": True,
                            "message": ("已创建 " + ", ".join(labels)) if labels else "OK"})
            ok_count += 1
        except Exception as e:
            results.append({"no": ln_no, "line": line, "ok": False, "message": str(e)})
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
    """兼容导出：GeoGebra XML 格式。"""
    xml = cons.save_ggb()
    return Response(
        content=xml,
        media_type="application/xml",
        headers={"Content-Disposition": 'attachment; filename="ggbpy.ggb"'},
    )


@app.post("/api/load")
async def do_load(request: Request):
    try:
        text = (await request.body()).decode("utf-8", errors="replace")
        view = None
        if text.strip().startswith("{"):
            view = cons.load_json(text)
        else:
            cons.load_text(text)
        return {"ok": True, "message": "已加载", "view": view, **_state((-10, 10, -10, 10))}
    except Exception as e:
        return {"ok": False, "message": "加载失败: " + str(e), **_state((-10, 10, -10, 10))}


def _cas_cells():
    """返回可 JSON 序列化的单元列表（剔除内部 sympy 对象）。"""
    return [{k: v for k, v in c.items() if k != "sym"} for c in cas.cells]


@app.get("/api/state3d")
def state3d():
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
    return {"elements": _clean(out), "count": len(out)}


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
