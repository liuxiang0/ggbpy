# ggbpy · Python 动态几何教学软件

> 用 Python 从头实现的「动态几何 + 代数 + CAS + 3D + 定理证明」一体化教学平台（GeoGebra 启发的交互理念，代码完全原创，BSD-3-Clause）。

`Python 3.12` · `FastAPI` · 原生 HTML5 Canvas（零构建）· **190 条命令** · 检测 **11/11 全绿（1927 断言）**

---

## ✨ 项目简介

ggbpy 是**浏览器端使用、Python 后端驱动**的动态几何软件：几何对象以**依赖图（DAG）**组织，拖动自由点即沿拓扑序**增量重算**派生对象，符号计算底座为 **SymPy**。前端为原生 HTML5 Canvas（零框架），支持中英双语、明暗主题与移动端触控。

数学内核与 Web 服务分离（平台无关 Python 包 + FastAPI），既可作为教学演示工具，也可作为「Python 动态几何」的参考实现阅读与扩展。

## 🚀 快速开始

```bash
pip install -r requirements.txt
./run.sh                              # 默认 8090；PORT=8091 ./run.sh 可改
```

打开 <http://127.0.0.1:8090>，输入：

```text
A=(1,1)  B=(5,2)
s=Segment[A,B]  M=Midpoint[A,B]
```

拖 A/B 实时重算；`?` 打开命令帮助，输入框支持签名补全（Tab / Shift+Tab 跳参）。

## 🎯 功能总览

- **2D 几何**：点 / 线段 / 射线 / 直线 / 圆 / 圆弧 / 扇形 / 多边形 / 刚性多边形 / 折线 / 向量 / 轨迹 / 文本；中点、垂线、平行线、中垂线、角平分线、切线、外接圆、内心、正多边形等构造；椭圆 / 双曲线 / 抛物线 / 五点圆锥曲线；平移 / 旋转 / 镜像 / 位似 / 反演；`Delaunay` / `Voronoi` 剖分。
- **代数**：自由点、数值、函数（SymPy 解析）、裸语法（隐式方程 / 参数曲线 / 极坐标 / 回归 / 列表）、`Derivative` / `Integral` / `Root` / `Intersect`、`If` 分段、表达式依赖化、`Solve` / `NSolve` / `Limit` / `SolveODE` 等 CAS 算子接线为构造命令。
- **交互**：分类工具栏（**11 个分类** / 79 按钮）、网格吸附（2D Shift / 3D Ctrl）、视图按钮、`Ctrl+Shift+G/X/S` 快捷键、滑块（播放 / 竖直 / 像素长度）、`Button` / `CheckBox` / `InputBox`、命令栏补全与 LaTeX 预览；`share/figures/` 内置示例。
- **CAS 面板**：11 个命令按钮，`#N` 引用前序单元，`a:=5` / `f(x):=x^2` 联动绘图区。
- **统计**：8 类统计图（柱 / 直方 / 箱线 / 饼 / 折线 / 散点 / 点图 / 茎叶），可整体拖动；黎曼和。
- **3D**：点 / 线 / 面 / 球 / 锥 / 柱 / 棱柱 / 棱锥 + 五种正多面体；`Surface` / `SurfaceParam` / `ImplicitSurface`；旋转缩放平移、控制点拖动、画家算法与 hidden-line；真三维度量、`Volume` / `Area`、多种求交与 3D 测量工具。
- **证明 / 脚本 / 导出**：`AreParallel` 等关系判定 + `Prove`；`Set*` 脚本、自定义宏、`.ggs`；`.ggk` / `.ggb` 保存加载；SVG / PNG / OBJ / STL / glTF 导出与 OBJ / STL / glTF / 图片导入；试卷 HTML、短链接分享。
- **界面**：中 / EN（各 **228** 条，检测锁定键集合）、明暗主题、移动端、Retina；对象列表行内编辑、虚拟数学键盘。

#### ⚠️ 限制与边界（由检测矩阵锁定）

#### 2D 限制

