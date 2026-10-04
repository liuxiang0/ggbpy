# ggbpy 十二批开发总回顾（2026-09-29）

> 基于仓库实测数据（代码行数、命令/端点覆盖脚本、性能计时、内存/载荷测量），不是叙述性总结。
> 回顾范围：`4b02a58`（LICENSE）→ `45985bd`（第十二批），共 13 个提交，全部已推送 Gitee。

## 0. 闭环状态（2026-10-04 复核）

> 本回顾的每一条都在 2026-10-04 复核过：能修的已修且有回归锁定，能测的已测（数字见下），
> 有两项**经测量判定不需要做**（原始建议本身不是瓶颈）。原始文本保留在 §4–§7 作为历史记录。
> 复核入口见本节末尾。当前全量检测：**11 步 / 1514 断言**。

### §4 架构债逐条

| 条目 | 状态 | 证据 |
|---|---|---|
| P0-1 服务端单一全局 Construction | ✅ 已解决 | `server/sessions.py`（`?sid=` > cookie > `default`；上限 24 / TTL 6h）+ `test_sessions.py` 23 断言 + 前端 cookie 持久 4 断言 |
| P0-2 重计算同步阻塞全局 | ✅ 已量化并缓解 | `bench_blocking.py`：阻塞是**间歇性**的（numpy 段释放 GIL，探测 0 失败）；marching 每 ~5 ms 协作让出（`GGBPY_YIELD_MS`）→ 跨会话 p50 27.1→**21.7 ms**、max 42.4→**31.9 ms**，重算耗时 +0.9% |
| P0-3 撤销/重做＝全构造重放 | ✅ 已量化 + 文档化 | `bench_undo.py`：快照 **58 B/对象**、满栈 200 → **2.2 MB**、单步 ~3 ms；`memo` 命中时 restore **2 ms**；唯一有界代价＝记忆清空后首次回放重元素（n=32 → 1395 ms）。差量快照**判定不需要**（见下） |
| P1-5 渲染 O(边×面) 遮挡 / 无投影缓存 | ✅ 缓存已做，换算法不需要 | 投影复用（浏览器断言 reuse>1000）+ 遮挡预算兜底；面心排序/空间哈希见「判定不需要」 |
| P1-6 命令注册四张表手工同步 | ✅ 已解决 | `kernel/registry.py`：`SPECS` 单一来源派生四张表（378 → **265** 行），新增命令只改一处；顺带清掉 5 个孤儿显示名 |
| P1-7 `data` 约定散落无 schema | ✅ 已解决 | `kernel/schemas.py` 11 个 builder + 「kernel 内禁止内联 `objtype`」守卫 |
| P1-8 两个同构仓库模块 | ✅ 已解决 | `image_store` / `mesh_store` 均已委托通用 `blob_store`（内容寻址 + serialize/load） |
| P1-9 前端单文件 5,596 行 | ✅ 已解决 | `app.js` 5979 → **2768**（21 个 `static/*.js`；薄包装保持调用点零改动） |
| P1-10 边表重复 + `except Exception` | ✅ 已解决 | 边表统一 `mesh_store.edges_of` + 守卫；宽泛捕获 68 处**全部带说明**、5 处收窄（→63）+ 策略守卫（禁裸 except / 预算 / 变异自检） |
| P1-11 内核单文件 7,671 行 | ✅ 已解决 | `commands.py` 7867 → **1155**（43 个内核模块；注册表集中于 `registry.py`） |
| P2-12 SVG 仅 2D / `.ggb` 不内嵌网格 | ✅ 已解决 | `/api/export/svg?view3d=1`（正交投影，>4000 面按面积取前 N）；`.ggb` 内嵌 `<ggbpyData>`（base64+JSON），往返断言：网格 8 顶点/6 面、体积 8、图片可再取 |
| P2-13 2D 侧无限制/边界文档 | ✅ 已解决 | README「2D 限制」10 条 + 「2D 检测矩阵」+ 文档守卫（条目 ≥8、锚定关键上限） |

### §6 建议项（A–J）

