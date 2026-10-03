# 已提交课程目录版：干净 checkout 验证

> 2026-10-03 整理：下列本地材料路径沿用原仓库相对路径；读取及历史恢复方式见[材料索引](README.md)。旧指标、失败与判定不变。

提交 `c7831d1dbf34219f22c6f7da30913002fa46966d` 的目录版可按锁文件安装、构建并在本机运行。独立 checkout 从开始到结束均无 Git 改动，566 个已跟踪文件逐字节一致；未复制真实 `.env`、未提交 T033 候选、原工作区虚拟环境或 node_modules。当前工作区的实验和旧证据保持原样。

机器结果（本地材料 `docs/acceptance/mvp-0.3-clean-checkout-20261003.json`）、执行协议/源码哈希（本地材料 `docs/acceptance/mvp-0.3-clean-checkout-20261003-evidence/protocol.json`）、全部日志及执行器（本地材料 `docs/acceptance/mvp-0.3-clean-checkout-20261003-evidence`）独立保存，不覆盖 T034/T045/T046 的旧协议、结果或成绩。

| 检查 | 实际结果 |
| --- | --- |
| `uv sync --frozen --offline --python 3.11` | Python 3.11.16，新 venv 安装 41 包，使用本地缓存 |
| `pnpm install --frozen-lockfile --offline` | pnpm 10.33.0，新 node_modules 安装 311 包，0 下载；esbuild 构建脚本默认忽略，后续实际 build 成功 |
| `pnpm build` | vue-tsc 与生产 Vite 构建通过 |
| `pnpm test --run` | 22 文件、136 测试通过 |
| 目录包/内容/签核/模式/度量闸门/动画模板及缓存/审核归属离线 pytest | 84 通过，21 跳过；没有把跳过算通过 |
| 新隔离库 Alembic + 目录 publication/sessions/quiz/demo/exports/mode pytest | 从零迁移到 0017；14 通过，含上行先跳过的 2 项 DB 模式检查；与离线套件有重叠，不累加为唯一测试数 |
| Ruff / ESLint | Ruff 全 app/tests 通过；ESLint 0 errors、67 既有 warnings |
| 任务/完成提交/人工签核 | 45 done 完成标记及依赖核对；T033 blocked；Lee 签核精确 digest 可发布 |
| 新建独立运行库 + Uvicorn + `vite preview` + Chromium | health/runtime 200；实际加载刚构建的 `/assets/`；10 节点/30 原始签核资源/30 不含答案的题面；一次真实 UI 学习、代码、3/3 评分、重复掌握度不变、刷新恢复、预设演示恢复/返回、笔记下载和路径通过；动态 409、CSRF 403、其他 owner 404；无页面异常/外网尝试 |

测试数据库仅使用新建的 `edumind_catalog_clean_*` 库；真实人工签核课程只登记到隔离运行库。API 的 Provider 构造被测试执行器阻止，后端连接与浏览器请求仅放行本机地址。新增 Provider 请求 **0**，累计 **2033/2500** 不变。运行后关闭 API/Web 服务。

运行探测 v1/v2 的失败也已保存：API 已正常启动，macOS 系统代理使 HTTPX 默认 `trust_env=True` 请求得到 502；显式 `trust_env=False` 和 curl 直连返回 200。v2只增加启动观测，v3只调整测试执行器的本机代理设置（Chromium `--no-proxy-server`），产品源码不改；v3真实运行通过。各执行器版本及哈希独立保留。

旧 `verify_catalog_exit.py` 在这个 clean checkout 实际退出 1，首先缺少 `.env`。它是旧冻结工作树审计器，还依赖历史未提交实验/证据，不能充当交付 checkout 的验证入口；没有复制密钥/实验、改旧 hash 或将失败当通过。其失败日志单独保存。本轮使用当前提交的目录包/签核/权限/数据库/页面检查得出运行结论。

这次没有重新渲染 Manim、没有重跑动画/性能矩阵、没有构建新部署镜像或公网部署。19 个 Docker 内容/渲染项仍未启用；MP4/SRT/Worker 的历史证据边界保留，不能据此宣称新环境媒体链路已验收。依赖安装验证使用已有离线缓存和本地 Python，不代表无缓存设备已完成下载测试。

动态生成、重解释和实时 AI 仍暂缓，T033 仍 blocked；没有 Provider、正式基准、部署、push、merge 或进入 Phase 1。保留独立 checkout 供复核，位置见机器结果。
