"""命令处理与几何算法（P0）。

实现：Midpoint Line Segment Ray Circle Polygon Intersect Distance Slope Angle
      Length Translate Rotate Reflect Vector

设计：每个命令创建"派生元素"（deps + compute_fn 闭包），数值状态在 compute 时
按 deps 当前坐标重算 —— 拖动自由点后由 Construction 增量重算整条依赖链。
"""

from __future__ import annotations

import math
import re
from typing import Callable, Dict, List, Optional, Tuple

from . import schemas
from .cmd_util import (  # 命令层共享工具（自本模块抽出）
    _nested_depth, label_of, _label_of, _mk, _auto, _resolve, _lookup, _tuple_parts_any, _list_arg,
    _point_arg, _num_deps, _num_list_items, _num_series, _elem_or_point, _is_segment_el
)
from .cmd_util import set_nested_evaluator
# 微积分/符号计算命令已抽到 kernel/calculus.py；re-export 保持调用方兼容
from .calculus import (  # noqa: F401
    _fmt, _feval, _roots_1d, _cmd_of, _cmd_derivative, _cmd_integral, _cmd_root, _root_state,
    _cmd_extremum, _cmd_rectsum, _int_values, _cmd_isprime, _cmd_divisors, _cmd_factorslist,
    _parse_sympy, _fit_expr, _cmd_fitexpr, _cmd_sequence, _cmd_normaldist, _cmd_solveineq, _fmt_sol,
    _fmt_sol_num
)

# 杂项命令（随机数/线框显示，P2 结构拆分）。（P2 结构拆分：命令组抽出）
from .misc import _cmd_randombetween, _cmd_randomize, _cmd_setwire  # noqa: F401

# 自定义宏命令（MacroCreate/MacroList，P2 结构拆分）。（P2 结构拆分：命令组抽出）
from .macros import _cmd_macrocreate, _cmd_macrolist  # noqa: F401

# 迭代与轨迹命令（Iteration/IterationList/Locus，P2 结构拆分）。（P2 结构拆分：命令组抽出）
from .iteration import (  # noqa: F401
    _iter_setup, _cmd_iteration, _cmd_iterationlist, _cmd_locus, _locus_state
)

# 拟合与相关命令（指数/对数/多项式/幂/正弦拟合、PMCC、协方差椭球，P2 结构拆分）。（P2 结构拆分：命令组抽出）
from .fits import (  # noqa: F401
    _cmd_cov_ellipsoid, _cov_ellipsoid_state, _cmd_pmcc, _cmd_fitpoly, _fit_cmd, _cmd_fitexp,
    _cmd_fitlog, _cmd_fitpow, _cmd_fitsin
)

# 三角形四心命令（外心/垂心/旁心，P2 结构拆分）。（P2 结构拆分：命令组抽出）
from .centers import (  # noqa: F401
    _tri_points, _cmd_orthocenter, _orthocenter_state, _cmd_circumcenter, _circumcenter_state,
    _cmd_excenter, _excenter_state
)

# 布尔判定与证明命令（共点/共圆/全等/Prove，P2 结构拆分）。（P2 结构拆分：命令组抽出）
from .proofs import _cmd_areconcyclic, _cmd_arecongruent, _cmd_areconcurrent, _cmd_prove  # noqa: F401

# 度量命令（距离/长度/周长/半周长/半径/斜率/角度，P2 结构拆分：从 commands.py 抽出）。（P2 结构拆分：命令组抽出）
from .measures import (  # noqa: F401
    _cmd_distance, _pt_linear_dist, _cmd_slope, _slope_state, _cmd_angle, _angle2_state, _angle_state,
    _polygon_perimeter, _section_perimeter, _cmd_perimeter, _cmd_circumference, _ellipse_circumference,
    _cmd_radius, _cmd_semiperimeter, _cmd_length
)

