# T087：分离任务准确验证包 r01（待审查，未执行）

**ADR0048 A—D已获用户接受；本包只完成控制器/离线测试与准确冻结。真实Provider调用0，没有新窗口、费用例外或执行许可。** 批准登记见[0048-approval](../../ADR/0048-approval-20261029.json)。原ADR/提案字节保持，当前接受状态以登记为准。未来执行scope预留PHASE-1.5-T088，根账本todo未领取；本任务完成不自动执行。

## 准确请求与不变边界

P0→W0→W1→W2→W3→W4→R0，七份.json逐字节复用已接受的[T086请求示例](../phase-1.5-separated-protocol-repair-r01/README.md)，没有改Schema、strict、顺序、Prompt或预期数据。请求字节/哈希见[requests.json](requests.json)，全源码/输入/运行时闭包见manifest.json；新控制器不覆盖T085或任何旧入口。

仅`https://api.deepseek.com/responses` / `deepseek-flash` / reasoning none、temperature0.2、stream/store false、max_output_tokens4096。所有例使用现有B完整Schema；其他三Schema和严格wire/local实现仅核对冻结，不在本包重新准入。

## 控制器的两种后置判据

- **P0、W0–W4**：先通过原有严格信封/准确Schema回显、phase/usage、单个JSON、现有Schema/局部规则，再逐值比较该请求的expected_output。只符合Schema但值不同也失败。
- **R0**：同样严格校验，核对原候选摘要、意见绑定与限定minor/difficulty范围；必须确实只改变`/paragraphs/0/text`。输入没有expected_output，不能用固定回显字符串当修复目标。原答案/代码/题目/动作不被程序补填或替换。
- R0机械合格仅记录`sample_status=pending_independent_semantic_review`、`fixed_echo_verified=false`、`repair_success=false`、`semantic_evaluated=false`。代码不导入手写参考改写做精确匹配，也没有设置语义通过的入口。

全部网络例校验后，终态只能是`network_complete_pending_semantic_review`；汇总固定`repair_success=false`、`diagnostic_success=false`、`full_role_admission_complete=false`。CLI `--run`/`--check-results`对该状态返回**exit3（待复核）**，不是exit0“修复成功”。协议/范围/预算等失败返回exit2；仅离线`--check`成功返回0。独立语义复核需另存有依据的评估，不能篡改本包summary来晋升状态。

## 实现与实际回归

[任务判据模块](../../../scripts/isolated_diagnostics/p15_separated_probe_contract.py)、[受控控制器](../../../scripts/isolated_diagnostics/p15_separated_probe.py)、[准确CLI](../../../scripts/run_p15_separated_probe.py)、[控制器回归](../../../scripts/tests/test_p15_separated_probe.py)。继续复用冻结的strict_json、wire.validate、Schema与local.validate；没有修JSON、裁前缀、删除字段或放宽类型。

实际控制器在HTTP MockTransport中跑完全部七槽并从原件只读重算：两种不同良好改写和故意错误讲解都保持待复核；未改、越界改答案/代码/题目/节点/增段、非法JSON/返回Schema/额外或重复字段等失败全批停止。回归检查改写/重排/晚到/stop后事件、伪造R0成功/回显、summary篡改、Mock冒充real、旧scope/费用/窗口、只读不读Key和不可重启。

[Mock证据索引](mock-evidence.json)的8组48个模拟HTTP位于`/private/tmp/edumind-p15-separated-mock-r01`，原件0700/0600，明确model-free；故意错误讲解pending证明机械门不代签语义，不表示讲解正确。旧T085及其43份真实原件不动。实际命令/结果/范围见verification.txt。

## 冻结预算、费用与停止

policy.json是代码核对的权威配置：最多7HTTP，新登记起900秒含等待/处理，单HTTP60秒、DNS9秒；输入占额8192×7=57344、总输出请求上限4096×7=28672，请求/响应65536/262144字节。固定顺序，前槽完整通过才下槽，无重试、重定向、回退、额外计数/models调用、调字段补发或自适应增加样本。R0后网络阶段结束等待独立语义复核。

定向公网DNS使用有界空环境子进程，拒绝非公网并固定本次IP，保留TLS Host/SNI，禁环境代理；只使用EDUMIND_DEEPSEEK_COMPAT_API_KEY，不加载AIAPI或通用Key作回退。scope/package/全部确认/有效新窗口/既有目录/路径检查先于凭据，pending入口拒绝时不读取.env/Key、不DNS、不建真实目录。

pricing.json冻结2026-10-29检查的[DeepSeek官方价格](https://api-docs.deepseek.com/quick_start/pricing/)：缓存未命中峰时输入$0.30/百万、输出$1.20/百万，按全部占额参考**$0.0516096**。这是公开标价参考，不是账户收费或账单硬上限；实际账户费率/币种、上游输入输出硬限、取消后继续计费均未独立核实。

因此本包当前费用边界固定为“**无可验证实际金额硬上限；必须在准确执行批准时另获本包未验证费用风险例外**”。这不是已接受例外：execution-approval.json保留pending/accepted:false/费用false/窗口null。若用户不接受这种执行边界，则不发送，应先另备可验证金额硬限方案。旧费用例外、旧未用2请求及旧900秒窗口不继承；本轮不请求费用批准。

任何HTTP/超时/unknown发送、拒绝/截断、来源/模型/reasoning/工具/phase、Schema回显/严格解析/局部规则/精确回显或R0范围、报告用量/预算/时钟/安全异常，立即不可逆全批停止。原件保留、未知占额不退款重发，后续未运行不补样。R0状态不得晋升为自动修复成功；本包不提供角色/课程或T038准入。

## 审查及复现

```sh
PYTHONPATH=backend:. backend/.venv/bin/python scripts/run_p15_separated_probe.py --check
PYTHONPATH=backend:. backend/.venv/bin/python docs/acceptance/phase-1.5-separated-validation-r01/check_preparation.py
PYTHONPATH=backend:. backend/.venv/bin/python -m pytest scripts/tests/test_p15_separated_probe.py -q --tb=short
# 以下仅列工程接口，当前pending必须拒绝；不是现在可执行的授权：
PYTHONPATH=backend:. backend/.venv/bin/python scripts/run_p15_separated_probe.py --run
PYTHONPATH=backend:. backend/.venv/bin/python scripts/run_p15_separated_probe.py --check-results
```

请核对：P/W不能只凭Schema通过；R0不能用精确参考文案比对或自动成功；原件重算/CLI退出状态也必须pending；七请求/Schema与已接受提案完全相同；有限矩阵/预算/费用与停止规则没有继承旧许可。审查后再决定新准确包执行，本轮提交后停止，不激活窗口、不读Key、不调用Provider或重启T085。
