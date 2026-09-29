# ggbpy · Python 动态几何教学软件

> 用 Python 从头实现的「动态几何 + 代数 + CAS + 3D + 定理证明」一体化教学平台
> （GeoGebra 启发的交互理念，代码完全原创，BSD-3-Clause）。

![界面预览](toolsicon/ggbpy-gui.png)

## ✨ 项目简介

ggbpy 是一个**浏览器端使用、Python 后端驱动的动态几何软件**：几何对象以**依赖图（DAG）**组织，拖动自由点即沿图拓扑序**增量重算**全部派生对象，符号计算底座为 **SymPy**。前端为原生 HTML5 Canvas（零框架），支持中英双语、明暗主题与移动端触控。

数学内核与 Web 服务分离（平台无关的 Python 包 + FastAPI），既可作为教学演示工具，也可作为"Python 动态几何"的参考实现来阅读与扩展。

## 🚀 快速开始

```bash
cd ggbpy
pip install -r requirements.txt      # fastapi / uvicorn / sympy / numpy
./run.sh                              # 默认端口 8090；可 PORT=8091 ./run.sh
```

浏览器打开 <http://127.0.0.1:8090> 即可使用。

> 也可以不用脚本：`python3 server/main.py --port 8090`

## 🎯 功能总览

### 动态几何（对象 + 命令 + 画布工具）

- **对象**：点 / 线段 / 射线 / 直线 / 圆 / 圆弧 / 扇形 / 多边形 / 刚性多边形 / 折线 / 向量 / 轨迹 / 文本
- **构造**：中点、垂线/垂足、平行线、中垂线、角平分线、切线（直线/圆/曲线/圆弧）、外接圆、内心/内切圆、垂心/外心/旁心、正多边形、圆上点/路径动点
- **圆锥曲线**：椭圆 / 双曲线 / 抛物线 / **五点圆锥曲线**（动态预览，圆/椭圆/双曲线自动参数化绘制，退化情形自动退回 marching squares）、焦点/准线、曲线求交
- **变换**：平移 / 旋转 / 镜像 / 位似 / **反演（圆反演）**（支持点、线、圆、线段、射线、圆弧、扇形、多边形、折线、向量、圆锥曲线、函数、参数/极坐标曲线、轨迹、隐式曲线等全部类型；其中线段/射线/圆弧/向量/参数/极坐标/椭圆**直接复合反演映射为参数方程**，曲线光滑）
- **度量**：距离 / 长度 / 斜率 / 角度（° 与弧度 π 分数）/ 面积 / 周长 / 半径 / 直径 / 半周长
- **概率**：随机整数/随机点（圆内、多边形内）、排列组合、点积、相关系数 PMCC
- **画布工具**：分类工具栏（点/线/圆/多边形/圆锥曲线/变换/测量/计算/滑块/视图）30+ 工具，支持动态虚线预览、网格智能吸附、拉框多选、对象点击拾取、选中对象整体拖动（OOP 联动）
- **刚性多边形**：两手柄语义——拖首点平移、拖第二点绕首点旋转，边长恒定

### 代数 / 函数 / 可视化

- 自由点 `A=(1,2)`、数值 `r=3`、函数 `f(x)=x^2+2x`（SymPy 解析，可互相引用并自动重编译）
- `Derivative` / `Integral`（定/不定积分、原函数）、`Root` / `Extremum` / `Intersect`（函数求交）
- **裸语法输入**（Desmos 风格）：`x^2+y^2=1` 隐式方程、`(cos(t),sin(t))` 参数曲线、`r=2cos(θ)` 极坐标、`y~a*x+b` 回归拟合、`L=[1,2,3]` 列表
- **If 分段函数**、动态文本拼接、未定义变量自动生成滑块、滑块 ▶ 播放动画
- 列表运算：`Sum/Mean/Median/Mode/Variance/StDev/Sort`、`Sequence`、`Iteration/IterationList`

### CAS 符号计算（右侧面板）
- CAS 面板内置**命令面板**（11 个命令按钮，点击插入模板、光标自动停在括号内）；`#N` 可点击引用前序单元；`a:=5` 创建数值、`f(x):=x^2` 创建函数（结果可 `:=` 联动到绘图区）；命令：`Expand` `Factor` `Simplify` `Solve` `NSolve` `Limit` `Derivative` `Integral` `SolveODE` `PartialFractions` `Substitute`；帮助面板 `?` 中也有入口

### 统计 / 概率

- 直方图 / 分组直方图 / 饼图 / 箱线图（五数概括）/ 黎曼和条带（左/右/中/下/上/梯形）
- 正态分布密度 `NormalDist`、`FitLine/FitPoly/FitExp/FitLog/FitPow/FitSin`、散点列表

### 3D 视图

