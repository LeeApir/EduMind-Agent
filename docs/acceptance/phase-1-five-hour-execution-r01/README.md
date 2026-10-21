# 受限验收执行包 r01

这是对已冻结16项材料的执行补齐。材料根保持 `f1cfe3af1bfccef27c02cc51d2486daf740be76982028b6ed9b9a1f9a7faa472`，原目录不改写。当前真实调用0、没有运行批准文件、没有真实调用台账；实现及零调用验证已完成，准确根需批准才可启动。未预签任何模型结果。

## 本次准确授权范围

- 顺序固定：U01–U08 → R01–R04 → A01–A04；每条结束先保存GPT评测再进入下一条，不要求用户逐条确认。
- 正常44次；硬上限60次；额外16次仅A原生有界修正。每次失败/超时/接收未知也占槽；无重试、回退、重复样本或附加judge API。费用不限。
- 生成：`https://api.deepseek.com/responses`，`deepseek-flash` / `none`，计划2048、资源/修正4096。
- 审核：`https://www.cbbb.fun/v1/responses`，`gpt-6-luna` / 请求`high`，8192，既有v4.9 Prompt/完整业务Schema/已实接投影不变；不推断渠道内部真实推理力度。
- 单次60秒、connect5秒、清理≤5秒；生成操作20次/180秒。44基础容量不伪记为已发送；未用容量不改作额外请求。
- 本轮采用保守T0 **2026-10-20 11:53:43（北京时间）**：这是此前大样本提案保存记录，五小时方案及材料准备在其后发生；用更早已知时间计入材料准备、执行补齐、检查及审批等待，不隐去开发时间，也不暂停或重置。**16:23:43停止新请求，16:53:43硬截止**。过期只可报告/停止/清理，不得复用本包重新计时；早期逐段研发精确耗时未知，不能伪造计时精度。

本次批准同时激活[ADR-0020](../../ADR/0020-limited-acceptance-and-gpt-evaluation.md)和[PRD补充](../../PRD-limited-acceptance-20261020.md)中的受限完成条件。原100目标与98%/95%/90%、总体错误频率/性能等延期且未证明。T040仍blocked，只有真实受限验收及必要检查满足并提交后才能按受限范围完成；不自动解锁T041/T042、生产dynamic或阶段退出。

## 已核实的边界

现有`.env`的活动连接是Luna；注释区另存有精确匹配DeepSeek Base URL和模型的连接组。执行器只从该唯一匹配组读取生成Key，或显式`EDUMIND_GENERATION_API_KEY`；不改.env，不打印Key，不把Key写入台账/请求/日志。init时只绑定私有凭据文件元数据，之后变动拒绝继续。

独立测试容器 `edumind-phase1-t037-pg` 须保留`edumind.test-only=phase1-dsl`及`127.0.0.1:15437`绑定。真实测试库为`edumind_catalog_five_hour_r01`，迁移`0031_teaching_context`；脚本化回归另用独立数据库，不能污染真实A项的owner和结果。只使用该容器配置构造连接，不读取生产数据库URL。

A项复用原`run_planned_operation`，包含真实持久化占槽、计划、三资源生成/审核、自然修正、单元审核和隔离发布。输入仍为冻结PlanInputs，路径明示为测试fixture；原文另经真实resolver检查。A02/A03解析实际ambiguous_aliases，用户已明确选择既定节点，登记[澄清](goal-clarifications.json)；不记自动解析成功，不冒称完整HTTP画像/路径创建旅程。

U/R只做各自scope的一次审核，R只发所选资源，不启动修正或发布。全体候选/原始HTTPbody/解析结果/全部修正输入和资源版本、业务Schema、准确wire/Host/SNI/审批IP、响应摘要链及实际用量保存在私有运行目录；usage缺失或接收未知保持未知。校验器强制逐一列出全部condition、impact、unresolved、unchecked及每个引用，不只核对主拒绝。语义正确性仍需GPT逐条判断，机械校验不能证明其判断为真。

## 准备检查（无模型请求）