| 建议 | 状态 |
|---|---|
| **A. 3D 状态增量 + 压缩** | ✅ `?since=<rev>` 增量（changed/removed/unchanged）+ `GZipMiddleware(minimum_size=1024)` |
| **B. 重计算卸载与保护** | ⚠️ 部分：**预算/超时已做**（隐式曲面 8 s 预算、分辨率上限 48、`GGBPY_IMPLICIT_BUDGET`）+ 协作让出；**线程池卸载未做**（实测阻塞为间歇性、让出后 p50 −20%，当前收益不足） |
| **C. 2D 检测入库** | ✅ `devtools/test_2d_matrix.py`（**170**）+ `test_2d_api.py`（44）+ `verify_2d_ui_matrix.js`（72），并入 `run_all_detection.sh`（11 步） |
| **D. 撤销差量快照** | ⛔ **判定不需要**（测量见 P0-3：快照 58 B/对象不是瓶颈；瓶颈是重元素重算，而记忆已 LRU） |
| **E. 投影缓存 + 遮挡换算法** | ⚠️ 缓存 ✅；换算法 ⛔ 判定不需要（原回顾 §7：9,288 面下 8 ms，成本远超收益） |
| **F. 结构收敛** | ✅ 三项全完成（schema / blob store / 注册单一来源） |
| **G. 补齐 API/前端回归** | ✅ share/demo/load/download/cas/image/编辑栏/键盘/会话均已入库并能一键复现 |
| **H. `.ggb` 内嵌网格；SVG 3D 投影** | ✅ 均实现并有端到端断言 |
| **I. `commands.py` 与 `app.js` 拆分** | ✅ 内核 7867→**1155**、前端 5979→**2768** |
| **J. 多会话隔离** | ✅ 见 P0-1 |

### §0 之外的补强（2026-10-04 第五十九批）

- **CAS 算子接线为构造命令**：`Solve` `NSolve` `Limit` `PartialFractions` `Substitute` `SolveODE`（CAS 面板早已实现，但只在那里可用）
  + `SurfaceArea` + `IsFinite` —— 每条在 `SPECS` 只加一行（§6-F「命令注册单一来源」的直接红利），全部 DAG 可重算

### 判定「不需要做」（有测量或原回顾依据）

- **差量撤销快照**：快照仅 58 B/对象、满栈 2.2 MB，不是瓶颈；真正瓶颈是重元素重算，已由 LRU 记忆保护
- **改记忆淘汰策略**：`memo.get()` 命中即 `move_to_end`，**已经是 LRU**（已加行为测试锁住，防改回 FIFO）
- **面心排序 + 空间哈希遮挡算法**：原回顾 §7 的依据（9288 面 8 ms）仍然成立，成本远超收益
- **重写 WebGL/GPU 渲染 / 引入前端框架**：原回顾「明确不建议」；前端改用**零构建多模块**方案完成拆分

### 复核入口

```bash
bash devtools/run_all_detection.sh                               # 11 步 / 1514 断言（需 8090 服务）
python3 devtools/bench_blocking.py --n 48                        # P0-2 阻塞压测（GGBPY_YIELD_MS 可 A/B）
python3 devtools/bench_undo.py --n 120 --heavy 32 --memo-cold    # P0-3 撤销成本模型
python3 devtools/test_quality.py                                 # 宽泛捕获策略 / README 章节守卫
```

## 1. 一页数字

| 维度 | 数值 |
|---|---|
| 提交 | 13（`4b02a58` → `45985bd`），remote = local |
| 内核 | 12,807 行（commands.py **7,671** / elements 1,257 / construction 793 / parser 558 / cas 404 / 其它 2,124）|
| 服务端 | 577 行（FastAPI，**32 个端点**）|
| 前端 | 6,164 行（app.js **5,596** / css 278 / html 290）|
| 命令 | **163** 条 + 中文别名 188 + 规范显示名映射 54 |
| 检测矩阵（入库、可重复） | 内核 **453** + API **150** + 浏览器 **112** = **715 断言**，`run_3d_detection.sh` **5/5** |
| 入库检测脚本 | 9 个（`devtools/` 下）|
| 未入库历史检测脚本 | **115/116**（devtools 下 JS 全部被 `.gitignore` 挡住）|

## 2. 十二批交付地图

