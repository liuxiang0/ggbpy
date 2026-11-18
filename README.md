# ggbpy · Python 动态几何教学软件

> 用 Python 从头实现的「动态几何 + 代数 + CAS + 3D + 定理证明」一体化教学平台（GeoGebra 启发的交互理念，代码完全原创，BSD-3-Clause）。

`Python 3.12` · `FastAPI` · 原生 HTML5 Canvas（零构建）· **190 条命令** · 检测 **11/11 全绿（1927 断言）**

---

## ✨ 项目简介

ggbpy 是**浏览器端使用、Python 后端驱动**的动态几何软件：几何对象以**依赖图（DAG）**组织，拖动自由点即沿拓扑序**增量重算**派生对象，符号计算底座为 **SymPy**。前端为原生 HTML5 Canvas（零框架），支持中英双语、明暗主题与移动端触控。

数学内核与 Web 服务分离（平台无关的 Python 包 + FastAPI），既可作为教学演示工具，也可作为「Python 动态几何」的参考实现阅读与扩展。

## 🚀 快速开始

```bash
pip install -r requirements.txt      # fastapi / uvicorn / sympy / numpy
./run.sh                              # 默认 8090；PORT=8091 ./run.sh 可改
```

浏览器打开 <http://127.0.0.1:8090>（也可 `python3 server/main.py --port 8090`）。

**上手三步**：

```text
A=(1,1)          # 点（可直接在画布上拖动）
B=(5,2)
s=Segment[A,B]   # 线段（随 A/B 自动重算）
M=Midpoint[A,B]  # 中点
```

拖 A 或 B，线段与中点实时跟随；`?` 打开命令帮助，输入框有签名补全（Tab / Shift+Tab 跳参数）。

## 🎯 功能总览

### 2D 动态几何

- **对象**：点 / 线段 / 射线 / 直线 / 圆 / 圆弧 / 扇形 / 多边形 / 刚性多边形 / 折线 / 向量 / 轨迹 / 文本。
- **构造**：中点、垂线/垂足、平行线、中垂线、角平分线、切线、外接圆、内心/内切圆、垂心/外心/旁心、正多边形、圆上点/路径动点。
- **圆锥曲线**：椭圆 / 双曲线 / 抛物线 / 五点圆锥曲线；焦点/准线、曲线求交；退化情形退回 marching squares。
- **变换**：平移 / 旋转 / 镜像 / 位似 / 反演。反演支持点、线、圆、圆弧、扇形、多边形、折线、向量、圆锥曲线、函数、参数/极坐标曲线、轨迹、隐式曲线等；线段/射线/圆弧/向量/参数/极坐标/椭圆直接复合映射为参数方程，曲线光滑。
- **度量**：距离 / 长度 / 斜率 / 角度（度与 π 分数弧度）/ 面积 / 周长 / 半径 / 直径 / 半周长。
  - `Length`（别名「弧长」）：线段 / 向量 / 折线 / 圆弧 / 扇形（只取弧长）/ 圆 / 椭圆 / 列表（元素个数）。
  - `Area`：多边形 / 圆 / 椭圆 / 扇形（½r²θ）/ 3D 立体 / 函数 + 上下限。
  - `Perimeter`：只对**封闭**图形有意义 —— 多边形（含刚性）/ 圆 / 椭圆 / 扇形（弧长 + 两半径）/ 3D 截面；圆弧/折线/线段是开放曲线，明确报错并指向 `Length`；双曲线/抛物线无有限周长，明确报错；椭圆用 Ramanujan 近似（圆精确 2πr）。中文命令/别名同样可嵌套（如 `面积[扇形[A,B,O]]`）。
- **概率**：随机整数 / 随机点（圆内、多边形内）、排列组合、点积、相关系数 PMCC。
- **刚性多边形**：拖首点平移、拖第二点绕首点旋转，边长恒定。
- **二维剖分**：`Delaunay[…]`（scipy Qhull）与 `Voronoi[…]`（半平面裁剪，元胞均为有界凸多边形）；返回多边形列表，带面积与质心。

