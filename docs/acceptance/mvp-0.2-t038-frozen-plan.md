# T032 v2正式复测执行冻结（T038）

2026-09-27用户明确授权：“按冻结计划执行，最多240次实际模型尝试”。
继承mvp-0.2-t032-retest-plan-v2.md所有20样本/单并发/0计费预热/180秒/240实际尝试参数，
不替换失败、不补跑，认证/余额/配额异常立即停止；不混旧20或T035三个诊断样本。

代码基线a7e7cc8efe86d568c4e2c72c4f9ffba2ae2c6039，包含T036正文无损修复。
当前只读configured model deepseek-flash，structured responses_json_schema，正文Responses streaming。
本轮不修改.env或切模型；返回模型由实际structured账本保存，stream没有返回模型元数据。
画像profile-v1/profile-instructions-v2；正式生成learning-resources-v1/learning-resources-instructions-v8；
审核resource-review-v3/resource-review-instructions-v2；首段无独立版本，raw保存四个源文件SHA。

新隔离PostgreSQL edumind_perf_t032_v2，迁移0009；localhostHTTP1.1→实际Vite4182代理→
Uvicorn8012单worker→当前配置Provider。不是TestClient/route mock或合成已审核资源。
Provider冷热/缓存、外部路由和排队未知；无计费预热；首匿名请求数据库冷连接不剔除。
macOS本机网络，真实Provider传输；瞬时负载在准备时另列，本轮采样不并行工程检查。

全部固定公开目标“我想理解单链表的前置知识，先看 C 代码。”，每样本新匿名owner/key。
HTTP首字节、头完成、SSE状态、任意非空delta、确认教学正文token、完整首段、正式发布分开。
PRD client HTTP P95≤2秒/可学习段落≤10秒；既定validated教学token2秒独立内容门槛不改变。
最近秩第19/20，全计划缺失按∞，条件成功P95不能替代全计划；所有候选hash绑定独立评审。
沿用真实空行/临时流结束边界、完整教学陈述、排除标题/纯代码，未知不能算通过。
编号或成员句点辅助字段不是人工语义通过依据，不改变已批准规则。

匿名HTTP与全准备另存；完整用户等待含匿名全准备。恢复只GET原操作，记录Provider增量。
本轮不另注入断网或取消，不冒充T031真实断网重新验收；T030回归已在434测试通过。
证据使用独立mvp-0.2-t038-{raw,ledger,decisions,audit}.json及正式报告，输出open(x)保护。
公开候选允许保存；不记录凭据、Provider URL、Cookie/CSRF、私有画像或完整临时流。

复现命令（已存在文件不能覆盖，未来复跑需新授权/库/输出）：

```text
# backend，数据库URL通过进程环境指向专用隔离库，不写.env
uv run --frozen alembic upgrade head
uv run --frozen --env-file ../.env python ../docs/acceptance/serve_first_screen.py --confirm-billable --ledger ../docs/acceptance/mvp-0.2-t038-ledger.json
# root，另一终端
EDUMIND_API_PROXY_TARGET=http://127.0.0.1:8012 pnpm --dir web dev --host 127.0.0.1 --port 4182 --strictPort
# backend，单次20样本
uv run --frozen python ../docs/acceptance/run_first_screen_v2.py --confirm-billable --ledger ../docs/acceptance/mvp-0.2-t038-ledger.json --output ../docs/acceptance/mvp-0.2-t038-raw.json
# 独立逐候选评审后（非计费）
uv run --frozen python ../docs/acceptance/audit_first_screen_v2.py --results ../docs/acceptance/mvp-0.2-t038-raw.json --decisions ../docs/acceptance/mvp-0.2-t038-decisions.json --output ../docs/acceptance/mvp-0.2-t038-audit.json
```

采样后停止计费服务，真实未达门槛则T032仍blocked；T038交付的是单次采样和诚实审计，
其独立证据完成提交不等于T032通过。不push/merge/自动归档或进入MVP0.3。
