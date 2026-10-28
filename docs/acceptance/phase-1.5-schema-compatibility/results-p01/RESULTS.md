# T074 最小兼容 p01：一请求后按协议终止

准确批准提交fe15f3d，manifest `0e3abcedfdfc5fa513fbbcb612ff4236d9453d11b21e4a19ea6ae0353842f59b`；登记ADR0043-approval-20261028.json和probe-p01/execution-approval.json。新窗口2026-10-28 20:03:36至20:05:06（Asia/Shanghai）。

## 实际观察和精确定位

仅S1发生一次real HTTP，服务返回200、status=completed、model=deepseek-flash、store=false、reasoning none，文本准确为`{"kind":"show_state"}`。本地Draft202012Validator确认该输出符合S1的带type Schema，响应text.format.schema也与请求相同。这是服务接收该最小请求并返回符合格式内容的证据，不证明对所有输入严格执行Schema。

服务报usage为95输入、6输出、总101，推理0。旧严格协议没有完成可信结算，原摘要observations保持空、unknown_protocol_or_usage=1；这些服务报告与实际账单/币种（未知）分开，不能写为零费用。

**实际本地阻塞为`WIRE_MESSAGE`**：准确`/output/0/phase`值为`final_answer`，旧p15_pilot_wire.validate仅允许message的id/type/role/status/content，故额外phase被拒绝。只读调用原validator复现同一错误；响应文本、usage、模型等未触发此前门禁。其余条件尚需在新兼容视图下完整校验，不能直接把本S1登记为原批准协议通过。

按冻结规则，S1未完整通过就终止：没有control_validated、S2预约、S2发送或S2文件。结果terminal/inconclusive_stopped，预留1、dispatch标记1、完整响应1、real1、未知1、未用1不继承。对照没有成立，因此**无法确认enum-only是否导致原复杂Schema的400**，也没有C角色、sol审核或课程内容。

## 文档约束

[OpenAI官方部署说明](https://developers.openai.com/api/docs/guides/deployment-checklist)定义assistant phase的commentary/final_answer含义；这是DeepSeek所称兼容格式的参照，并不自行证明DeepSeek所有phase行为或字段都可信。本次原始响应独立提供了final_answer这一实际值。旧允许字段缺少这个标准定义的元数据，是本项目解析器的兼容缺口，不能把本次200误称为服务拒绝Schema。

OpenAI API参考整页抓取超出工具容量；已实际读取官方部署说明及reasoning指南的phase段，未只用搜索摘要。未调用OpenAI服务或索取OpenAI Key。

## 证据与验真

受控原件位于`/private/tmp/edumind-p15-schema-probe-p01`，目录0700/文件0600，逐文件SHA见evidence-manifest.json，不将原件提交Git。准确包46文件及旧p01/独立真值均未改。独立语法/格式定位仅读取本次合成响应，不读取任何参考答案。

实际--run返回2；--check-results同样返回2，因为结论不确定，而`evidence_verified=true`、`recorded_window_verified=true`，不是验真失败。assessment.json保存重算值，原summary/事件保持原字节。公开资料读取属于文档核对，不是新的模型请求。本批仅1模型HTTP；与此前头插p01的1次另账，共2次，不复用任一账本或unknown。

下一步先离线验证仅认可`phase=final_answer`的窄兼容视图，拒绝commentary/未知值/其他新字段，保留完整原件和原教学标准。旧p01已经终止，不能因离线发现可兼容字段就回填control或补发S2；若继续真实对照须全新准确包和窗口。相关角色准确Schema/响应准入前，不启动一份课程或完整诊断。
