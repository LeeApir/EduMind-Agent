# T108 r03 独立停止核对：规划通过，正文协议失败

2026-11-04。评估者：独立评估助手 `/root/head_goal_independent`，与开发执行分离。依据：准确r03包、实际安全导出的规划/映射/绑定/独立plan-review、正文request/attempt/body/failure及generate-diagnostic；未读取私有加密原件或其密钥。

**结论：应停止本批，剩余1次请求失效。规划语义pass保持；正文在严格JSON解析处失败，没有合格正文候选或完整新课程。普通措辞修复额度不能用于重复键协议错误。** HTTP200、完整body及final_answer阶段均不能替代输出协议通过，不可选择重复项中的某一份、合并字段或让助手修JSON后当作模型成功。

## 独立核对结果

- 真实规划已由本评估者独立核对并通过：plan_digest为`b6cc3d5304b87673c343a9cf31f11ae2cf8b44d4f12a07e852795ac71d4e4991`，结论只覆盖规划。该pass的planning_basis_binding与plan.binding.payload中的依据准确相等。
- 实际正文`generate.request.json`逐对象等于冻结`m.body(plan.binding.payload)`，其SHA256为`e646596ca6c49599f594613544b8d14f613493710f941d30e8e19da9f9bbbde1`，与正文attempt记录相符。没有用另一份计划、fixture或丢失basis的输入替代该次请求。
- 正文body收据记录HTTP200、body_complete=true、19720字节、SHA256 `4f05e35015c83b5660c3508e3b7e63671036ece326637ffeb56d5cf9d9f169ee`；与安全diagnostic的长度/摘要相同。failure为generate阶段的PilotError，状态failed_or_unknown。
- 执行方安全诊断将错误定位为model_output_text层的DUPLICATE_JSON_KEY：questions对象内link_target、normal_values、discarded_values、unreachable_count四个键各出现2次；诊断标明accepted_candidate=false、diagnostic_only_not_a_normalized_candidate=true。这份结构诊断不属于正文候选，不能据此进行教学事实核验或生成pass。
- 只读代码确认：冻结wire.strict_json使用object_pairs_hook逐项检查，遇到重复键立即抛PilotError；模型output_text再次通过该严格解析器后才能进入Schema/候选装配。实际CLI先保存body收据，再执行observe_generation；异常后保留failure/STOP及ACTIVE，不会生成generate.record或推进下一请求。仅用本地合成重复键JSON独立复现了同一DUPLICATE_JSON_KEY拒绝；没有对真实私有原稿做宽松归一化或覆盖解析。
- 本安全交付可见plan与generate两份attempt，分别是规划、正文，共2/3请求。普通教学措辞修复需要合格准确父候选及独立minor意见，而这里没有解析通过的父候选；协议错误按批准包必须停止，不得利用第3次请求修协议。

## 保留的成绩与未运行项

本批新增证据是：带同版程序依据的真实规划通过机械检查与独立语义核验；正文请求按相同计划/依据真实发出，并保留了被严格拒绝的原始body收据。规划pass不会随正文失败抹去，也不能外推为教学正文成功。

本批完整新课程为0。未运行合格正文的逐段/逐题/逐帧教学评估、普通措辞修复、最终候选入实际私有v2、完整新课程浏览器学习与刷新、独立课程教学效果评估。现有可读规划或旧离线夹具不能补作完整新课程交付；T108最终目标仍未达成。

## 证据与处置边界

本评估者**未独立解密真实raw**，未读取raw.key、Provider Key、终端或私有vault，亦未发起网络/Provider请求。完整加密body保存、解密回读及真实重复键位置来自执行方收据/安全诊断；本次独立核对其公开对应关系、冻结拒绝规则和正确停止处置，不冒称亲自重解析私有正文。用量是上游自报，实际金额仍未知，HTTP200不代表已验证金额或内容正确。

窗口仍为10:24:46–10:34:46（Asia/Shanghai），不延长。按本批规则保留全部原件、失败、规划pass和STOP/ACTIVE，未用1次失效；不得重试、选重复值、追加Schema补丁、换Provider或以措辞修复名义重发。r01/r02原失败和T102 blocked保持。后续方案或新批次由用户决定；本报告不是课程教学pass。
