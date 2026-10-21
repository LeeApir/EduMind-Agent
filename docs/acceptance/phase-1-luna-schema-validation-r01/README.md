# Luna Schema 兼容修复：零调用审计与单次验证包

**本轮真实调用0；原r02继续停止，新包最多1次且尚未获准确调用授权。** 用户“yes”承接的是零调用契约核对和修复验证包准备，不登记为新真实请求批准。费用维持用户“不用考虑费用，无上限”的决定，不杜撰第三方单价或实际账单。

## 实际证据与问题范围

原r02首条HTTP400/invalid_json_schema，安全错误表示某嵌套Schema必须带type；完整错误正文未保存、路径部分已脱敏，不能唯一确定原接口首先拒绝了哪个字段，也不能认定只有一个问题。原回答、281字节错误摘要、唯一发送记录、持久halt和余11未发均保持。

审计直接读取原冻结requests.json中的完整实际wire，而非重建一个简化探测请求。原Schema共有47个没有独立type的节点，须区分：

- const/enum隐含取值类型，但部分Provider子集要求显式type；这是具体兼容风险。
- 纯$ref/anyOf节点本来可以不含独立type，不能把47个全叫成47处非法Schema。
- 原请求把完整业务Schema的所有$defs都带上了，包含本次审核未引用的plan、场景、plan_generation等；它们也含无type的const/enum与元组结构。

本次审核实际只引用finding定义。裁剪未引用定义后，明确剩余5处需规范化的字符串域：

| 位置 | 原定义 | 规范化 |
| --- | --- | --- |
| properties.schema_version | const=resource-review-v4 | 增加type=string |
| properties.scope | const=unit | 增加type=string |
| properties.verdict | enum=pass/reject/needs_human | 增加type=string |
| $defs.finding.properties.category | 四类enum | 增加type=string |
| $defs.finding.properties.severity | 三类enum | 增加type=string |

详细完整路径/分类、裁剪清单和原安全失败记录见[audit.json](audit.json)。[OpenAI结构化输出文档](https://developers.openai.com/api/docs/guides/structured-outputs)明确它只支持JSON Schema子集，并支持本地定义/引用；它是适配参考，**不是www.cbbb.fun兼容性证明**。

## 修复边界与实际请求证明

新增scripts/acceptance_support/luna_schema_projection.py，只供这个审核候选使用：

1. 从原Schema的$ref闭包保留所需定义，当前只有finding；外部/缺失/不支持的引用失败关闭。
2. 仅给现有const/enum的字符串域加冗余type。当前固定审核Schema若出现不可安全推断的混合或非字符串枚举则拒绝，不随意强转。
3. **所有可达约束均保留**：uniqueItems、enum、required、additionalProperties、检查ID/锚点、字符串/数组上下界等没有移除。strict参数保持原来未设置，不同时切换模式。
4. ProjectedReviewAdapter实际通过现有Responses适配器发送规范化Schema，返回后再用完整原业务Schema校验；请求审计摘要来自实际规范化出站字节，不伪用原请求摘要。

没有改backend/app、v4.9 Prompt/政策/业务Schema或生成流程，DeepSeek生成仍按原配置。本次不批量重冻12例，也不恢复旧r02。未引用定义裁剪和显式类型补齐在普通JSON Schema语义上等价：离线逆变换可准确重建原Schema；有效和无效响应对照保持一致。

requests.json旧首槽与本包[request.json](request.json)经真实review_once→显式路由→ProjectedReviewAdapter→现有Responses适配器→MockTransport捕获比较，**唯一请求字段变化是text.format.schema**。固定同一www.cbbb.fun/v1/responses、gpt-6-luna、low、8192总输出、单次60秒、temperature0、相同输入/Prompt/原始目标/教学节点/材料/判据。8.8.8.8是离线IP替身，不是渠道真实IP。Mock pass只证明构造和本地校验，不是模型质量成绩。

uniqueItems保持是因为本次真实错误并未证明它被拒；官方文档未明确该第三方支持情况。若新请求仍返回其他关键字错误，本次也停止，不能现场连续删除约束、增加调用或扩大输出上限。

## 单次真实验证的准确边界

- 只使用原r02的screen-complete，完整原始目标、材料及干净pass判据不变。原实际标签确认仅因内容/政策/判据逐字节相同可继续引用，不继承旧请求授权，也不预签新结果。
- **最多1次，无重试/修正/回退/其他探测；成功或失败后均停止。** 本包不包括剩余11例或正式T040。
- 成功须HTTP正常完成、准确model、完整原业务Schema、本地unit六必检、准确wire、完整用量且总输出≤8192；正确对照还应pass且findings/unchecked/unresolved为空。随后仍须人工核对全部断言/引用与实际结果，不能仅凭HTTP200晋级。
- 单次60秒覆盖Key读取、DNS、HTTP与解析；仅本地关闭最多5秒。上游/用量/Schema/判据/人工判断失败均保留，不重试。批准到期仍2026-10-21 23:59:59 Asia/Shanghai。
- 执行器验证新manifest/根目录/env身份/新1次批准、旧r02确实仍halt。使用全新私有目录与O_EXCL持久单次预留；中断、未知发送或本地错误都消耗槽，不可重放。
- 发送前再次核对准确授权/文件/原账本及固定公共IP/Host/SNI/path。无代理、重定向、隐式SDK重试或新厂商回退；无生产库、发布或掌握度写入。

## 批准及复核入口

只读核验：
```text
backend/.venv/bin/python scripts/prepare_luna_schema_validation.py
backend/.venv/bin/python scripts/freeze_luna_schema_validation.py
backend/.venv/bin/python scripts/run_luna_schema_validation.py
```

未来用户批准后才登记本目录run-approval.json，结构为：
```json
{
  "manifest_sha256": "本新包canonical manifest SHA256",
  "requests": 1,
  "decision": "approve_one_corrected_schema_validation",
  "reviewer": "Lee",
  "source_user_message": "用户对本准确包最多1次的实际批准原话或消息标识",
  "cost_policy": "uncapped_by_explicit_user_instruction"
}
```
本轮不创建这份记录。真实单次命令：backend/.venv/bin/python scripts/run_luna_schema_validation.py --run-one。未批准必须在新私有目录、Key提取、DNS和HTTP前拒绝。调用后必须停止，原r02旧11槽不移动、不改分。

所有准备验证见validation.json。T040仍blocked；Schema≥98%、自动正式成功≥95%、严重错误召回≥90%及人工不补自动分子保持，正式质量/T041/T042不启动。
