# 头插教学实验候选冻结 r01

冻结基线 `0cdc710` 的新版教学规则、B/C Mock 流程、精简审核适配、本地检验器、原 Schema 和受限引擎，详见 [manifest.json](manifest.json)。冻结内容是**隔离实验候选**，不是可运行的真实批次，也不证明模型教学、Responses 审核链或正式验收已通过。候选执行证据在 [T100](../phase-1.5-teaching-revision-t100/README.md)。

[prompt-snapshot.json](prompt-snapshot.json) 是全部七阶段实际 system 指令的快照；审查 B/C 共用教学要求，B 不获得 C 的事实/答案。`policy.json` 记录既定样本分母和 T097 审核限制；这只是候选开发配置，不是新 HTTP、时间或费用预算授权。旧 T095/T096 原件保留；助手中文修订草稿是开发示例，不是新模型样本或独立真值。

现有 `p15_teaching_pilot.Pilot` 是 MockTransport 实现；`p15_teaching_revision.observe_review` 可离线检验 B/C Responses 与绑定，但尚未在真实出站控制器中接线。独立样本选取应发生在本候选完成提交后，由独立评估者单独选参数、手算并核定；不使用旧 e03、开发例或 H 作为真值，不向待测模型外发独立真值。

执行 `PYTHONPATH=backend:. backend/.venv/bin/python docs/acceptance/phase-1.5-teaching-frozen-r01/check_freeze.py` 核对冻结文件、运行时、逐阶段 prompt 和本地示例/旧原件；不会读取 Key 或联网。真实审核准入与完整小实验需另行准备准确闭包、预算和授权。