- 三维点/线段/直线/平面/球/圆锥/圆柱/棱柱/棱锥 + **五种正多面体**（正方体/正四面体/正八面体/正二十面体/正十二面体，黄金比构造）；2D 图形按 z=0 同场显示
- **`Cube` 多种输入**：`Cube[A,B]`（两点）、`Cube[A,B,C]`（三点定底面）、`Cube[线段]`（以线段为棱，方向缺省时系统自选）、`Cube[线段, 点]`（该点定相邻棱方向）、`Cube[正方形多边形]`（以正方形为底面），均为 8 顶点/6 面/12 棱等长；**3D「立方体」工具按钮**同样支持：直接点线段/正方形即生成，或点两个空间点自动生成
- **`Cone` 多种输入**：`Cone[圆, 高度]`（圆为底面，顶点在圆心正上方，高度可为滑块/数值）、`Cone[顶点, 底面圆心, 半径]`（轴可任意方向）、`Cone[顶点, 轴向量, 半顶角(度)]`（无限双圆锥，半顶角∈(0°,90°)）、以及经典 `Cone[A,B,C]`（A=底面圆心、B=半径点、C=顶点，底面垂直于 AC）；**3D「圆锥」工具按钮**支持：点圆/圆弧→输入高度，或点顶点→底面圆心→输入半径（对话框取消则改为再点一个底面半径点），或依次点顶点、底面圆心、半径点
- **`Cylinder` 多种输入**：`Cylinder[圆, 高度]`（圆为底面，沿圆法向抬升，高度可为滑块/数值）、`Cylinder[底面圆心, 顶面圆心, 半径]`（轴可任意方向），以及经典 `Cylinder[A,B,C]`（A=底面圆心、B=底面半径点、C=顶面圆心）；**3D「圆柱」工具按钮**支持：点圆→输入高度，或点底面圆心→顶面圆心→输入半径（对话框取消则改为再点一个底面半径点），或依次点底心、顶心、半径点
- 斜二测画法（默认，可自由旋转）/ 俯 / 前 / 右正交视图；右键旋转、Shift+拖动改 z、z 轴控制柄
- **3D 对象平移**：点击选中 3D 对象后直接在画布上拖动即可平移（普通=水平面内，Shift+拖动=仅改高度），空白处拖动仍旋转视角
- **3D 控制点提示**：自由点渲染为**红色菱形**（可拖动的控制点，拖动即可改变其驱动的立方体/多面体大小），派生点为蓝色圆点；选中的点变为**橙色**并加粗、带虚线光环，状态栏提示「已选中控制点 — 拖动可改变立体大小」
- 画家算法排序、hidden-line 遮挡虚线、逐对象线框/实体切换、坐标轴刻度

### 定理证明器 / 脚本 / 导出 / 协作

- `AreParallel/ArePerpendicular/AreCollinear/AreConcyclic/AreCongruent/AreConcurrent` + `Prove`（Botana 坐标法 + SymPy 符号归约；区分「恒假（存在反例）」与「退化敏感」）
- `SetCoords/SetValue/SetColor/SetVisible/SetLocked/SetWire/Rename/Delete` 等脚本命令
- 自定义宏（Macro，GUI 点选输入/输出）、命令脚本面板（.ggs 批量执行）
- **保存/加载**：自有 .ggk（JSON，含视口/样式/宏），兼容 .ggb XML 导入导出、SVG/PNG 导出
- **插入图片**：工具栏 🖼 选择图片 → 点击两个基点放置；拖动第二基点缩放，**保持原始长宽比**（图片随 .ggk 保存/加载）
- 一键生成**试卷 HTML**（题目截图 + 题干/答案编辑，A4 打印即 PDF）；**短链接分享**

### 界面

- 中 / EN 一键切换、明暗主题、移动端响应式 + 双指缩放、Retina 高清渲染
- 命令输入**所见即所得 LaTeX 预览**（KaTeX 本地托管）、虚拟数学键盘（含 π、e）、对象列表行内编辑

## 🧱 架构

```
ggbpy/
├── kernel/                平台无关内核（纯 Python，无 Web 依赖）
│   ├── elements.py        对象模型（GeoElement 家族 + 依赖/计算闭包）
│   ├── construction.py    Construction：注册表、DAG、增量重算、撤销/重做、序列化
│   ├── parser.py          代数输入解析（标签 / 元组 / 命令 / 数学表达式）
│   ├── commands.py        命令注册表 + 几何算法（求交 / 变换 / 圆锥曲线…）
│   ├── geom_util.py       通用几何算法（五点圆锥曲线 / marching squares / 规范化）
│   ├── cas.py             SymPy CAS 引擎
│   ├── prover.py          定理证明器（Botana 坐标法）
│   ├── ggb_io.py / svg_io.py    GGB XML / SVG 导出导入
│   └── macro.py           自定义宏
├── server/
│   ├── main.py            FastAPI 服务（输入、拖拽重算、存取、分享）
│   └── static/            HTML5 Canvas 前端（app.js / index.html / style.css / toolsicon/ / vendor/katex/）
├── run.sh                 一键启动（PORT 环境变量可改）
├── requirements.txt       Python 依赖
└── toolsicon/             README 等使用到的图标素材
```

