# DeepSeek 官方 Flash：一次性合成观察 r01

日期：2026-10-27。任务背景：PHASE-1.5-T038 仍 blocked。

用户已明确官方生成／`deepseek-flash` 候选，并要求“直接执行，不用批准”。本包依据该指令运行至多两例，不捏造独立人工逐哈希审阅；缺少独立官方 Key 时只允许离线检查。真实状态以本目录后续 RESULTS.md 及私有执行目录为准，本文本身不是已执行证明。

## 准确配置与请求

- 仅 `POST https://api.deepseek.com/responses`，模型 `deepseek-flash`、reasoning none；不继承通用 `.env` 地址／模型／Key。
- 凭据仅 `EDUMIND_DEEPSEEK_COMPAT_API_KEY`（进程环境优先，其次项目 `.env` 的同名字段），不回退现有AIAPI凭据。
- S1为128输出的固定OK／角色标记／null非流式；S2为512输出的enum／顺序／null流式。两份正文从已提交零调用准备包按原字节复制，SHA独立冻结。
- 无课程或审核生成，无真实学生数据或生产教学Prompt；不改变项目运行配置。
- 不发送工具、store、service_tier或strict；按官方文档的json_schema请求，本地完整Schema逐条校验。探针协议与生产准入区别见[ADR-0032](../../ADR/0032-deepseek-synthetic-observation.md)。

## 限额与停止

最多2HTTP／2生成，输入本地留额8192、输出请求总640、每次40秒、全批90秒、每响应1MiB；无重试／重定向／回退／重启。固定公开IP、Host和TLS SNI，禁用代理环境。S1有协议／内容／用量矛盾则不发S2；S2流失败同样停止。

峰时无缓存估算USD0.0032256；本地每槽USD0.005、合计USD0.01均保留unknown，不作为实际发票金额或可信供应商硬限。模型别名版本、计数、缺失回显及实际费用均可能未证。客户端终止不保证服务端停止收费，usage仍仅供应商报告。费率快照24小时，启动余量不足90秒即拒绝。

官方依据：[Responses参数](https://api-docs.deepseek.com/api/create-response/)、[兼容表](https://api-docs.deepseek.com/guides/responses_api/)、[费率](https://api-docs.deepseek.com/quick_start/pricing/)。文档声称支持不等于真实验证通过；实际执行时若账号或模型映射不同，不临场换ID／供应商。

## 入口

```bash
# 纯离线：不读Key、不DNS、不创建执行目录
backend/.venv/bin/python scripts/run_p15_deepseek_flash_r01.py --check

# 只有准确指令登记、有效费率、官方Key齐全后才可执行
backend/.venv/bin/python scripts/run_p15_deepseek_flash_r01.py --execute
```

`execution-authorization.json` 绑定当前manifest，记录真实用户原话、来源及未独立逐哈希审阅，不由入口自动制造。manifest绑定源码／依赖锁／请求／费率／方案，不含Key或`.env`。没有登记即拒绝；任何材料改动使原登记失效。

私有原件目录 `/tmp/edumind-p15-deepseek-flash-r01` 必须尚不存在；目录一旦创建，不能通过删掉目录或改变路径来重试。执行前有持久两槽预约和只追加收据；响应完成、HTTP失败、未知或未发分别可追溯，原件不提交Git。若进程崩溃，已预约额度保留，不自动恢复。

成功状态只叫 `two_synthetic_observations_only_unsettled`，不是课程兼容、审核或教学验收通过。两例终态、失败和未知都完整记录；输入计数独立性／上游快照／实际发票不因此通过。T038和旧失败不改分，所有后续真实调用须另行确定准确范围。
