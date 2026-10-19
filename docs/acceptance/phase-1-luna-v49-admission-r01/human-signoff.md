# 独立标签与逐槽结果签核协议

签署者为用户Lee，或Lee另行明确授权且能核对数据结构/C语义的独立人工。当前执行器只接受Lee记录；换人须新包，不冒用身份。Codex材料作者、读者检查子代理、Mock回复、待测模型不能代替独立人工。助手可在用户实际确认后忠实登记原话和准确摘要，不可预签、推测批准或将费用豁免写成质量通过。

## 执行前两类确认

先阅读materials-review.md的12份完整目标/计划/学生材料、proposed-labels.json与README停止规则。标签有歧义就先修正、换新包，不先打API。一次确认全部材料/标签可以登记一份labels-human.json；不能事后看结果改标签让它过关。

以下是格式示例，**占位内容不能通过运行门禁，本包不创建这些文件**。H为manifest.json经qwen_review_budget.canonical排序序列化后的SHA256，不是原JSON文件字节摘要；L为manifest.files中proposed-labels.json的字节SHA256。CLI只读检查输出H。

run-approval.json：
```json
{
  "manifest_sha256": "H",
  "requests": 12,
  "cost_policy": "uncapped_by_explicit_user_instruction",
  "reviewer": "Lee",
  "source_user_message": "实际用户批准本准确包和12次上限的原话/消息标识",
  "decision": "approve_exact_diagnostic"
}
```
labels-human.json：
```json
{
  "manifest_sha256": "H",
  "labels_sha256": "L",
  "reviewer": "Lee",
  "source_user_message": "实际用户逐份核对后接受12份材料和标签的原话/消息标识",
  "decision": "accept_all_materials_and_labels"
}
```

## 每个真实响应后的确认

执行run_luna_admission.py --run-one只发一槽，结果保存在local-materials/phase-1-luna-v49-admission-r01/<slot>.json。用户应核对实际最终回答和所有引用字段；完整性包含业务必检ID、未决/缺口与真实完成状态，不能只看HTTP200。所有主辅断言/影响/分类都要检验，引用逐项支持实际命题。检查与冻结预期对应：正确对照干净pass，缺口具体needs_human，事实/安全具体reject，混合保留真实覆盖不足。没有结论时维持等待，不记通过。

用户实际确认后，登记assessments/<slot>.json；R为命令输出的准确receipt_sha256：
```json
{
  "manifest_sha256": "H",
  "receipt_sha256": "R",
  "reviewer": "Lee",
  "source_user_message": "实际确认这一份回答的原话/消息标识",
  "integrity": true,
  "all_claims": true,
  "all_citations": true,
  "criterion": true,
  "issues": []
}
```

上例只说明结构，不是预先通过。实际任何一项false或issues非空必须保存真实问题；下次只读检查/尝试会持久halt，不能修改否决记录恢复。若判据路由已失败，运行器本身已halt，不等待人类把它改成pass。

前8槽全通过后，还须用户明确“允许进入4份新材料”，登记screen-pass.json，receipts精确包含前8份{slot:R}，其余字段为manifest_sha256=H、reviewer=Lee、source_user_message实际原话、decision=admit_holdout。费用/初始12次批准不等于这一阶段晋级。

最后一份也要签核，执行--check-complete只可得到DIAGNOSTIC_SIGNED_PENDING_T040_ADMISSION，不授予T040完成或生产发布。没有结果的槽保留未运行，费用/Token未知不填0。全部记录作为新的诊断证据保存，旧Qwen/DeepSeek失败不改。