### 代数 / 函数 / 表达式

- 自由点 `A=(1,2)`、数值 `r=3`、函数 `f(x)=x^2+2x`（SymPy 解析，可互相引用并自动重编译）。
- **裸语法输入**（Desmos 风格）：`x^2+y^2=1`、`(cos(t),sin(t))`、`r=2cos(θ)`、`y~a*x+b`、`L=[1,2,3]`。
- `Derivative` / `Integral`（定/不定）、`Root` / `Extremum` / `Intersect`（函数求交）、`If` 分段、动态文本、未定义变量自动生成滑块。
- 列表与统计：`Sum/Mean/Median/Mode/Variance/StDev/Sort`、`Sequence`、`Iteration/IterationList`、`FitLine/FitPoly/FitExp/FitLog/FitPow/FitSin`、`NormalDist`、`StemPlot`。
- **表达式依赖化**：`A=(s,0)`、`Segment[(0,0),(s,2)]` 等引用已有元素的写法自动成为**受控对象**（声明依赖、随滑块重算、不可直接拖动，`.ggk` 重放仍跟随）；纯常量仍是自由可拖对象。
- **CAS 算子接线为构造命令**（可参与 DAG、命名、引用、随依赖重算）：`Solve` / `NSolve` / `Limit` / `PartialFractions` / `Substitute` / `SolveODE` / `IsFinite` / `SurfaceArea`；中文别名 求解方程 / 数值解 / 极限 / 部分分式 / 代入 / 微分方程 / 是否有限 / 表面积。

### 画布工具与交互

- **分类工具栏**（点 / 线 / 圆 / 多边形 / 圆锥曲线 / 变换 / 度量 / 计算 / 统计图 / 控件 / 3D，共 **11 个分类**，30+ 工具、79 个按钮）：动态虚线预览、拉框多选、对象拾取、选中整体拖动；工具选中后再点一次取消。
- **网格吸附**：视图菜单开关；关闭时 2D 按住 **Shift** 临时吸附，3D 按住 **Ctrl**（3D 的 Shift 已绑定「只改高度」）；拖动已有点同样吸附；落点优先复用已有点。
- **视图**：放大 / 缩小（×1.3，以画布中心为锚）/ 复位；滚轮缩放独立。
- **全局快捷键**：统一 `Ctrl+Shift+<键>`（macOS `Cmd+Shift+<键>`），只绑定切换类动作：

  | 快捷键 | 动作 |
  |---|---|
  | `Ctrl+Shift+G` | 网格显示 / 隐藏 |
  | `Ctrl+Shift+X` | 坐标轴显示 / 隐藏 |
  | `Ctrl+Shift+S` | 格点吸附开关 |

- **滑块**：`Slider[最小, 最大, 步长?, (x,y)?, vertical?, px?]`，轨道 + 滑钮；拖滑钮改值（按步长），拖轨道整体移动；▶/⏸ 与顶栏「全部播放/暂停/动画设置」；`SetSlider` 就地改范围，`SetSliderVertical`、`SetSliderLength` 调竖直与像素长度；定义与当前值分离（当前值进 `.ggk` 的 `values`）。
- **交互控件**：`Button` / `CheckBox` / `InputBox`，无自身状态，勾选/文本由绑定对象派生；控件与列表定义式均可双击就地编辑。
- **命令栏**：下拉补全带完整签名；模板态 Tab / Shift+Tab 循环跳参，Enter 顺序跳参到末参提交；所见即所得 LaTeX 预览、虚拟数学键盘。
- **示例图形**：`share/figures/` 内置小猫 / 小屋与花园 / 自行车 / 3D 小屋与庭院，可在 **文件 → 示例** 打开，或用 `python3 devtools/make_figures.py` 重建（每幅同时产出 .svg / .ggk / .png）。

### CAS 符号计算（右侧面板）

