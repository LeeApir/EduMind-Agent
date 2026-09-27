# T032下一轮有界复测计划 v2（待执行批准，0实际调用）

不是原计划的覆盖或追加补跑。新计划独立证据文件；原20样本/162尝试/raw/audit/失败结论保留。
需另行确认执行；当前轮明确禁止付费，不使用历史宽泛授权自动运行本计划。
T033/T034本地完成后T032仍blocked，不以mock结果作为done或阶段切换依据。

## 冻结参数建议

- 20正式样本，同一公开目标“我想理解单链表的前置知识，先看 C 代码。”；新匿名owner/新key各一次。
- 单并发，0计费预热，全部样本保留，特别是第一样本不丢弃。
- 每次learning POST总体180s；匿名建立独立30s；不客户端重试/替换失败或超时样本。
- 全局240实际adapter尝试硬上限（含Gateway/审核重试），常规约160，但不保证费用。
  余额/认证/配额异常或上限到达停止，把剩余未发样本记录为unattempted，不另开预算。
- 当前配置Provider/模型/传输，不切换或修改.env；新隔离PG例如edumind_perf_t032_v2，0009迁移。
- HTTPX匿名建立 → actual Vite4182 → Uvicorn8012；learning POST由受限loopback原始HTTP/1.1采集。
  若需TLS/HTTP2等网络，不沿用原始HTTP1测量入口伪称兼容，应另建立并验证口径。
- 记录操作系统、依赖/commit、prompt源码SHA及指令版本、configured/returned model、传输、
  主机网络、机器负载；停止并行工程检查，以减少上次负载混杂；Provider冷热/缓存未知仍注明。

## 指标与评审

分别记录client POST起点及校验后起点到：原始HTTP首字节、HTTP头收齐、完整SSE状态、
任意非空delta、人工确认教学正文首token、完整可学习段落、scene_ready。
匿名会话耗时另列；端到端完整用户旅程应加上必要的匿名建立，不能用移到计时外粉饰。
PRD首字节2秒、首段10秒标准不变；校验后教学token2秒仍独立检查原批准计划内容门槛。
状态/头都不是教学内容；旧指标不能作新的精确HTTP首字节或正文证据。

沿用已批准段落规则：标题/空白/纯代码排除，真实空行或temporary结束为边界，
至少完整句末标点教学陈述，语义不能确认则未确认，不设字数门槛。
所有候选保存到达/完整边界单调时间、ID/SHA和固定公开基准段落，供独立人工评审。
不保存密钥、真实ProviderURL、Cookie/CSRF/HTTP头、私有画像、任意用户目标或完整模型流。
导语明确标记intro后继续审后段；缺失或unconfirmed的早期候选不能静默排除。
decision以sample→candidate ID→SHA/verdict/reason绑定；最早教学段落用采集时刻，不用审核时刻。
候选JSON本身不自动代表通过；raw与decision/audit各自独立，禁止覆盖。

P95最近秩第19/20位，缺失按+∞并报告missing与失败率；条件成功分布另列。
所有样本确认且无操作失败才允许整体门槛通过；完整发布时长不替代首段。
特别报告固定目标/C指针场景有限样本不证明全课程、公网或并发容量。

## 入口（本轮未执行，命令不构成调用授权）

启动仍使用serve_first_screen.py，保留校验后clock header与240 adapter硬预算。
计费执行参数和全新输出路径必需。准备阶段只读配置，不打印凭据。

```text
# backend，预先设置隔离EDUMIND_DATABASE_URL，不打印值
uv run --frozen alembic upgrade head
uv run --frozen --env-file ../.env python ../docs/acceptance/serve_first_screen.py --confirm-billable --ledger ../docs/acceptance/<v2-fresh-ledger>.json
# root，另一个终端
EDUMIND_API_PROXY_TARGET=http://127.0.0.1:8012 pnpm --dir web dev --host 127.0.0.1 --port 4182 --strictPort
# backend，另一个终端，一次20样本
uv run --frozen python ../docs/acceptance/run_first_screen_v2.py --confirm-billable --ledger ../docs/acceptance/<v2-fresh-ledger>.json --output ../docs/acceptance/<v2-fresh-raw>.json
# 人工逐候选核对后，另存decision文件，再独立审核（不计费）
uv run --frozen python ../docs/acceptance/audit_first_screen_v2.py --results ../docs/acceptance/<v2-fresh-raw>.json --decisions ../docs/acceptance/<v2-decisions>.json --output ../docs/acceptance/<v2-fresh-audit>.json
```

执行前仍须确认审批、当前配置和240预算未变；上限耗尽或结果失败即保存blocked并停止。
若先选择画像时序产品变更，需先批准契约并独立实现验证，再冻结新的复测基线。