- **撤销/重做**：快照式，撤销栈上限 `UNDO_LIMIT = 200`；重做走计算记忆。
- **计算记忆**：按定义式 + 依赖状态签名缓存，≤ 96 条 / 约 60 万坐标；随机类不参与。
- **嵌套命令**：`Cmd[...]` 最多 **4 层**；匿名辅助元素不进列表 / 撤销 / 序列化。
- **角度语义**：`Angle[A,B,C]` 为 BA→BC 逆时针有向角，范围 [0°,360°)；3D 用真三维夹角。
- **周长/长度/面积**：`Perimeter` 只对封闭图形，开放曲线报错指向 `Length`；`Length` 对扇形只取弧长；`Area` 对圆弧报错指向 `Sector`；3D 用 `Volume` / `SurfaceArea`。
- **统计图**：柱高 `CHART_H = 3`、饼半径 `PIE_R = 3`；饼图非负且总和为正、直方图非空且有变化、折线 x/y 等长；`StemPlot` 仅非负有限数据。
- **剖分**：`Delaunay` ≥3 点，共线/重合报退化；`Voronoi` ≥2 点，外扩 15% 包围盒，元胞有界。
- **工具与词条**：工具面板 **11 个分类**；zh / en 各 **228 条**，键集合由检测锁定。
- **保存/导出**：`.ggk` JSON；`.ggb` 按命令重放并内嵌网格/图片；SVG 的 `Image` 用 data URI，类型覆盖由白名单锁定。
- **其它**：`Solve` 只返回实根；`SolveODE` 仅通解；`NSolve` 默认区间 [-60,60]；`Implicit` 需含 x、y。

#### 3D 限制

- **求交**：支持面×面、线×面、平面×立体（截面）、球×平面/球×球/球×空间圆、空间圆相关、体×体（凸交）、体/球×线；球面×曲面、体×空间圆尚未支持，明确报错。
- **曲面/网格**：`ImplicitSurface` 为 marching tetrahedra 近似（粗网格面积误差约 0.1%–8%），`Volume` 无定义；OBJ/STL 只保留几何。
- **精度与让出**：3D 点带真实 z；SVG 默认 2D，`?view3d=1` 出 3D；隐式曲面每 ~5 ms 协作让出（`GGBPY_YIELD_MS`）。

## 🧪 检测与质量

```bash
bash devtools/run_all_detection.sh     # 全量 11 步 / 1927 断言（提交前门禁，服务在 8090）
bash devtools/run_scope.sh quick       # 迭代：registry + kernel2d + core + docs（~4s）
bash devtools/run_scope.sh docs        # 纯文档
```

分范围：`docs` / `registry` / `kernel2d` / `api2d` / `core` / `content2d` / `kernel3d` / `api3d` / `ui2d` / `ui3d` / `all`。提交前纯文档跑 `docs`，任何代码改动跑 `all` 并看到「全部检测通过」；各步断言与耗时以脚本输出为准，历史数字见 [CHANGELOG.md](CHANGELOG.md)。

## 🧱 架构

`kernel/` 平台无关内核（`elements.py` 对象模型、`construction.py` DAG/撤销/序列化、`registry.py` 命令单一来源、`commands*.py`、`tolerance.py`、`memo.py`、`cas.py` / `prover.py`）；`server/main.py` FastAPI 服务；`server/static/` 零构建前端；`devtools/` 检测矩阵；`share/figures/` 示例。

核心：对象挂在依赖图上 → 拖动自由点沿拓扑序增量重算；编辑沿依赖链传播并保留样式，全部操作可撤销/重做（快照式）。

## 📖 命令示例

```text
A=(1,1)  B=(5,2)  C=(3,6)
M=Midpoint[A,C]
g=Line[A,B]
c=Circle[A,B]
f(x)=x^2-2*x+1
df=Derivative[f]
area=Integral[f,0,4]
s=Slider[0,10,1,(-3,-4)]  f2(x)=s*x
D=Delaunay[{A,B,C,(4,5),(7,2)}]
Prove[AreParallel[g, Line[M,C]]]
```

全部 190 条命令、237 个别名见 **`?` 帮助面板**或 `GET /api/commands`；中文别名同样可嵌套。

## 📦 发布到 Gitee

```bash
git remote add origin https://gitee.com/<用户名>/ggbpy.git
git push -u origin main
```

完整步骤（新建空仓库、SSH 免密、常见问题）见 [`GITEE_UPLOAD.md`](GITEE_UPLOAD.md)。

## 📜 变更历史

本项目按「批」开发，功能、修复与各批检测数字都记录在 **[CHANGELOG.md](CHANGELOG.md)**；本 README 只描述当前状态。

## 📄 许可与致谢

- 本仓库代码为**原创**实现（BSD-3-Clause）。
- 设计交互思想参考 GeoGebra（EUPL 1.2，仅限非商用）；**不包含** GeoGebra 任何源码。
- 符号计算：SymPy（BSD）；Web 服务：FastAPI；数学渲染：KaTeX（MIT）。