- 11 个命令按钮插入模板，`#N` 可引用前序单元；`a:=5` 建数值、`f(x):=x^2` 建函数并联动绘图区。
- 命令：`Expand` `Factor` `Simplify` `Solve` `NSolve` `Limit` `Derivative` `Integral` `SolveODE` `PartialFractions` `Substitute`。

### 统计与概率

- 统计图 8 类：`BarChart` / `Histogram` / `BoxPlot` / `PieChart` / `LineChart` / `ScatterPlot` / `DotPlot` / `StemPlot`；每张图是可整体拖动的对象（世界坐标 offset，随 `.ggk` 保存）；黎曼和条带（左/右/中/下/上/梯形）。

### 3D 视图

- 三维点/线段/直线/平面/球/圆锥/圆柱/棱柱/棱锥 + **五种正多面体**（正方体/正四面体/正八面体/正二十面体/正十二面体，黄金比构造）；2D 图形按 z=0 同场显示。
- `Cube` 支持 `Cube[A,B]` / `Cube[A,B,C]` / `Cube[线段]` / `Cube[线段, 点]` / `Cube[正方形多边形]`；`Cone` 与 `Cylinder` 同样支持多种输入（底面圆 + 高度 / 顶点 + 底心 + 半径 / 轴向量 + 半顶角等）。
- 曲面三类：显式 `Surface`、参数 `SurfaceParam`、隐式 `ImplicitSurface`（marching tetrahedra）。
- 操作：斜二测/俯/前/右正交视图；右键旋转、滚轮缩放、空白拖动平移；点击 3D 对象直接拖动（Shift+拖动只改高度），z 轴控制柄改高度。
- 控制点：自由点红色菱形、派生点蓝色圆点，选中橙色虚线光环；正多面体中心点拖动=平移、半径点=缩放、方向点=旋转朝向；**立体工具建完自动退出**。
- 渲染：画家算法、hidden-line 虚线、逐对象线框/实体、坐标轴刻度。
- 度量与变换：`Translate` 的 z 分量参与；`Rotate[三维点,…]` 绕平行 z 轴旋转；`Distance`/`Angle` 用真三维量；`Volume`/`Area`（球/锥/柱解析，多面体网格积分）。
- 求交：面×面、直线/线段×面、平面×立体（截面）、球×平面/球×球/球×空间圆、空间圆相关、立体×立体（凸交）、立体/球×直线（第 3 参数取第 n 个）。
- 3D 测量工具：体积 / 表面积，点立体即在状态栏给出结果；`/api/state3d` 为每个对象附带可读 `solid` 字段。

### 定理证明 / 脚本 / 导出 / 协作

- `AreParallel` / `ArePerpendicular` / `AreCollinear` / `AreConcyclic` / `AreCongruent` / `AreConcurrent` + `Prove`（Botana 坐标法 + SymPy 符号归约；区分恒假与退化敏感）。
- 脚本：`SetCoords` / `SetValue` / `SetColor` / `SetVisible` / `SetLocked` / `SetWire` / `Rename` / `Redefine` / `Delete` / `SetCaption` / `SetScript`；自定义宏（GUI 点选输入/输出）、命令脚本面板（`.ggs`）。
- 保存/加载：自有 `.ggk`（JSON，含视口/样式/宏/滑块值/网格），兼容 `.ggb` XML 导入导出。
- 导出：SVG / PNG / OBJ / STL / glTF；SVG 2D 覆盖全部 28 种可绘制元素（含统计图 7 类与控件 3 类，`Image` 以 data URI 内嵌），3D 用 `?view3d=1&yaw=&pitch=` 指定机位；多边形填充跟随元素颜色。
- 导入：OBJ / STL / glTF / GLB 网格、图片（选图片 → 点两个基点放置，拖第二基点缩放保持长宽比）；一键生成试卷 HTML、短链接分享。

### 界面与多语言

- 中 / EN 一键切换（zh / en 各 **228 条**，键集合由检测锁定防漏翻）、明暗主题、移动端响应式 + 双指缩放、Retina 高清渲染。
- 对象列表行内编辑、命令栏 LaTeX 预览、虚拟数学键盘（含 π、e）。