# 矩阵与复数命令（矩阵/行列式/转置/逆/点积/复数运算，P2 结构拆分：从 commands.py 抽出）。（P2 结构拆分：命令组抽出）
from .linalg import (  # noqa: F401
    _vec2_arg, _vec_arg_objs, _cmd_dot, _cmd_conj, _cmd_re, _cmd_im, _cmd_arg, _arg_deg,
    _parse_matrix_arg, _cmd_matrix, _cmd_det, _det_state, _cmd_transpose, _transpose_state,
    _cmd_inverse, _inverse_state
)

# 圆锥曲线命令（椭圆/双曲线/抛物线/五点圆锥/焦点/直径/极线/隐式/参数曲线，P2 结构拆分：从 commands.py 抽出）。（P2 结构拆分：命令组抽出）
from .conics import (  # noqa: F401
    _cmd_diameter, _curve_compute, _cmd_parametric, _cmd_polar, _cmd_implicit, _mk_conic,
    _conic_from_canonical, _cmd_ellipse, _cmd_hyperbola, _cmd_parabola, _cmd_conic5, _cmd_focus
)

# 导入导出命令（OBJ/STL/glTF 导入导出、图片与文本，P2 结构拆分：从 commands.py 抽出）。（P2 结构拆分：命令组抽出）
from .io_cmds import (  # noqa: F401
    _tuple_parts, _cmd_image, _txt_num, _dyn_text_segments, _ref_text, _dyn_text_compute, _cmd_text
)

# 数值与统计命令（求和/均值/方差/排序/四分位/组合数/取整等，P2 结构拆分：从 commands.py 抽出）。（P2 结构拆分：命令组抽出）
from .numeric import (  # noqa: F401
    _cmd_npr, _cmd_ncr, _cmd_gcd, _cmd_lcm, _resolve_complex, _cmd_complex_abs, _cmd_sum, _cmd_mean,
    _cmd_median, _cmd_mode, _cmd_variance, _cmd_stdev, _cmd_min, _cmd_max, _cmd_sort, _cmd_normal,
    _cmd_q1, _cmd_q3, _cmd_iqr
)

# 编辑与样式命令（改值/改色/改名/重定义/删除/显隐，P2 结构拆分：从 commands.py 抽出）。（P2 结构拆分：命令组抽出）
from .editing import _COLOR_NAMES  # noqa: F401
from .editing import (  # noqa: F401
    _COLOR_NAMES, _cmd_slider, _cmd_setcoords, _cmd_setvalue, _cmd_setlocked, _parse_color, _cmd_delete,
    _cmd_rename, _cmd_redefine, _cmd_setcolor, _cmd_setvisible, _cmd_macrodelete
)

# 仿射变换命令（反射/旋转/平移/位似/反演，P2 结构拆分：从 commands.py 抽出）。（P2 结构拆分：命令组抽出）
from .transforms import DEG  # noqa: F401
from .transforms import (  # noqa: F401
    DEG, _cmd_translate, _cmd_rotate, _cmd_reflect, _transform_mk, _inv_map, _inv_circle_params,
    _inv_linear_state, _inv_circle_conic_state, _inv_line_conic_state, _source_chains,
    _inv_sampled_state, _invert_implicit_state, _mk_implicit, _mk_param_curve, _compose_inv, _seg_pole,
    _cmd_invert, _cmd_dilate
)