核心设计（沿用 GeoGebra 思想）：**对象挂在依赖图上 → 拖动自由点沿拓扑序增量重算**。每个对象由 `(deps, compute_fn)` 闭包描述，重算只影响受影响子树；编辑（重定义/重命名/改色）自动沿依赖链传播并保留样式，全部操作可撤销/重做（快照式）。

## 📖 使用示例

```
A=(1,1)  B=(5,2)  C=(3,6)
M=Midpoint[A,C]
g=Line[A,B]
c=Circle[A,B]
poly=Polygon[A,B,C]
f(x)=x^2-2*x+1
df=Derivative[f]
area=Integral[f,0,4]
t=Tangent[f,2]
E=Ellipse[A,B,C]                # 焦点+过点
c5=Conic[(0,0),(1,1),(2,0),(1,-1),(0.4,0.6)]   # 五点圆锥曲线
k1=Cone[Circle[(0,0),2], 3]           # 底面圆 + 高度
k2=Cone[(0,0,5),(0,0,0),2]           # 顶点 + 底面圆心 + 半径
k3=Cone[(0,0,0),(0,0,1),30]          # 顶点 + 轴向量 + 半顶角(度)
y1=Cylinder[Circle[(0,0),2], 4]        # 底面圆 + 高度
y2=Cylinder[(0,0,0),(0,0,5),2]        # 底心 + 顶心 + 半径
Prove[AreParallel[g, Line[M,C]]]
```

更多命令与中文别名（如 `中点` / `刚性多边形` / `外接圆` / `随机点`）见 CHANGELOG.md。

## 📦 发布到 Gitee（如何上传本仓库）

本目录已就绪：

- ✅ `README.md`（本文件）、`CHANGELOG.md`（开发记录）
- ✅ `.gitignore` —— 已排除 `__pycache__`、开发期截图/日志/检测脚本（`*.log`、`audit*`、`verify*`、`diag*`、`screenshot_*`、`shot_*`）等不应发布的文件

### 第 1 步：在 Gitee 新建仓库

1. 登录 [gitee.com](https://gitee.com) → 右上角 **+** → **新建仓库**；
2. 填写仓库名（如 `ggbpy`）与简介；
3. **不要勾选**「初始化仓库」下的 README / .gitignore / 许可证（保持完全空仓库，避免推送冲突）；
4. 点 **创建**。复制仓库地址（HTTPS 形如 `https://gitee.com/<用户名>/ggbpy.git`；也可切到 SSH 形如 `git@gitee.com:<用户名>/ggbpy.git`）。

### 第 2 步：本地初始化并提交（在 ggbpy 目录内）

```bash
cd ggbpy
git init -b main
git add .
git status          # 核对将要上传的文件（被 .gitignore 忽略的不会出现）
git commit -m "feat: ggbpy 动态几何教学平台首个版本"
```

首次使用 git 若提示身份缺失，先设置：

```bash
git config --global user.name  "你的昵称"
git config --global user.email "你的邮箱"
```

### 第 3 步：关联远程仓库并推送

HTTPS 方式：

```bash
git remote add origin https://gitee.com/<用户名>/ggbpy.git
git push -u origin main
```

SSH 方式（需先在 Gitee「设置 → SSH 公钥」中添加 `~/.ssh/id_ed25519.pub`，见第 4 步）：

```bash
git remote add origin git@gitee.com:<用户名>/ggbpy.git
git push -u origin main
```

刷新 Gitee 仓库页面即可看到全部源码。**此后每次改动的常规流程**：

```bash
git add .
git commit -m "说明本次改动"
git push
```

### 第 4 步（可选但推荐）：SSH 免密

```bash
ssh-keygen -t ed25519 -C "你的邮箱"     # 一路回车
cat ~/.ssh/id_ed25519.pub               # 复制输出
```

到 Gitee「设置 → SSH 公钥」粘贴保存，之后推送无需反复输密码。

### 常见问题

| 现象 | 处理 |
|---|---|
| 推送被拒 `non-fast-forward` | 仓库非空或有远端提交：`git pull --rebase origin main` 后再 `git push` |
| 提示认证失败 / 403 | HTTPS 用 Gitee 账号密码或**私人令牌**（设置 → 私人令牌）；确认用户名拼写 |
| 想上传的文件被忽略 | 检查是否命中 `.gitignore`；确实要传则 `git add -f <文件>` |
| 修改 .gitignore 后仍被跟踪 | 已跟踪文件需 `git rm -r --cached <路径>` 再提交 |
| 想删除远程误传文件 | `git rm -r --cached <路径>` → commit → push（本地文件保留） |

> 详细图文教程、多账号、已有远程仓库、Windows 换行符等进阶情况见 **`GITEE_UPLOAD.md`**。

## 📜 许可与致谢

- 本仓库代码为**原创**实现（BSD-3-Clause）。
- 设计交互思想参考 GeoGebra（EUPL 1.2，仅限非商用）；**不包含** GeoGebra 任何源码。
- 符号计算：SymPy（BSD）；Web 服务：FastAPI；数学渲染：KaTeX（MIT）。