#### ⚠️ 限制与边界（由检测矩阵锁定当前行为）

#### 2D 限制

- **撤销/重做**：撤销栈上限 `UNDO_LIMIT = 200`（超出丢弃最早快照）；重做走计算记忆。
- **计算记忆**：按「定义式 + 依赖几何状态签名」缓存，≤ 96 条 / 约 60 万坐标；随机类命令不参与；compute 闭包必须返回完整 state。
- **嵌套命令**：参数里的 `Cmd[...]` 最多 **4 层**（超出明确报错）；嵌套的匿名辅助元素不进对象列表/撤销/序列化。
- **符号求解边界**：`Root` / `Extremum` 需有效区间；`Solve` 只返回实数解（复数解给文本、无解给空列表）；`SolveIneq` / `Implicit` 输入不合法给明确错误。
- **角度语义**：`Angle[A,B,C]` 为从 BA 逆时针到 BC 的有向角，范围 [0°,360°)；弧的圆心角即该角；三维点用真三维夹角（0..180°）。
- **统计图边界**：柱高 `CHART_H = 3`、饼半径 `PIE_R = 3`（世界单位），基线取世界 y=0；饼图须非负且总和为正，直方图须非空且数据有变化，折线图 x/y 须等长非空；`StemPlot` 只接受非负有限数据（叶单位 1）。
- **列表字面量**：含元素引用时声明依赖并随依赖重算；支持点标签 `{A,B}` 与三维点；点标签与坐标混用、2D/3D 混用明确报错。
- **剖分边界**：`Delaunay` 至少 3 点，共线/重合报「点集退化」；`Voronoi` 至少 2 点，外扩 15% 包围盒裁剪（元胞有界，面积和 = 包围盒面积）。
- **周长/长度/面积**：`Perimeter` 只对封闭图形（多边形/圆/椭圆/扇形/3D 截面），开放曲线报错指向 `Length`；`Length` 对扇形只取弧长，多边形请用 `Perimeter`；`Area` 对圆弧报错并提示用 `Sector`；3D 立体用 `Volume`/`SurfaceArea`。
- **工具入口**：工具面板 **11 个分类**；统计图分类含 11 个按钮（2D 八类 + 3D 三类）。
- **多语言词条**：zh / en 各 **228 条**，键集合完全一致（检测锁定，防漏翻）；主题 light/dark 记忆在 localStorage。
- **`.ggk` / `.ggb`**：`.ggk` 为 JSON；`.ggb` 按命令重放，网格与图片数据内嵌 `<ggbpyData>`（base64+JSON），缺数据时跳过并给 `X-GGB-Warnings`。
- **SVG 导出的图片**：`Image` 以 data URI 内嵌（文件自包含）；仓库缺记录时画灰色虚线占位框；元素类型覆盖由检测白名单锁定。
- **有意为之的边界**：`Implicit` 需含 x、y 的方程；立体相关的体积/截面积等运算属 3D。

#### 3D 限制

- **求交边界**：支持面×面、线×面、平面×立体（截面）、球×平面/球×球/球×空间圆、空间圆相关、立体×立体（凸交）、立体/球×线；**球面×曲面、体×空间圆（作为曲线输出）尚未支持**，明确报错；平行/重合平面、超出线段的交点、相切球面/球过立体顶点会产出带 `error` 的元素。
- **曲面精度**：`ImplicitSurface` 为 marching tetrahedra 线性插值（粗网格面积误差约 0.1%–8%）；曲面网格可用于显示/面积/导出，`Volume` 无定义（明确报错）。
- **网格导入**：OBJ/STL 只保留几何（顶点去重、面索引重排），忽略材质/UV/法向/颜色；非闭合网格可显示/导出，但 `Volume` 无物理意义。
- **`.ggb` / SVG**：3D 点带真实 z（`w="1"`），派生对象按命令重放，网格与图片内嵌往返；SVG 默认 2D，`?view3d=1` 输出 3D 正交投影（画家算法，超 4000 面按面积取前 N 面）。
- **重计算让出**：隐式曲面 marching 循环内每 ~5 ms 协作让出（`GGBPY_YIELD_MS`，0=关闭），避免其它会话轻请求长时间排队；压测见 `devtools/bench_blocking.py`。