# 二维图元命令（点/线/圆/多边形族，P2 结构拆分：从 commands.py 抽出）。（P2 结构拆分：命令组抽出）
from .primitives import _PRED_VIEW  # noqa: F401
from .primitives import (  # noqa: F401
    _resolve_vector, _resolve_vector3, _intersect_lines, _dist, _line_circle, _circle_circle,
    _circumcircle, _cmd_midpoint, _cmd_line, _line3d_state, _parallel_state, _cmd_segment, _seg3d_state,
    _cmd_ray, _cmd_circle, _circle_state, _circ_state, _cmd_polygon, _cmd_rigidpolygon, _cmd_polyline,
    _cmd_intersect, _cmd_isoline, _isoline_state, _ix_fn_fn, _ix_fn_lin, _ix_linlin, _check_seg_ray,
    _on_segment, _ix_lincir, _ix_circir, _ix_conic_conic, _cmd_vector, _mk_free, _line_y_x,
    _cmd_tangent, _tangent_state, _cmd_perpendicularline, _perp_state, _cmd_foot, _foot_state,
    _cmd_perpbis, _perpbis_state, _perpbis_state2, _cmd_regularpolygon, _cmd_anglebisector,
    _bisector_state, _cmd_incenter, _incenter_state, _cmd_incircle, _incircle_state, _cmd_centroid,
    _centroid_state, _cmd_randpointin, _randpointin_state, _cmd_fitline, _conic_coeffs,
    _cmd_tangent_conic, _tangent_conic_state_i, _tangent_arc_state, _tangent_conic_state, _ix_lin_conic,
    _pred_dir, _pred_scale, _numeric_verdict, _prove_cmd, _cmd_areparallel, _cmd_areperpendicular,
    _cmd_arecollinear, _cmd_pointoncircle, _cmd_pointonpath, _pop_state, _poc_state, _cmd_arc,
    _cmd_semicircle, _semicircle_state, _cmd_sector, _arc_state
)

# 三维命令（P2 结构拆分（P2 结构拆分）
from .commands3d import (  # noqa: F401
    _cmd_bbox, _bbox_state, _cmd_covariance, _cmd_convexhull, _convexhull_state, _surface_eval,
    _cmd_surfacepoint, _surfacepoint_state, _cmd_surfaceproject, _surfaceproject_state, _cmd_fitsphere,
    _polygon_area, _cmd_area, _cmd_volume, _cmd_surface, _surface_compute, _cmd_mesh,
    _cmd_surface_param, _surface_param_compute, _cmd_implicit_surface, _implicit_surface_compute,
    _cmd_fitplane, _cmd_sphere, _cmd_plane, _plane_state, _cmd_cube, _poly3_points, _poly_register,
    _number_arg, _vector3_arg, _infinite_cone_state, _cmd_cone, _cmd_cylinder, _cmd_prism, _cmd_pyramid,
    _cmd_tetrahedron, _cmd_octahedron, _cmd_hexahedron, _cmd_icosahedron, _cmd_dodecahedron
)

# 统计图命令（P2 结构拆分（P2 结构拆分）
from .charts import (  # noqa: F401
    _cmd_piechart, _cmd_histogram, _cmd_boxplot, _cmd_barchart, _cmd_linechart, _cmd_scatterplot,
    _cmd_dotplot, _cmd_barchart3d, _cmd_scatterplot3d, _cmd_surfacechart3d, _anon_list
)
from .cmd_util import _NESTED_CALL_RE, _NESTED_MAX_DEPTH  # noqa: F401

# 四张注册表已抽到 kernel/registry.py（P2 结构拆分）
from .registry import ALIASES, COMMANDS, DISPLAY_NAMES, RESULT_KINDS  # noqa: F401
from .registry import _label_kind, _result_kind  # noqa: F401（命名助手随注册表）
from .nested import _DetachedConstruction, _eval_nested  # noqa: F401（嵌套命令求值器）
from .elements import (
    EPSILON, Geo3D, GeoAngle, GeoArc, GeoBarChart, GeoBoolean, GeoChart2D, GeoCircle, GeoConic,
    GeoDotPlot, GeoLineChart, GeoScatterPlot, GeoBoxPlot, GeoComplex, GeoCurve, GeoError, GeoFunction,
    GeoImage, GeoImplicit, GeoInequality, GeoLine, GeoList, GeoLocus, GeoMatrix, GeoNumber, GeoPolar,
    GeoPoint, GeoPolygon, GeoPolyline, GeoPie, GeoRay, GeoResult, GeoSegment, GeoSumRect, GeoText,
    GeoVector
)
from .parser import _split_commas, eval_number, parse_line

