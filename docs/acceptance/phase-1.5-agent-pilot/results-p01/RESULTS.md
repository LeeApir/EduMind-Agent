# T069 p01 受控实验结果

2026-10-28，准确执行包提交 `1bd3228`；manifest `295bc335af529b6906a51a61c5e22586b414d4e6c9986068534703b7b0aebe0d`。用户明确批准 ADR0042 A—C、两指定服务合成外发、90 HTTP / 新 3 小时窗口及本批 token/金额例外，登记见执行包 execution-approval.json 和 ADR0042 批准登记。

## 观察与停止

首槽 E03-S01 / B 只发出 1 次生成请求，DeepSeek 官方 `https://api.deepseek.com/responses` / `deepseek-flash` 返回 HTTP 400：`Invalid json schema: one of type, anyOf, $ref field is required`。原始错误另含服务请求 ID，原件保留在受控证据目录。请求使用 text.format.type=json_schema、strict=true、reasoning.effort=none、max_output_tokens=8000，原始完整 Schema 未投影或修改。

结果 reason=HTTP_STATUS、state=stopped；批次不可逆停止，无传输重试、Schema修补、补样、回退或重发。未收到模型课程内容，versions=0；没有审核模型调用、修复或独立通过检查点。该响应证明此准确 Schema 请求被接口拒绝，错误未定位具体子路径，不能据此断言 Responses 接口缺失、其他 Schema 一定失败或模型教学质量不合格。

## 完整分母与未知

计划每臂 10 支持+4拒绝，共 28 臂槽；本次 B 首支持槽停止，余下 27 臂槽未运行。首次结构/首次端到端/最终端到端均为 B 0/10、C 0/10；正确本地拒绝 B 0/4、C 0/4，拒绝槽均未运行。零成功仅反映完整固定分母下未取得成功证据，不能转换为已观察到 20 次教学失败。

预约1、记录真实HTTP响应1、unknown1、pending0。用量未提供，实际输入/输出/推理token、币种、收费均未知；不能把400或无内容记成零费用，unknown不退还请求占额。剩余授权不用于新批次或继续调用。

## 证据与验真

完整原始请求/响应/状态、准确grant与调度输入、逐槽result及SQLite事件/调用账本位于 `/private/tmp/edumind-p15-agent-pilot-p01`。原件不提交Git；公开摘要清单见 evidence-manifest.json。开发侧未读取独立truth/ratification/推导正文，独立参考摘要见准确包。授权header不进入证据。

实际执行 `backend/.venv/bin/python scripts/run_p15_agent_pilot.py --start` 返回0/requests0；唯一 `--step` 返回2/stopped/calls1；随后 `--assessment` 返回0，evidence_verified/authority_pins_verified/recorded_window_verified=true，batch_state=stopped，unrun_arm_slots=27。详细输出见 assessment.json；本机时间核验不等于外部可信时钟认证。

停止后另做零调用负测：将 load_keys 插桩为必抛错，再调用 --step，准确返回2/BATCH_NOT_ACTIVE，未触达Key，SQLite账本字节摘要不变。该负测未预约、发送或新增任何HTTP，不能被记作第二次真实调用。

T069仅核对受控采集是否合规，接口兼容未通过、教学质量未测。独立证据复核和T070全量评估另行记录；不得把本说明或模型缺失当作独立质量通过。catalog_only、T038 blocked、H封存保持，不开放生产或自动追加调用。

## T069交接

独立助手已实际重跑只读核验并逐原件复核采集合规，结论通过；见 [独立采集复核](../t069-preparation/EXECUTION-EVIDENCE-REVIEW.md)，摘要 `78f67b77d7e0d188f2532057a52f81da4d98628b094b662dfb03af36d638e0c5`。主执行复核公开报告；完成提交后才领取T070，由同一独立助手评估全部现有产物/缺失与指标。不得把此处采集合规通过解释为教学或接口兼容通过。下一步不是修补或重试。
