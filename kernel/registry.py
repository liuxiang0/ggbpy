"""命令注册单一来源（P1-F / REVIEW #6）。

**新增或修改命令只改一处**：`SPECS` 列表。四张表都由它派生：
- ``COMMANDS``      命令名 → 实现函数
- ``ALIASES``       中文/英文别名 → 规范命令名
- ``DISPLAY_NAMES`` 命令 → CamelCase 显示名（未提供则回退首字母大写）
- ``RESULT_KINDS``  命令 → 结果类型（自动标签/类型提示）

派生是纯函数且顺序稳定（保持 SPECS 顺序），因此 `commands.py` 的调度器、
`_result_kind` 命名助手与 `/api/commands` 端点的行为不变。
一致性由 ``devtools/test_registry.py`` 保证（每条命令都有结果类型、别名都指向真实命令、
显示名唯一等）。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Tuple

from .cmd_util import _lookup
from .cas_cmds import (_cmd_limit, _cmd_nsolve, _cmd_partialfractions,
                       _cmd_solve, _cmd_solveode, _cmd_substitute)
from .calculus import _cmd_derivative, _cmd_divisors, _cmd_extremum, _cmd_factorslist, _cmd_fitexpr, _cmd_integral, _cmd_isprime, _cmd_normaldist, _cmd_rectsum, _cmd_root, _cmd_sequence, _cmd_solveineq
from .centers import _cmd_circumcenter, _cmd_excenter, _cmd_orthocenter
from .charts import _cmd_stemplot
from .charts import _cmd_barchart, _cmd_barchart3d, _cmd_boxplot, _cmd_dotplot, _cmd_histogram, _cmd_linechart, _cmd_piechart, _cmd_scatterplot, _cmd_scatterplot3d, _cmd_surfacechart3d
from .commands3d import _cmd_area, _cmd_bbox, _cmd_cone, _cmd_convexhull, _cmd_covariance, _cmd_cube, _cmd_cylinder, _cmd_dodecahedron, _cmd_fitplane, _cmd_fitsphere, _cmd_hexahedron, _cmd_icosahedron, _cmd_implicit_surface, _cmd_mesh, _cmd_octahedron, _cmd_plane, _cmd_prism, _cmd_pyramid, _cmd_sphere, _cmd_surface, _cmd_surface_param, _cmd_surfacepoint, _cmd_surfaceproject, _cmd_tetrahedron, _cmd_volume, _cmd_surfacearea
from .conics import _cmd_conic5, _cmd_diameter, _cmd_ellipse, _cmd_focus, _cmd_hyperbola, _cmd_implicit, _cmd_parabola, _cmd_parametric, _cmd_polar
from .editing import _cmd_delete, _cmd_macrodelete, _cmd_redefine, _cmd_rename, _cmd_setcolor, _cmd_setcoords, _cmd_setlocked, _cmd_setvalue, _cmd_setvisible, _cmd_slider
from .fits import _cmd_cov_ellipsoid, _cmd_fitexp, _cmd_fitlog, _cmd_fitpoly, _cmd_fitpow, _cmd_fitsin, _cmd_pmcc
from .io_cmds import _cmd_image, _cmd_text
from .iteration import _cmd_iteration, _cmd_iterationlist, _cmd_locus
from .linalg import _cmd_arg, _cmd_conj, _cmd_det, _cmd_dot, _cmd_im, _cmd_inverse, _cmd_matrix, _cmd_re, _cmd_transpose
from .macros import _cmd_macrocreate, _cmd_macrolist
from .measures import _cmd_angle, _cmd_circumference, _cmd_distance, _cmd_length, _cmd_perimeter, _cmd_radius, _cmd_semiperimeter, _cmd_slope
from .misc import _cmd_randombetween, _cmd_randomize, _cmd_setwire
from .numeric import _cmd_complex_abs, _cmd_gcd, _cmd_iqr, _cmd_lcm, _cmd_max, _cmd_mean, _cmd_median, _cmd_min, _cmd_mode, _cmd_ncr, _cmd_normal, _cmd_npr, _cmd_q1, _cmd_q3, _cmd_sort, _cmd_stdev, _cmd_sum, _cmd_variance, _cmd_isfinite
from .primitives import _cmd_anglebisector, _cmd_arc, _cmd_arecollinear, _cmd_areparallel, _cmd_areperpendicular, _cmd_centroid, _cmd_circle, _cmd_fitline, _cmd_foot, _cmd_incenter, _cmd_incircle, _cmd_intersect, _cmd_isoline, _cmd_line, _cmd_midpoint, _cmd_perpbis, _cmd_perpendicularline, _cmd_pointoncircle, _cmd_pointonpath, _cmd_polygon, _cmd_polyline, _cmd_randpointin, _cmd_ray, _cmd_regularpolygon, _cmd_rigidpolygon, _cmd_sector, _cmd_segment, _cmd_semicircle, _cmd_tangent, _cmd_vector
from .proofs import _cmd_areconcurrent, _cmd_areconcyclic, _cmd_arecongruent, _cmd_prove
from .widgets import (_cmd_button,
                      _cmd_checkbox,
                      _cmd_inputbox,
                      _cmd_setcaption,
                      _cmd_setinput,
                      _cmd_setscript,
                      _cmd_setslider,
                      _cmd_setsliderlength,
                      _cmd_setslidervert,
                      _cmd_setwidgetpos)
from .tessellation import _cmd_delaunay, _cmd_voronoi
from .transforms import _cmd_dilate, _cmd_invert, _cmd_reflect, _cmd_rotate, _cmd_translate


# 单一来源：命令规格（命令名, 实现函数, 显示名, 结果类型, 别名）
SPECS: List[Tuple[str, Callable, str, str, Tuple[str, ...]]] = [
    ("midpoint", _cmd_midpoint, "", "point", ("中点",)),
    ("line", _cmd_line, "", "line", ("直线",)),
    ("segment", _cmd_segment, "", "segment", ("线段",)),
    ("ray", _cmd_ray, "", "ray", ("射线",)),
    ("circle", _cmd_circle, "", "circle", ("圆", "外接圆")),
    ("circumcircle", _cmd_circle, "CircumCircle", "circle", ()),
    ("polygon", _cmd_polygon, "", "polygon", ("多边形",)),
    ("rigidpolygon", _cmd_rigidpolygon, "RigidPolygon", "polygon", ("刚体多边形", "刚性多边形")),
    ("intersect", _cmd_intersect, "", "point", ("交点",)),
    ("distance", _cmd_distance, "", "number", ("距离",)),
    ("slope", _cmd_slope, "", "number", ("斜率",)),
    ("angle", _cmd_angle, "", "angle", ("角度",)),
    ("length", _cmd_length, "", "number", ("长度", "弧长")),
    ("translate", _cmd_translate, "", "point", ("平移",)),
    ("rotate", _cmd_rotate, "", "point", ("旋转",)),
    ("reflect", _cmd_reflect, "", "point", ("对称", "镜像")),
    ("invert", _cmd_invert, "", "point", ("反演",)),
    ("image", _cmd_image, "", "image", ("图像", "图片", "插入图片")),
    ("vector", _cmd_vector, "", "vector", ("向量",)),
    ("derivative", _cmd_derivative, "", "function", ("导数",)),
    ("integral", _cmd_integral, "", "function", ("积分",)),
    ("tangent", _cmd_tangent, "", "line", ("切线",)),
    ("root", _cmd_root, "", "point", ("求根",)),
    ("extremum", _cmd_extremum, "", "point", ("极值",)),
    ("ellipse", _cmd_ellipse, "", "conic", ("椭圆",)),
    ("hyperbola", _cmd_hyperbola, "", "conic", ("双曲线",)),
    ("parabola", _cmd_parabola, "", "conic", ("抛物线",)),
    ("conic", _cmd_conic5, "", "conic", ("圆锥曲线",)),
    ("focus", _cmd_focus, "", "point", ("焦点",)),
    ("sum", _cmd_sum, "", "number", ("求和",)),
    ("mean", _cmd_mean, "", "number", ("平均",)),
    ("median", _cmd_median, "", "number", ("中位数",)),
    ("mode", _cmd_mode, "", "number", ("众数",)),
    ("variance", _cmd_variance, "", "number", ("方差",)),
    ("stdev", _cmd_stdev, "", "number", ("标准差",)),
    ("min", _cmd_min, "", "number", ("最小值",)),
    ("max", _cmd_max, "", "number", ("最大值",)),
    ("sort", _cmd_sort, "", "list", ("排序",)),
    ("fitline", _cmd_fitline, "FitLine", "line", ("直线拟合",)),
    ("fitpoly", _cmd_fitpoly, "FitPoly", "function", ("多项式拟合",)),
    ("fitexpr", _cmd_fitexpr, "FitExpr", "function", ("回归", "拟合")),
    ("sphere", _cmd_sphere, "", "geo3d", ("球", "球面")),
    ("surface", _cmd_surface, "", "geo3d", ("曲面",)),
    ("fitplane", _cmd_fitplane, "FitPlane", "geo3d", ("平面拟合", "拟合平面")),
    ("mesh", _cmd_mesh, "", "geo3d", ("导入网格", "网格")),
    ("surfaceparam", _cmd_surface_param, "SurfaceParam", "geo3d", ("参数曲面",)),
    ("implicitsurface", _cmd_implicit_surface, "ImplicitSurface", "geo3d", ("隐式曲面",)),
    ("linechart", _cmd_linechart, "LineChart", "linechart", ("折线", "折线图")),
    ("scatterplot", _cmd_scatterplot, "ScatterPlot", "scatterplot", ("散布图", "散点图")),
    ("dotplot", _cmd_dotplot, "DotPlot", "dotplot", ("点图", "点阵图")),
    ("barchart3d", _cmd_barchart3d, "BarChart3D", "geo3d", ("三维条形图", "三维柱状图")),
    ("scatterplot3d", _cmd_scatterplot3d, "ScatterPlot3D", "geo3d", ("三维散点图",)),
    ("surfacechart3d", _cmd_surfacechart3d, "SurfaceChart3D", "geo3d", ("三维曲面图", "高度场")),
    ("fitsphere", _cmd_fitsphere, "FitSphere", "geo3d", ("拟合球", "球拟合")),
    ("boundingbox", _cmd_bbox, "BoundingBox", "geo3d", ("包围盒", "点云包围盒")),
    ("covariance", _cmd_covariance, "", "matrix", ("协方差", "协方差矩阵")),
    ("covarianceellipsoid", _cmd_cov_ellipsoid, "CovarianceEllipsoid", "geo3d", ("协方差椭球", "椭球")),
    ("surfaceisoline", _cmd_isoline, "SurfaceIsoline", "geo3d", ("参数线",)),
    ("convexhull", _cmd_convexhull, "ConvexHull", "geo3d", ("凸包",)),
    ("surfacepoint", _cmd_surfacepoint, "SurfacePoint", "point", ("曲面取点",)),
    ("surfaceproject", _cmd_surfaceproject, "SurfaceProject", "point", ("曲面投影",)),
    ("plane", _cmd_plane, "", "geo3d", ("平面",)),
    ("cube", _cmd_cube, "", "geo3d", ("立方体",)),
    ("cone", _cmd_cone, "", "geo3d", ("圆锥",)),
    ("cylinder", _cmd_cylinder, "", "geo3d", ("圆柱",)),
    ("prism", _cmd_prism, "", "geo3d", ("三棱柱", "棱柱")),
    ("pyramid", _cmd_pyramid, "", "geo3d", ("三棱锥", "棱锥")),
    ("tetrahedron", _cmd_tetrahedron, "", "geo3d", ("正四面体",)),
    ("octahedron", _cmd_octahedron, "", "geo3d", ("正八面体",)),
    ("hexahedron", _cmd_hexahedron, "", "geo3d", ("正六面体", "正方体")),
    ("icosahedron", _cmd_icosahedron, "", "geo3d", ("正二十面体",)),
    ("dodecahedron", _cmd_dodecahedron, "", "geo3d", ("正十二面体",)),
    ("areparallel", _cmd_areparallel, "AreParallel", "boolean", ("平行",)),
    ("areperpendicular", _cmd_areperpendicular, "ArePerpendicular", "boolean", ("垂直",)),
    ("arecollinear", _cmd_arecollinear, "AreCollinear", "boolean", ("共线",)),
    ("areconcyclic", _cmd_areconcyclic, "AreConcyclic", "boolean", ("共圆",)),
    ("arecongruent", _cmd_arecongruent, "AreCongruent", "boolean", ("相等",)),
    ("areconcurrent", _cmd_areconcurrent, "AreConcurrent", "boolean", ("共点",)),
    ("prove", _cmd_prove, "", "boolean", ("证明",)),
    ("sequence", _cmd_sequence, "Sequence", "list", ("序列",)),
    ("fitexp", _cmd_fitexp, "", "function", ("指数拟合",)),
    ("fitlog", _cmd_fitlog, "", "function", ("对数拟合",)),
    ("fitpow", _cmd_fitpow, "", "function", ("幂拟合",)),
    ("fitsin", _cmd_fitsin, "", "function", ("正弦拟合",)),
    ("setcoords", _cmd_setcoords, "SetCoords", "number", ("坐标",)),
    ("setvalue", _cmd_setvalue, "SetValue", "number", ("赋值",)),
    ("delete", _cmd_delete, "", "point", ("删除",)),
    ("rename", _cmd_rename, "", "point", ("重命名",)),
    ("redefine", _cmd_redefine, "", "point", ("重定义",)),
    ("setcolor", _cmd_setcolor, "SetColor", "point", ("颜色",)),
    ("setvisible", _cmd_setvisible, "SetVisible", "point", ("显示", "隐藏")),
    ("setwire", _cmd_setwire, "SetWire", "point", ("实体", "线框")),
    ("macrocreate", _cmd_macrocreate, "MacroCreate", "result", ()),
    ("macrodelete", _cmd_macrodelete, "MacroDelete", "result", ()),
    ("macrolist", _cmd_macrolist, "MacroList", "result", ()),
    ("polyline", _cmd_polyline, "", "polyline", ()),
    ("dilate", _cmd_dilate, "", "point", ("位似", "缩放")),
    ("perpendicularline", _cmd_perpendicularline, "PerpendicularLine", "line", ("垂线", "平行线")),
    ("foot", _cmd_foot, "", "point", ("垂足",)),
    ("anglebisector", _cmd_anglebisector, "AngleBisector", "line", ("角平分线",)),
    ("perpendicularbisector", _cmd_perpbis, "PerpendicularBisector", "line", ("中垂线",)),
    ("regularpolygon", _cmd_regularpolygon, "RegularPolygon", "polygon", ("正多边形",)),
    ("area", _cmd_area, "", "number", ("表面积", "面积")),
    ("volume", _cmd_volume, "", "number", ("体积",)),
    # 新功能（REVIEW §6 #1/#2）：CAS 算子接线 + 表面积/有限性判定
    ("solve", _cmd_solve, "Solve", "list", ("求解方程", "解方程")),
    ("nsolve", _cmd_nsolve, "NSolve", "list", ("数值解", "数值求解")),
    ("limit", _cmd_limit, "Limit", "number", ("极限",)),
    ("partialfractions", _cmd_partialfractions, "PartialFractions", "function", ("部分分式", "分式分解")),
    ("substitute", _cmd_substitute, "Substitute", "function", ("代入", "替换")),
    ("solveode", _cmd_solveode, "SolveODE", "result", ("微分方程", "解微分方程")),
    ("surfacearea", _cmd_surfacearea, "SurfaceArea", "number", ("表面积", "曲面面积")),
    ("isfinite", _cmd_isfinite, "IsFinite", "boolean", ("是否有限", "有限")),
    ("delaunay", _cmd_delaunay, "Delaunay", "list", ("三角剖分", "德劳内")),
    ("voronoi", _cmd_voronoi, "Voronoi", "list", ("泰森多边形", "沃罗诺伊")),
    ("stemplot", _cmd_stemplot, "StemPlot", "stemplot", ("茎叶图",)),
    ("button", _cmd_button, "Button", "button", ("按钮",)),
    ("checkbox", _cmd_checkbox, "CheckBox", "checkbox", ("复选框", "勾选框")),
    ("inputbox", _cmd_inputbox, "InputBox", "inputbox", ("输入框",)),
    ("setwidgetpos", _cmd_setwidgetpos, "SetWidgetPos", "point", ("控件位置", "移动控件")),
    ("setcaption", _cmd_setcaption, "SetCaption", "point", ("设置说明", "改说明")),
    ("setscript", _cmd_setscript, "SetScript", "point", ("设置脚本", "改脚本")),
    ("setinput", _cmd_setinput, "SetInput", "point", ("输入框提交", "提交输入")),
    ("setslider", _cmd_setslider, "SetSlider", "point", ("滑块范围", "改滑块")),
    ("setslidervertical", _cmd_setslidervert, "SetSliderVertical", "point", ("滑块方向", "竖直滑块")),
    ("setsliderlength", _cmd_setsliderlength, "SetSliderLength", "point", ("滑块长度", "改滑块长度")),
    ("perimeter", _cmd_perimeter, "", "number", ("周长",)),
    ("circumference", _cmd_circumference, "", "number", ("圆周长", "椭圆周长")),
    ("incenter", _cmd_incenter, "", "point", ("内心",)),
    ("incircle", _cmd_incircle, "", "circle", ("内切圆",)),
    ("centroid", _cmd_centroid, "Centroid", "point", ("质心", "重心")),
    ("slider", _cmd_slider, "", "number", ("滑动条",)),
    ("parametric", _cmd_parametric, "", "parametric", ("参数曲线",)),
    ("polar", _cmd_polar, "", "polar", ("极坐标",)),
    ("implicit", _cmd_implicit, "", "implicit", ("隐式", "隐式方程")),
    ("normal", _cmd_normal, "", "number", ("正态",)),
    ("normaldist", _cmd_normaldist, "NormalDist", "function", ("正态函数", "正态分布")),
    ("barchart", _cmd_barchart, "BarChart", "barchart", ("直方图",)),
    ("text", _cmd_text, "", "text", ("文本",)),
    ("pointoncircle", _cmd_pointoncircle, "PointOnCircle", "point", ("圆上点",)),
    ("pointonpath", _cmd_pointonpath, "PointOnPath", "point", ("动点",)),
    ("locus", _cmd_locus, "", "locus", ("轨迹",)),
    ("arc", _cmd_arc, "", "arc", ("圆弧", "弧")),
    ("sector", _cmd_sector, "", "arc", ("扇形",)),
    ("semicircle", _cmd_semicircle, "SemiCircle", "arc", ("半圆",)),
    ("solveineq", _cmd_solveineq, "SolveIneq", "result", ("解不等式",)),
    ("setlocked", _cmd_setlocked, "SetLocked", "point", ("锁定",)),
    ("matrix", _cmd_matrix, "", "matrix", ("矩阵",)),
    ("det", _cmd_det, "", "number", ("行列式",)),
    ("transpose", _cmd_transpose, "", "matrix", ("转置",)),
    ("inverse", _cmd_inverse, "", "matrix", ("逆矩阵",)),
    ("orthocenter", _cmd_orthocenter, "OrthoCenter", "point", ("垂心",)),
    ("circumcenter", _cmd_circumcenter, "CircumCenter", "point", ("外心",)),
    ("excenter", _cmd_excenter, "", "point", ("旁心",)),
    ("radius", _cmd_radius, "", "number", ("半径",)),
    ("diameter", _cmd_diameter, "", "number", ("直径",)),
    ("semiperimeter", _cmd_semiperimeter, "SemiPerimeter", "number", ("半周长",)),
    ("randombetween", _cmd_randombetween, "RandomBetween", "number", ("随机整数",)),
    ("randomize", _cmd_randomize, "", "number", ("重新随机", "随机化")),
    ("npr", _cmd_npr, "", "number", ("排列",)),
    ("ncr", _cmd_ncr, "", "number", ("组合",)),
    ("dot", _cmd_dot, "", "number", ("点积",)),
    ("pmcc", _cmd_pmcc, "", "number", ("相关系数",)),
    ("correlationcoefficient", _cmd_pmcc, "CorrelationCoefficient", "number", ()),
    ("leftsum", lambda c, d, a: _cmd_rectsum(c, d, a, "left"), "LeftSum", "sumrect", ("左端点矩形和",)),
    ("rightsum", lambda c, d, a: _cmd_rectsum(c, d, a, "right"), "RightSum", "sumrect", ("右端点矩形和",)),
    ("midpointsum", lambda c, d, a: _cmd_rectsum(c, d, a, "mid"), "MidpointSum", "sumrect", ("中点矩形和",)),
    ("lowersum", lambda c, d, a: _cmd_rectsum(c, d, a, "lower"), "LowerSum", "sumrect", ("下和",)),
    ("uppersum", lambda c, d, a: _cmd_rectsum(c, d, a, "upper"), "UpperSum", "sumrect", ("上和",)),
    ("trapezoidalsum", lambda c, d, a: _cmd_rectsum(c, d, a, "trap"), "TrapezoidalSum", "sumrect", ("梯形和",)),
    ("rectanglesum", lambda c, d, a: _cmd_rectsum(c, d, a, "rect"), "RectangleSum", "sumrect", ("矩形和",)),
    ("piechart", _cmd_piechart, "PieChart", "piechart", ("扇形统计图", "饼图")),
    ("histogram", _cmd_histogram, "Histogram", "barchart", ("分组直方图", "直方图分组")),
    ("q1", _cmd_q1, "", "number", ("下四分位数",)),
    ("q3", _cmd_q3, "", "number", ("上四分位数",)),
    ("iqr", _cmd_iqr, "", "number", ("四分位距",)),
    ("boxplot", _cmd_boxplot, "BoxPlot", "boxplot", ("箱线图",)),
    ("iteration", _cmd_iteration, "", "number", ("迭代",)),
    ("iterationlist", _cmd_iterationlist, "IterationList", "list", ("迭代序列", "迭代表")),
    ("gcd", _cmd_gcd, "", "number", ("最大公约数",)),
    ("lcm", _cmd_lcm, "", "number", ("最小公倍数",)),
    ("isprime", _cmd_isprime, "IsPrime", "boolean", ("素数", "质数")),
    ("divisors", _cmd_divisors, "Divisors", "list", ("因数",)),
    ("factorslist", _cmd_factorslist, "FactorsList", "list", ("质因数",)),
    ("randompointin", _cmd_randpointin, "RandomPointIn", "point", ("随机点",)),
    ("conj", _cmd_conj, "", "complex", ("共轭", "共轭复数")),
    ("conjugate", _cmd_conj, "", "complex", ()),
    ("re", _cmd_re, "", "number", ("实部",)),
    ("im", _cmd_im, "", "number", ("虚部",)),
    ("arg", _cmd_arg, "", "number", ("幅角", "辐角")),
    ("abs", _cmd_complex_abs, "", "number", ()),
]


def _derive(specs):
    """由 SPECS 派生四张表（保持 SPECS 顺序 → 行为与历史一致）。"""
    commands: Dict[str, Callable] = {}
    aliases: Dict[str, str] = {}
    displays: Dict[str, str] = {}
    kinds: Dict[str, str] = {}
    for name, fn, display, result, als in specs:
        commands[name] = fn
        kinds[name] = result
        if display:
            displays[name] = display
        for a in als:
            aliases[a] = name
    return commands, aliases, displays, kinds


COMMANDS, ALIASES, DISPLAY_NAMES, RESULT_KINDS = _derive(SPECS)



def _result_kind(name: str) -> str:
    """命令的默认结果类型（自动标签、类型提示用）。表见模块级 RESULT_KINDS（单一来源，可检测）。"""
    return RESULT_KINDS.get(name, "point")


def _label_kind(cons, lname: str, args) -> str:
    """自动标签用的「命名类型」。

    与结果类型基本一致，唯一例外是反演（Invert）：它可能产生点，也可能是圆/直线/
    曲线/多边形等图形。点反演仍按点命名（A,B,C…），其余反演像用独立的 inv1,inv2…
    前缀（小写开头，见 Construction.auto_label）——避免图形被命名成"下一个点"。
    """
    # 三维统计图：虽然结果类型是 geo3d，但用独立的命名前缀（bc3_/sc3_/sf3_）便于识别
    _chart3d = {"barchart3d": "chart3dbar", "scatterplot3d": "chart3dscatter",
                "surfacechart3d": "chart3dsurface"}
    if lname in _chart3d:
        return _chart3d[lname]
    if lname != "invert":
        return _result_kind(lname)
    try:
        el = cons.elements.get(args[0].strip()) if args else None
        if el is None and args:
            el = _lookup(cons, args[0])          # 支持嵌套命令参数
        if el is not None and getattr(el, "kind", "") == "point":
            return "point"
    except Exception:  # 防御性捕获：该分支失败不应中断用户操作
        pass
    return "invert"


# ---------------------------------------------------------------------------
# 命令表与主入口
# ---------------------------------------------------------------------------