# 3D 几何算法已抽到 kernel/geometry3d.py（P2 结构拆分）；此处 re-export 保持调用方兼容
from .geometry3d import (  # noqa: F401
    _tag3d, _z_of, _has_z, _dist3, _solve2, _line_ends, _circle3d_basis, _ray_triangle,
    _frame_from_axis, _normalize_mesh, _newell_normal, _mesh_volume, _mesh_area, _solid_volume,
    _solid_area, _is_solid_el, _solid_planes, _clip_polyhedron, _ix_plane_plane, _ix_line_plane,
    _ix_line3d_plane, _ix_solid_plane, _ix_sphere_sphere, _ix_sphere_circle3d, _ix_circle3d_circle3d,
    _ix_circle3d_plane, _ix_circle3d_solid, _ix_sphere_solid, _ix_sphere_plane, _ix_solid_solid,
    _ix_solid_line, _ix_sphere_line, _poly_state
)

# 立体构造数学已抽到 kernel/solids.py（P2 结构拆分）；re-export 保持调用方兼容
from .solids import _PHI as _solids_PHI  # noqa: F401
from .solids import (  # noqa: F401
    _sphere_check, _sphere_state, _sphere_state_r, _sphere_state_fixed, _cube_seg_pts, _cube_from_edge,
    _cube_from_poly, _cube_build, _cube_state, _cube_state2, _ortho_frame, _with_analytic,
    _cone_mesh_axis, _cone_from_circle_state, _cone_apex_center_radius_state, _cone_state,
    _cyl_mesh_axis, _cylinder_from_circle_state, _cylinder_centers_radius_state, _cylinder_state,
    _prism_state, _pyramid_state, _tetrahedron_state, _regular_polyhedron, _octahedron_state,
    _hexahedron_state, _icosahedron_state, _dodecahedron_state
)

# 二维几何基元与变换已抽到 kernel/geo2d.py（P2 结构拆分）；re-export 保持调用方兼容
from .geo2d import (  # noqa: F401
    _linear, _line_through, _reflect_point_line, _reflect_point_point, _rotate, _line_state, _dilate_pt,
    _transform_fn, _reflect_lin, _reflect_lin_xy, _reflected_line, _reflected_point_line, _rotated_line,
    _fn_state, _conic_t, _dilated_line
)

# 统计/拟合已抽到 kernel/stats.py（P2 结构拆分）；re-export 保持调用方兼容
from .stats import (  # noqa: F401
    _median, _mode, _variance, _fit_silent_fit, _fitline_state, _barchart_state, _fitsphere_state,
    _fitplane_state
)
from .stats import (  # noqa: F401
    _bars3d_mesh, _dotplot_state, _linechart_state, _scatter3d_mesh, _scatter_state, _surface3d_mesh
)
from .stats import _REF_DOT, _REF_X  # noqa: F401
from .tolerance import EPSILON, TIGHT, COORD, ZERO_SQ, LOOSE, COARSE, NEGLIGIBLE, ROOT_TOL, OPT_XATOL, OPT_FATOL  # 统一数值容差（见 kernel/tolerance.py）


# 形如 "Circle[O,2]" / "Plane[A,B,C]" 的嵌套命令调用（不含赋值号）
# _NESTED_CALL_RE / _NESTED_MAX_DEPTH 已移至 kernel/cmd_util.py（此处 re-export）
# 嵌套命令最大层数（防御深层递归/自引用）




# ---------------------------------------------------------------------------
# 解析辅助
# ---------------------------------------------------------------------------







def _number(cons, s: str):
    s = s.strip()
    el = _lookup(cons, s)
    if el is not None and el.kind in ("number", "angle"):
        return el
    raise GeoError(s + " 不是数值对象")












# ---------------------------------------------------------------------------
# 创建派生元素的公共闭包工厂
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 各命令实现（返回新建元素）
# ---------------------------------------------------------------------------



























































# ---- 凸多面体半空间裁剪（体∩体） ----































# (旧 _cmd_length 已被下方新版覆盖，已删除)