## 🧪 检测与质量

```bash
bash devtools/run_all_detection.sh      # 全量 11 步（提交前门禁；服务在 8090）
bash devtools/run_all_detection.sh http://127.0.0.1:8091   # 非默认端口：依赖服务的步骤透传该 BASE
bash devtools/run_scope.sh quick        # 迭代用：按改动层跑最小范围
```

### 全量检测（11 步 / 1927 断言）

| 步骤 | 脚本 | 断言 | 覆盖 |
|---|---|---|---|
| 1 命令注册表一致性 | `test_registry.py` | 17 | 注册表/别名/显示名/结果类型/参数签名表 |
| 2 内容寻址仓库 | `test_stores.py` | 18 | 图片/网格仓库 |
| 3 统一容差 | `test_tolerance.py` | 20 | 零魔数扫描、前后端常量一致、防漏导入 |
| 4 模块边界 | `test_modules.py` | 336 | 内核拆分、薄包装、前端作用域/文案外置/词条一致 |
| 5 多会话隔离 | `test_sessions.py` | 24 | `?sid=`/cookie、构造/宏/state3d 独立性、TTL |
| 6 2D 内核 | `test_2d_matrix.py` | 313 | 对象/命令/圆锥曲线/统计图/命名/`.ggk` 往返/计算记忆 |
| 7 2D 平台 API | `test_2d_api.py` | 121 | `/api/*`（state/input/drag/load/download/share/cas/image/export…） |
| 8 3D 三层 | `run_3d_detection.sh` | 504 / 183 / 159 | 3D 内核 / 3D API / 3D 浏览器 |
| 9 2D 前端回归 | `verify_2d_ui_matrix.js` | 204 | 编辑栏/CAS/工具/滑块/吸附/快捷键/指针捕获 |
| 10 微积分·求根 smoke | `test_mixed_smoke.py` | — | 2D↔3D 混合冒烟 |
| 11 代码质量策略 | `test_quality.py` | 28 | 宽泛捕获说明/预算、文档结构、CHANGELOG 批次完整性 |

### 分范围检测（迭代用）

| scope | 覆盖 | 实测 |
|---|---|---|
| `docs` | 代码质量 / 文档与 CHANGELOG 结构守卫 | 0.3s |
| `registry` | 命令注册表 + 参数签名表 | 0.2s |
| `kernel2d` | 2D 内核矩阵 | 1.7s |
| `api2d` | 2D / 平台 API 矩阵 | 0.4s |
| `core` | 容差 + 模块边界 + 多会话隔离 | 1.6s |
| `content2d` | 内容寻址仓库 + 微积分 smoke | 0.2s |
| `kernel3d` / `api3d` | 3D 内核 / 3D API | 6.7s / 7.4s |
| `ui2d` / `ui3d` | 模块边界 + 浏览器矩阵 | ~100s / ~210s |
| `quick` | registry + kernel2d + core + docs | ~4s |
| `all` | 全量 11 步 | ~4–5 分钟 |

**策略**：迭代中按上表选最小范围；**提交前**纯文档改动跑 `docs`，**任何代码改动跑 `all`** 并看到「全部检测通过」。

### 开发纪律守卫

- `test_quality.py` F 段：CHANGELOG 批次条目结构（编号唯一 / 最新批次段连续 / 段长与总数不减少 / 条目够长），防止整条被替换/删除。
- `devtools/doc_add_batch.py`：追加 CHANGELOG 批次条目的**唯一入口**（锚点行前插入 → 自检 → 结构守卫 → 不过自动回滚）。
- `devtools/_probe_lib.js`（+ 自检）：浏览器探针夹具库（页面级清空 / 幂等选工具 / 按 alpha 量像素 / 世界→像素换算）。
- 性能压测：`bench_blocking.py`（跨会话阻塞）、`bench_undo.py`（撤销/重做与快照成本）。