| 批 | 提交 | 主题 | 关键能力 |
|---|---|---|---|
| 二 | `0a77fca` | 三层检测矩阵 + 度量修正 | 3D 点保 z、真 3D 距离/角度、`solid` 字段、`.ggb` 3D 警告（当时）|
| 三 | `483009f` | 嵌套求值 + Volume/Area + 求交扩展 | 嵌套命令就地求值、`Volume`/`Area` 立体、网格面序/朝向规范化 |
| 四 | `c58702d` | 空间圆 + 立体交 + 容差 | 球×平面→空间圆、立体∩立体（半空间裁剪）、截面周长、t=0 命中 |
| 五 | `70d535a` | 球×球 + 两圆求交 + 样式快照 | 球×球→交圆、空间圆×平面/×圆、undo/redo 保留 `locked`/`wire` |
| 六 | `43213c3` | OBJ/STL 导出 + 圆求交 | OBJ/STL 导出、球×空间圆、空间圆×空间圆 |
| 七 | `3890efa` | 显式曲面 + FitPlane + OBJ 导入 | `Surface[z=f(x,y)]`、3D 点列表 + `FitPlane`、`Mesh[id]` + 网格仓库 |
| 八 | `80cd192` | 参数曲面 + 隐式曲面 + STL 导入 | `SurfaceParam`、`ImplicitSurface`（marching tetrahedra）、STL(ASCII/二进制) |
| 九 | `73d1190` | 3D 统计 + 交线 + glTF 导出 | `Centroid` 扩展、`FitSphere`、球×立体→`curve3d`、glTF 2.0 |
| 十 | `55836d0` | 点云统计 + glTF/GLB 导入 + 渲染预算 | `BoundingBox`、`Covariance`、glTF/GLB 导入、LOD/遮挡预算、**修 3D 刷新 bug** |
| 十一 | `525b640` | `.ggb` 3D 往返 + 椭球 + 参数线 | 解除 `.ggb` 不支持 3D 的长期限制、`CovarianceEllipsoid`、`SurfaceIsoline` |
| 十二 | `45985bd` | 凸包 + 曲面取点投影 + 帮助升级 | `ConvexHull`、`SurfacePoint`/`SurfaceProject`、命令筛选/点击插入/规范显示名 |

## 3. 覆盖度真相（脚本实测）

- **命令**：三层矩阵引用 **43/163**；全部 devtools 脚本（含未入库）引用 **100/163**；**63 条从未被任何脚本引用**：
  - 变换/几何 **23**：`dilate reflect inverse locus pointonpath pointoncircle regularpolygon perpendicularline perpendicularbisector anglebisector foot circumcircle incenter incircle slope focus hyperbola parabola …`
  - 统计/回归/数值 **23**：`sum mean median mode min max stdev variance sort normal normaldist fitexp fitpoly fitpow fitsin histogram barchart boxplot …`
  - 编辑/脚本/宏/CAS **16**：`delete redefine rename setcoords setvisible macrocreate macrodelete macrolist areperpendicular arecollinear areconcurrent areconcyclic arecongruent solveineq implicit …`
  - 其它 1：`image`
- **API**：32 端点中 **17 个**未被 API 矩阵触及：`/api/drag /api/demo /api/batch /api/share /api/shared/{sid} /api/macro* /api/image* /api/cas* /api/download /api/export/svg /api/reorder`
- **前端**：15 个 3D 工具与主要交互路径、滑块、撤销重做、导出/导入、帮助面板已覆盖；**编辑栏**（改色/显隐/锁定/重定义/重命名/删除）、CAS 面板、试卷、分享、宏、图片插入、i18n/主题/移动端**无入库回归**
- **可复现性缺口**：115 个历史 JS 检测脚本未入库 → 2D 回归无法从仓库复现（`.gitignore` 只放行了 `verify_3d_ui_matrix.js`）

## 4. 架构债（带证据）

> 复核状态见 **§0**（2026-10-04）。

### P0 — 阻塞级 / 影响正确性与可用性
1. **服务端单一全局 Construction**（`server/main.py`：`cons = Construction()`）：所有客户端共享一份构造，无会话隔离、无鉴权。第五批"两个浏览器脚本并发互清场"就是这个结构的直接表现。
2. **重计算同步阻塞全局**（`process_line` → 同步几何计算）：`ImplicitSurface` 实测 n=24/32/40/48 = **0.88/1.23/2.03/3.12 s**（n 上限 64 → 约 7–8 s），期间所有请求排队；无超时、无取消、无线程池卸载。
3. **撤销/重做 = 全构造重放**（`construction.snapshot/restore`）：快照存 `(label, defn, style)`，恢复时对整条构造 `process_internal` 重放 —— 含 n=32 等值面时 **redo 1.20 s**（首次创建 1.48 s）；快照无差量、无计算缓存。
4. **3D 状态每次全量传输**（`app.js load3d` + 第十批的 `refresh3dIfNeeded`）：每次输入/撤销/重做都 `fetch /api/state3d`。实测载荷 **n=24 → 0.94 MB，n=32 → 1.71 MB**，服务端 JSON 序列化 10–19 ms；无增量、无缓存、无压缩。