# ---------------------------------------------------------------------------
# 变换：Translate / Rotate / Reflect（每个目标类型一个闭包）
# ---------------------------------------------------------------------------













# ---------------------------------------------------------------------------
# 函数（SymPy 解析）
# ---------------------------------------------------------------------------

def _make_function(cons, label, body: str) -> GeoFunction:
    refs = _function_refs(cons, body)
    # 未定义变量 → 自动生成参数滑块（多个未知量 → 多个 slider，类似 GeoGebra）
    import sympy
    try:
        x = sympy.Symbol("x")
        expr0 = _parse_sympy(body, {"x": x}, cons)
        free = expr0.free_symbols - {x}
        for s in sorted(free, key=str):
            sname = str(s)
            if sname in cons.elements:
                continue  # 已是已有对象（数值/函数）→ 作引用
            if not re.match(r"^[A-Za-z_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff]*$", sname):
                raise GeoError("函数未知变量名非法: " + sname)
            sl = GeoNumber(sname, sname + "=Slider[-5,5,0.1]", 0.0)
            sl.min, sl.max, sl.step = -5.0, 5.0, 0.1
            cons.add(sl)
            refs.append(sl)
    except GeoError:
        raise
    except Exception:
        pass  # 解析失败交给 configure 报错
    el = GeoFunction(label, label + "(x)=" + body)
    try:
        el.configure(cons, body, refs)
    except GeoError:
        raise
    except Exception:
        raise GeoError("无法解析函数表达式: " + body)
    return cons.add(el)


def _function_refs(cons, body: str) -> List:
    """找出函数体中引用的已有元素（数值/函数），用于建立依赖。"""
    import re
    refs = []
    for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", body):
        if tok in ("x", "e", "pi", "sin", "cos", "tan", "exp", "log", "ln", "sqrt", "abs",
                   "log10", "asin", "acos", "atan", "sinh", "cosh", "tanh", "floor", "ceil", "round", "sign"):
            continue
        el = cons.elements.get(tok)
        if el is not None and el.kind in ("number", "function") and el not in refs:
            refs.append(el)
    return refs


# ---------------------------------------------------------------------------
# 数值求根（函数求交 / Root / Extremum 共用）
# ---------------------------------------------------------------------------



def _fn_line_diff(f, lin, x):
    """f(x) - line_y(x) 的符号表达式；垂直线返回 None（单独处理）。"""
    a, b, c = _linear(lin)
    if abs(b) < EPSILON:
        return None
    return f.expr - (-(a * x + c) / b)


# ---------------------------------------------------------------------------
# P1 命令：Derivative / Integral / Tangent / Root / Extremum
# ---------------------------------------------------------------------------





# ---------------------------------------------------------------------------
# 初中几何补充：垂线/垂足/角平分线/度量/内心/重心/滑动条
# ---------------------------------------------------------------------------






































































# ---------------------------------------------------------------------------
# 教学批次2：随机 / 排列组合 / 向量点积 / 相关系数
# ---------------------------------------------------------------------------


















# ---------------------------------------------------------------------------
# 教学批次3：黎曼和（LeftSum/RightSum/MidpointSum/LowerSum/UpperSum/RectangleSum/TrapezoidalSum）与饼图
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# 教学批次5：迭代（数列递推）与数论（GCD/LCM/素数/因数）
# ---------------------------------------------------------------------------
















# ---------------------------------------------------------------------------
# 复数（复平面）：z=3+4i；conj/re/im/abs/arg
# ---------------------------------------------------------------------------

_IMG_I_RE = None  # 占位