```sh
backend/.venv/bin/python scripts/prepare_five_hour_environment.py --verify
backend/.venv/bin/python scripts/run_five_hour_acceptance.py check
```

第一条只创建/迁移allowlist隔离库并执行必要的脚本化回归；不启动公开服务、不读取模型Key、不发DNS/Provider请求、不运行新C。证据见[环境检查](environment-check.json)、[验证说明](validation.json)。首次准备失败及修复原因保留，不能只展示最后成功。

## 实际运行入口（当前未授权）

获准后才创建`run-approval.json`，准确字段由`authorize()`约束：manifest摘要、`approve_limited_execution_and_scope`、60次、18000秒、费用不限、GPT非独立真人、Lee及用户实际授权原文。不得提前伪填批准。`check`无需批准；`init/run/assess/report/stop`必须验证准确批准。

```sh
backend/.venv/bin/python scripts/run_five_hour_acceptance.py init
backend/.venv/bin/python scripts/run_five_hour_acceptance.py run --case U01
backend/.venv/bin/python scripts/run_five_hour_acceptance.py assess --case U01 --evaluation /absolute/path/U01-evaluation.json
backend/.venv/bin/python scripts/run_five_hour_acceptance.py report
backend/.venv/bin/python scripts/run_five_hour_acceptance.py stop
```

`init`不发模型请求，核验隔离库和凭据后初始化新台账，沿用上述T0。每次`run`只处理一例；A项内部仍可自然修正，不中途等待GPT。原始结果写好后状态为awaiting_gpt，不能自动继续。评分沿用原[格式](../phase-1-five-hour-test-plan-r01/evaluation.schema.json)，`run_id=five-hour-r01`，实际凭据/人类审批字段不得伪造。

台账和原件在`local-materials/phase-1-five-hour-execution-r01/`，权限0700/0600，不提交Key、真实env、完整原始私有body或SQLite。完成记录中的artifact_hashes绑定全部证据；评分必须绑定准确实际调用数/原判定、每条请求和完整响应；进入下一例前重核旧结果/评分/证据摘要。进程锁阻止并发，中断中的同例不能重放。红事件立即停；核心必达条件不再可能满足、附带错误项超过1也停止。原历史运行完全不恢复。

## 运行后的浏览器与清理

浏览器检查现在尚无真实A结果，故未运行。执行器已提供只读入口，待A结果存在时复用同一批结果，不额外生成：

```sh
backend/.venv/bin/python scripts/serve_five_hour_results.py --case A01
EDUMIND_API_PROXY_TARGET=http://127.0.0.1:18179 pnpm --dir web dev --host 127.0.0.1 --port 18178 --strictPort
```

打开 `http://127.0.0.1:18178/api/__acceptance/bootstrap`，为当前测试owner建立一次性测试会话，并通过sessionStorage恢复实际operation/精确publication版本，然后进入原Web界面。后端仅绑定loopback，白名单GET只读取该case；所有POST、人工批准、课堂生成和其他unit被拒绝，不存在浏览器新增模型调用。测试cookie仅为该独立库的可撤销fixture，生产cookie设置不改。

逐项核对实际阶段、自动完成/待审/失败显示、精确版本正文及待审正文隔离；截图和网络状态绑定实际result摘要，不将脚本化回归当实际读屏。未发生的自然修正/待审分支标“本轮未观察”，引用匹配源码的工程证据，不能额外制造候选。所有4项结果（含失败/未完成）保留在报告分母；缺少必需浏览器检查则不能宣布通过。

结束后Ctrl-C关闭只读后端和Vite；后端正常退出删除临时auth_sessions，异常退出时至多1小时过期且仅在隔离库，报告实际清理状态。保留测试库和私有证据用于审计，不自动drop、撤回失败或发布到生产。报告16固定分母、核心与完整质量分项、真实请求及已知/未知用量、准备/调用/评分耗时、未运行与所有失败、停止原因、清理和延期范围。`report`输出台账快照，不自动宣称验收通过；总体结论必须结合GPT记录及实际浏览器/清理证据。