### P1 — 质量与可维护性
5. **3D 渲染 O(边×面) 遮挡测试**：已有预算阈值（2000 面 / 4000 边 / 15 万乘积）兜底，但阈值内仍全量计算，且每帧重投影所有顶点（无投影缓存、无脏标记重绘）。
6. **命令注册四张表手工同步**：`COMMANDS`(163) / `ALIASES`(188) / `_result_kind` / `DISPLAY_NAMES`(54) 各写一遍，新增命令要改 4 处，漏一处就退化（如缺 `_result_kind` → 自动标签类型错）。
7. **`data` 约定散落无 schema**：`commands.py` 内 **24 处**内联 `{"objtype": …}`；`analytic/param/ranges/expr/meshid/lo/hi/normal/u/v/segs/pts/grid/center/axes` 等键各自为政，新代码靠约定与记忆。
8. **两个近乎同构的仓库模块**：`image_store.py`(64 行) 与 `mesh_store.py`(87 行) 只差校验/清理逻辑，可合并为通用 blob store。
9. **前端单文件 5,596 行**：`toolCollectPoints`(322) / `drawElement`(250) / `snapPoint`(217) / `render3d`(198) 四个大函数；i18n ~108 词条内联双语。
10. **几何工具重复实现**：网格边表派生分别写在 `mesh_store.edges_of`、`_ix_solid_solid`（内联）、`_convexhull_state`（内联）；`except Exception` **27 处**（无裸 except），个别会把编程错误吞成无声 `error` 状态。
11. **内核单文件 7,671 行**：`_transform_fn` 256 行、`process_line` 166 行；几何/统计/3D/CAS/导入导出全混在一起。

### P2 — 已知但影响有限
12. SVG 导出只含 2D 视图（3D 跳过，无 3D 投影视图）；`.ggb` 不内嵌网格数据（导入网格只能 .ggk）；`Perimeter` 对立体无定义（刻意）。
13. 2D 侧没有"限制/边界"文档章节（3D 侧很完整）。

## 5. 性能与资源实测

| 操作 | 实测 |
|---|---|
| `ImplicitSurface` n=24 → 48 | 0.88 s → 3.12 s；顶点 6.7k → 26.7k；面 13.3k → 53.4k |
| `SurfaceParam` 96×96（上限） | 39 ms；9,409 顶点；载荷 ~1.0 MB |
| n=32 等值面 Python 内存峰值 | 18.3 MB（顶点/面为嵌套 list）|
| `/api/state3d` 载荷 | n=24 → 0.94 MB；n=32 → 1.71 MB |
| redo（构造含 n=32 等值面） | 1.20 s |
| `.ggk` 体积（n=32 等值面 + 32² 环面）| **0.4 KB**（只存 defn，不存网格）✅ |
| 大网格重绘（浏览器内，LOD+遮挡预算）| 9,288 面 3 次重绘 **8 ms** ✅ |

## 6. 建议的下一批（按投入产出排序）

> 复核状态见 **§0**（2026-10-04）。

**P0（半批内可完成，收益最大）**
- **A. 3D 状态增量 + 压缩**：给 geo3d 元素加 `rev`，`/api/state3d?since=rev` 只回变化项；加 `GZipMiddleware`（1.7 MB → 约 0.2 MB）。必要时配合前端脏标记重绘。
- **B. 重计算卸载与保护**：`run_in_threadpool` 执行 `process`，并加"分辨率 × 面数"预算与超时（超时返回明确错误而不是挂住）。
- **C. 2D 检测入库**：新增 `devtools/test_2d_matrix.py`（变换族 / 统计回归 / 圆锥曲线 / 证明器 / 编辑命令），纳入 `run_3d_detection.sh`（改名或并列 `run_all_detection.sh`）。

**P1**
- **D. 撤销差量快照**：只存变化元素 + 重算缓存（解决 redo 秒级）。
- **E. 渲染投影缓存 + 遮挡测试换算法**（面心排序 + 空间哈希）。
- **F. 结构收敛**：统一 `data` schema（集中定义 + 校验）、合并 blob store、命令注册单一来源（一张表派生 4 张）。
- **G. 补齐 API/前端回归**：drag、macro、cas、share、image、download、export-svg、编辑栏操作。

**P2**
- **H.** `.ggb` 内嵌网格数据；SVG 3D 投影视图。
- **I.** `commands.py` 与 `app.js` 拆分（几何/统计/3D/CAS 子模块 + renderer/panels/i18n）。
- **J.** 多会话隔离（若真要用于多人教学再投入）。

## 7. 明确不建议做（避免过度工程）

- **不重写 WebGL/GPU 渲染**：当前 2D canvas + LOD + 遮挡预算在 9,288 面下 8 ms，成本远超收益。
- **不为非闭合网格硬凑 `Volume`**：保持"明确报错"比给出物理无意义数字好。
- **不追求 marching tetrahedra 的解析级精度**：3–4% 误差对教学足够，要更准提高 n 即可（已有上限保护）。
- **不引入前端框架**：5,596 行原生 JS 虽大，但零构建、单文件部署的收益仍在；应先做模块拆分而非换栈。