def _complex_build(cons, label, expr_text):
    import re as _re
    import sympy
    s = _re.sub(r"(?<=[0-9a-zA-Z_\])])i(?![A-Za-z_0-9])", "*I", expr_text)
    s = _re.sub(r"(?<![0-9a-zA-Z_])i(?![A-Za-z_0-9])", "I", s)
    tr = (sympy.parsing.sympy_parser.standard_transformations
          + (sympy.parsing.sympy_parser.implicit_multiplication_application,
             sympy.parsing.sympy_parser.convert_xor))
    e = sympy.parsing.sympy_parser.parse_expr(s, local_dict={"I": sympy.I}, transformations=tr)
    free = e.free_symbols - {sympy.I}
    if free:
        raise GeoError("复数表达式仅支持数值系数（如 3+4i、1-2i、i、-2.5i），出现未知符号: "
                       + ", ".join(sorted(str(v) for v in free)))
    rv, iv = e.as_real_imag()
    el = GeoComplex(label, label + "=" + expr_text, float(rv), float(iv))
    el.free = False
    return cons.add(el)


















# ---------------------------------------------------------------------------
# P2：参数曲线 / 极坐标 / 隐式方程（参考 Desmos 的函数式绘图能力）
# ---------------------------------------------------------------------------








# ---------------------------------------------------------------------------
# P3：不等式 / 列表 / 统计 / 圆锥曲线 / 3D
# ---------------------------------------------------------------------------

def _make_ineq_y(cons, label, op, body):
    import sympy
    x = sympy.Symbol("x")
    expr = _parse_sympy(body, {"x": x}, cons)
    free = expr.free_symbols - {x}
    if free:
        raise GeoError("不等式出现未知变量: " + ", ".join(sorted(str(s) for s in free)))
    el = GeoInequality(label, label + ": y " + op + " " + body)
    el.form = "y"
    el.expr = expr
    el.xsym = x
    el.ysym = None
    el.yside = 1 if op in (">", ">=") else -1
    el.strict = op not in (">=", "<=")
    el.free = False
    return cons.add(el)


def _make_ineq_general(cons, label, op, lhs, rhs):
    import sympy
    x = sympy.Symbol("x")
    y = sympy.Symbol("y")
    le = _parse_sympy(lhs, {"x": x, "y": y}, cons)
    re = _parse_sympy(rhs, {"x": x, "y": y}, cons)
    if op in ("<", "<="):
        expr = le - re
    else:
        expr = re - le
    free = expr.free_symbols - {x, y}
    if free:
        raise GeoError("不等式出现未知变量: " + ", ".join(sorted(str(s) for s in free)))
    el = GeoInequality(label, label + ": " + lhs + " " + op + " " + rhs)
    el.form = "general"
    el.expr = expr
    el.xsym = x
    el.ysym = y
    el.yside = 0
    el.strict = op not in (">=", "<=")
    el.free = False
    return cons.add(el)


def _list_defn(items, itemkind):
    if itemkind == "point":
        return "{" + ", ".join("(" + _fmt(a) + "," + _fmt(b) + ")" for a, b in items) + "}"
    if itemkind == "point3d":
        return "{" + ", ".join("(" + _fmt(a) + "," + _fmt(b) + "," + _fmt(c) + ")" for a, b, c in items) + "}"
    return "{" + ", ".join(_fmt(v) for v in items) + "}"


























# ---- 圆锥曲线 ----



























# ---- 3D ----

























# ---------------------------------------------------------------------------
# 3D 多面体：圆锥/圆柱/棱柱/棱锥/正四面体/正八面体/正二十面体/正十二面体
# 统一数据模型：{verts: [[x,y,z]...], faces: [[idx...]...], edges: [[i,j]...]}
# ---------------------------------------------------------------------------









# ---- 立体体积 / 表面积（网格散度定理 + 解析优先）----













# _PHI 已随立体构造数学移至 kernel/solids.py（此处 re-export 兼容）
_PHI = _solids_PHI










# ---------------------------------------------------------------------------
# P4：定理证明 / 序列 / 回归 / 脚本
# ---------------------------------------------------------------------------

# 与 construction.DEFAULT_VIEW 一致（此处避免循环导入而本地定义）
# _PRED_VIEW 已随图元/谓词命令移至 kernel/primitives.py（此处 re-export）






