## 🧱 架构

```text
ggbpy/
├── kernel/                平台无关内核（纯 Python，无 Web 依赖）
│   ├── elements.py        对象模型（GeoElement 家族 + 依赖/计算闭包）
│   ├── construction.py    Construction：注册表、DAG、增量重算、撤销/重做、序列化
│   ├── parser.py          代数输入解析（标签 / 元组 / 命令 / 数学表达式）
│   ├── registry.py        命令规格单一来源（COMMANDS / ALIASES / 显示名 / 结果类型）
│   ├── commands*.py       命令实现（2D / 3D / CAS / 统计 / 拟合 / 剖分…）
│   ├── tolerance.py       分级数值容差（零魔数）
│   ├── memo.py            计算记忆（撤销/重放加速）
│   ├── cas.py / prover.py SymPy CAS 引擎 / 定理证明器（Botana 坐标法）
│   └── ggb_io.py / svg_io.py    GGB XML / SVG 导出导入
├── server/
│   ├── main.py            FastAPI 服务（输入、拖拽重算、存取、分享、导出）
│   └── static/            前端（零构建）：index.html / app.js / style.css / i18n.js / data.js
├── devtools/              检测矩阵与工具（run_all_detection.sh / run_scope.sh / make_figures.py …）
├── share/figures/         示例图形（.svg / .ggk / .png）
├── run.sh                 一键启动（PORT 环境变量可改）
└── requirements.txt       Python 依赖
```

核心设计（沿用 GeoGebra 思想）：**对象挂在依赖图上 → 拖动自由点沿拓扑序增量重算**。每个对象由 `(deps, compute_fn)` 闭包描述，重算只影响受影响子树；编辑（重定义/重命名/改色）沿依赖链传播并保留样式，全部操作可撤销/重做（快照式）。

## 📖 命令示例

```text
A=(1,1)  B=(5,2)  C=(3,6)
M=Midpoint[A,C]
g=Line[A,B]
c=Circle[A,B]
poly=Polygon[A,B,C]
f(x)=x^2-2*x+1
df=Derivative[f]
area=Integral[f,0,4]
E=Ellipse[A,B,C]                                # 焦点 + 过点
c5=Conic[(0,0),(1,1),(2,0),(1,-1),(0.4,0.6)]    # 五点圆锥曲线
s=Slider[0,10,1,(-3,-4)]  f2(x)=s*x             # 滑块驱动函数
D=Delaunay[{A,B,C,(4,5),(7,2)}]                 # 三角剖分
Prove[AreParallel[g, Line[M,C]]]
```

中文别名（`中点` / `刚性多边形` / `外接圆` / `随机点` / `三角剖分` …）与全部 190 条命令、237 个别名见 **`?` 帮助面板**或 `GET /api/commands`。

## 📦 发布到 Gitee

```bash
git remote add origin https://gitee.com/<用户名>/ggbpy.git   # 或 git@gitee.com:<用户名>/ggbpy.git
git push -u origin main
```

完整步骤（新建空仓库、SSH 免密、常见问题）见 [`GITEE_UPLOAD.md`](GITEE_UPLOAD.md)。

## 📜 变更历史

本项目按「批」开发，功能、修复与各批检测数字都记录在 **[CHANGELOG.md](CHANGELOG.md)**；本 README 只描述当前状态，不重复历史。

## 📄 许可与致谢

- 本仓库代码为**原创**实现（BSD-3-Clause）。
- 设计交互思想参考 GeoGebra（EUPL 1.2，仅限非商用）；**不包含** GeoGebra 任何源码。
- 符号计算：SymPy（BSD）；Web 服务：FastAPI；数学渲染：KaTeX（MIT）。
