# AGENTS.md（ggbpy 项目）

## 启动流程

每次会话（**工作目录应为 `/home/kumath/ggbpy`**）：
1. Read `SOUL.md` → 我是谁、怎么干活（项目工程纪律，**必读**）
2. Read `USER.md` → 用户在做什么、协作偏好
3. Read `memory/YYYY-MM-DD.md`（今天+昨天）→ 近期上下文
4. 主会话再读 `MEMORY.md`（若存在）

## 项目速查

- 平台：Python 动态几何（DAG 内核 + FastAPI + 零构建 Canvas 2D/3D）
- 起服务：`./run.sh` → **http://127.0.0.1:8090**（规范端口；改 `kernel/` 后必须重启）
- 全量检测：`bash devtools/run_all_detection.sh`（11 步；**必须出现「全部检测通过」才提交**）
- 仓库：Gitee `kumath/ggbpy`（branch `main`）；**本地提交，用户手动推送**
- 记忆：`memory/YYYY-MM-DD.md`（每日原始日志）· 想记住的**必须写文件**

## 铁律（摘自 SOUL.md）

- 一批 = 一需求 = 一提交；每批：补断言 → 更新文档 → 本地提交 → 告知推送
- 数字**从实际输出抄**；不用"看起来更好"替代"已验证"
- 不发布 `PROJECT_SUMMARY.md`；不删文件（用 trash）；出网操作先问