# ---------------------------------------------------------------------------
# 变换辅助：函数变换 / 圆锥曲线变换 / Dilate 命令
# ---------------------------------------------------------------------------































# ---------------------------------------------------------------------------
# 第二优先级：分布 / 直方图 / 文本 / 圆上点 / 轨迹
# ---------------------------------------------------------------------------





















# ---------------------------------------------------------------------------
# 三维统计图（网格对象，走既有 polyhedron 渲染管线）
# ---------------------------------------------------------------------------































# ---------------------------------------------------------------------------
# 第三优先级：矩阵
# ---------------------------------------------------------------------------

















# ---------------------------------------------------------------------------
# 第三优先级：圆弧/扇形 / 解不等式 / 对象锁定
# ---------------------------------------------------------------------------











def _sol_lo(part: str) -> float:
    """排序键：区间下界。"""
    import re
    m = re.match(r"[\[(]\s*(-?[0-9.]+)", part)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return -1e18   # -∞ 排最前




# ---------------------------------------------------------------------------
# 编辑命令：Delete / Rename / Redefine / SetColor / SetVisible
# ---------------------------------------------------------------------------

















# ---------------------------------------------------------------------------
# 自定义宏（Macro）
# ---------------------------------------------------------------------------







# ---------------------------------------------------------------------------
# 中文命令别名（GGB 中文版风格）
# ---------------------------------------------------------------------------

# 规范显示名（命令解析大小写不敏感；帮助面板/补全用它展示与插入）




# ---------------------------------------------------------------------------
# 结果类型提示（自动标签用）
# ---------------------------------------------------------------------------



