"""命令**参数签名**（供前端补全/帮助显示「完整输入内容」）。

设计：
- 只列「值得展示参数」的常用命令；未列出的命令回退为 ``名字[…]``（覆盖可增量扩充）
- 签名用**中英混排的中性写法**：``?`` 表示可选，``…`` 表示可继续追加
- 真实校验仍在各命令处理器里（这里只为输入体验服务，不作为唯一真相）
"""
from __future__ import annotations

from typing import Dict

SIGNATURES: Dict[str, str] = {
    # —— 滑块与交互控件 ——
    "slider": "Slider[最小值, 最大值, 步长?, (x,y)?, vertical?, px?]",
    "setslider": "SetSlider[滑块, 最小值, 最大值, 步长?]",
    "setsliderlength": "SetSliderLength[滑块, 像素长度]",
    "setslidervertical": "SetSliderVertical[滑块, true/false]",
    "button": 'Button["说明", "命令1;命令2", (x,y)?]',
    "checkbox": 'CheckBox["说明", 目标对象, (x,y)?]',
    "inputbox": "InputBox[目标对象, (x,y)?]",
    "setcaption": 'SetCaption[对象, "新说明"]',
    "setscript": 'SetScript[按钮, "命令1;命令2"]',
    "setwidgetpos": "SetWidgetPos[控件|滑块, (x,y)]",
    "setinput": 'SetInput[目标, "数值或表达式"]',
    "text": 'Text["模板(可含 + 引用)", 点或(x,y)]',
    "image": "Image[角点1, 角点2, 图片数据或URL]",
    # —— 点/线/圆/多边形 ——
    "point": "Point[(x,y)] 或 点标签= (x,y)",
    "midpoint": "Midpoint[点, 点] 或 Midpoint[线段]",
    "intersect": "Intersect[对象1, 对象2]",
    "segment": "Segment[点, 点]",
    "line": "Line[点, 点]",
    "ray": "Ray[点, 点]",
    "vector": "Vector[点, 点] 或 Vector[(dx,dy)]",
    "circle": "Circle[圆心, 半径或点]",
    "semicircle": "Semicircle[点, 点]",
    "arc": "Arc[圆心, 点, 点]",
    "polygon": "Polygon[点1, 点2, 点3, …]",
    "regpoly": "Polygon[点, 点, 边数]",
    "incircle": "Incircle[点, 点, 点]",
    "circumcircle": "Circle[点, 点, 点] 三点外接圆",
    "perpbis": "PerpendicularBisector[点, 点]",
    "anglebis": "AngleBisector[点, 点, 点]",
    "tangent": "Tangent[点, 圆] 或 Tangent[点, 曲线]",
    "compass": "Compass[点, 线段]",
    "polyline": "Polyline[点1, 点2, …]",
    "locus": "Locus[点, 动点]",
    # —— 测量 ——
    "distance": "Distance[对象1, 对象2]",
    "angle": "Angle[点A, 顶点B, 点C]（有向 0..360°）",
    "slope": "Slope[直线]",
    "area": "Area[多边形或圆]",
    "perimeter": "Perimeter[多边形或圆]",
    # —— 函数与统计图 ——
    "function": "f(x)=表达式 或 Function[表达式]",
    "barchart": "BarChart[{值…}] 或 BarChart[{值…}, {标签…}]",
    "dotplot": "DotPlot[{值…}]",
    "linechart": "LineChart[{值…}]",
    "scatterplot": "ScatterPlot[{点…}]",
    "stemplot": "StemPlot[{值…}]",
    "histogram": "Histogram[{值…}, 组数]",
    "boxplot": "BoxPlot[{值…}]",
    "piechart": "PieChart[{值…}]",
    # —— 剖分 ——
    "delaunay": "Delaunay[{点…}]",
    "voronoi": "Voronoi[{点…}]",
    # —— 变换 ——
    "reflect": "Reflect[对象, 直线或点]",
    "rotate": "Rotate[对象, 角度, 旋转中心]",
    "translate": "Translate[对象, 向量]",
    "dilate": "Dilate[对象, 比例, 中心]",
    # —— 编辑与脚本 ——
    "setvalue": "SetValue[数值对象, 新值]",
    "setcoords": "SetCoords[自由点, x, y]",
    "setcolor": 'SetColor[对象, "颜色名或#RRGGBB"]',
    "setvisible": "SetVisible[对象, true/false]",
    "setlocked": "SetLocked[对象, true/false]",
    "rename": "Rename[对象, 新标签]",
    "redefine": "Redefine[对象, 对象=新定义]",
    "delete": "Delete[对象]",
    "zoom": "ZoomIn[(x,y)] 需先选工具",
    # —— CAS ——
    "solve": "Solve[方程 或 方程组, 变量?]",
    "nsolve": "NSolve[方程, 变量?, 初值?]",
    "limit": "Limit[表达式, 变量→值]",
    "derivative": "Derivative[表达式, 变量?]",
    "integral": "Integral[表达式, 变量?, 下限?, 上限?]",
    "substitute": "Substitute[表达式, 替换规则]",
    "solveode": "SolveODE[方程, 函数名, 自变量]",
    "partialfractions": "PartialFractions[表达式, 变量]",
    # —— 3D ——
    "sphere": "Sphere[球心, 半径]",
    "cube": "Cube[点, 点]",
    "cone": "Cone[底心, 顶点, 半径]",
    "cylinder": "Cylinder[底心, 顶心, 半径]",
    "prism": "Prism[多边形, 高度]",
    "pyramid": "Pyramid[多边形, 高度]",
    "tetra": "Tetrahedron[点, 点, 点, 点]",
    "plane3d": "Plane[点, 点, 点]",
    "surfacearea": "SurfaceArea[立体]",
    "volume": "Volume[立体]",
}


def signature_of(key: str, display: str) -> str:
    """取签名；未登记的命令回退为 ``名字[…]``（提示「有参数但未登记」）。"""
    sig = SIGNATURES.get(key)
    if sig:
        return sig
    return display + "[…]"


def all_signatures(keys, displays) -> Dict[str, str]:
    return {k: signature_of(k, displays.get(k, k)) for k in keys}