def process_line(cons, line: str) -> List:
    # 多结果命令的单一元素重放：#idx 后缀
    idx = None
    m = re.match(r"^(.*)#(\d+)$", line.strip())
    if m:
        line = m.group(1)
        idx = int(m.group(2))
    fm = re.match(r"^y\s*~\s*(.+)$", line.strip())
    if fm:
        return _fit_expr(cons, line, line)
    label, kind, payload = parse_line(cons, line)

    if kind == "parametric":
        # 裸参数曲线：(cos(t), sin(t)) 或 f(t)=...（payload 含可选参数名）
        xb, yb = payload[0], payload[1]
        pname = payload[2] if len(payload) == 3 else "t"
        if label is None:
            label = cons.auto_label("parametric")
        defn = label + "=" + xb + "," + yb
        el = GeoCurve(label, defn, xb, yb, pname, -2 * math.pi, 2 * math.pi)
        el.set_deps(_num_deps(cons, defn), _curve_compute(xb, yb, pname, "parametric"))
        return [cons.add(el)]

    if kind == "polar":
        if label is None:
            label = cons.auto_label("polar")
        return [_cmd_polar(cons, label + "=Polar[" + payload[0] + "]", [payload[0]])]

    if kind == "implicit":
        if label is None:
            label = cons.auto_label("implicit")
        return [_cmd_implicit(cons, label + "=Implicit[" + payload[0] + "]", [payload[0]])]

    if kind == "list_index":
        lname, arg = payload
        L = _resolve(cons, lname, ("list",))
        if label is None:
            label = cons.auto_label("number")
        defn = label + "=" + lname + "(" + arg + ")"
        if L.itemkind in ("point", "point3d"):
            three = L.itemkind == "point3d"

            def fn(d):
                idx = int(eval_number(cons, arg)) - 1
                items = d[0].items
                if idx < 0 or idx >= len(items):
                    raise GeoError("索引越界: " + arg)
                p = items[idx]
                if three:
                    return {"x": p[0], "y": p[1], "z": p[2]}
                return {"x": p[0], "y": p[1]}
            return [_mk(cons, GeoPoint, "point", defn, [L], fn)]
        def fn(d):
            idx = int(eval_number(cons, arg)) - 1
            items = d[0].items
            if idx < 0 or idx >= len(items):
                raise GeoError("索引越界: " + arg)
            return {"value": items[idx]}
        return [_mk(cons, GeoNumber, "number", defn, [L], fn)]

    if kind == "point":
        if len(payload) == 3:
            x, y, z = payload
            if label is None:
                label = cons.auto_label("point")
            el = GeoPoint(label, label + "=(" + _fmt(x) + "," + _fmt(y) + "," + _fmt(z) + ")", x, y, True, z)
            return [cons.add(el)]
        x, y = payload
        if label is None:
            label = cons.auto_label("point")
        el = GeoPoint(label, label + "=(" + _fmt(x) + "," + _fmt(y) + ")", x, y)
        return [cons.add(el)]

    if kind == "ineq_y":
        if label is None:
            label = cons.auto_label("inequality")
        return [_make_ineq_y(cons, label, payload[0], payload[1])]

    if kind == "ineq_general":
        if label is None:
            label = cons.auto_label("inequality")
        op, lhs, rhs = payload
        return [_make_ineq_general(cons, label, op, lhs, rhs)]

    if kind == "list":
        items, itemkind = payload
        if label is None:
            label = cons.auto_label("list")
        el = GeoList(label, label + "=" + _list_defn(items, itemkind), items, itemkind)
        return [cons.add(el)]

    if kind == "vector":
        dx, dy = payload
        if label is None:
            label = cons.auto_label("vector")
        el = GeoVector(label, label + "=(" + _fmt(dx) + "," + _fmt(dy) + ")", dx, dy)
        return [cons.add(el)]

    if kind == "complex":
        if label is None:
            label = cons.auto_label("complex")
        return [_complex_build(cons, label, payload)]

    if kind == "number":
        if label is None:
            label = cons.auto_label("number")
        el = GeoNumber(label, label + "=" + _fmt(payload), payload)
        return [cons.add(el)]

    if kind == "value":
        # 函数求值：f(2) → 数值对象（依赖函数与参数）
        fname, arg = payload
        f = _resolve(cons, fname, ("function",))
        deps = [f]
        arg_el = cons.elements.get(arg.strip())
        if arg_el is not None and arg_el.kind in ("number", "angle"):
            deps.append(arg_el)
            fixed = None
        else:
            fixed = eval_number(cons, arg)
        if label is None:
            label = cons.auto_label("number")
        defn = label + "=" + fname + "(" + arg + ")"

        def fn(d):
            import sympy
            xv = fixed if fixed is not None else d[1].value
            try:
                v = float(sympy.N(d[0].expr.subs(d[0].xsym, xv)))
            except Exception:
                raise GeoError("函数在该点无法求值")
            return {"value": v}
        return [_mk(cons, GeoNumber, "number", defn, deps, fn)]

    if kind == "function":
        if label is None:
            label = cons.auto_label("function")
        return [_make_function(cons, label, payload)]

    # command
    name, args = payload
    lname = name.lower()
    lname = ALIASES.get(lname, lname)   # 中文别名归一化
    handler = COMMANDS.get(lname)
    if handler is None:
        # 自定义宏：宏名[实参...]（宏名区分大小写，用原始 name 查表）
        from . import macro
        if name in macro.registry(cons):
            created = macro.run_macro(cons, name, args, label)
            if created is None:
                raise GeoError("宏执行失败: " + name)
            return created
        raise GeoError("未知命令: " + name + "（支持: " + ", ".join(sorted(COMMANDS)) + "）")
    if label is None:
        # 自动标签：需要知道结果类型 → 预注册占位
        kind_hint = _label_kind(cons, lname, args)
        label = cons.auto_label(kind_hint)
        defn = label + "=" + line.strip()
    else:
        defn = line.strip()
    if idx is not None and not defn.rstrip().endswith("#" + str(idx)):
        defn += "#" + str(idx)   # 保留多结果序号，保证 .ggk/.ggb 往返取同一分支
    if lname in ("intersect", "extremum", "focus", "tangent"):
        created = handler(cons, defn, args, idx)
    else:
        created = handler(cons, defn, args)
    return created if isinstance(created, list) else [created]