# T118 单次引用修订执行包

本包只有准备授权，实际 Provider 调用 0。父候选为 r02 封存首稿。独立评估确认第 5 段的结论正确，引用只覆盖接收返回值的路径。准确旧结果见 [T118 统一记录](../phase-1.5-head-empty-t118/RESULTS.md)。

[准确请求](request.json) 为唯一将发送的规范 JSON 字节，内容限第 5 段原文、C01 和两个相关事实，以及父稿、规划、材料和证据摘要。[返回 Schema](output.schema.json) 只接收一个数组字段 `paragraph_4_fact_ids`。合并要求值恰为 `["trace_step_05","head_evidence_v1.discard_return_comparison"]`，保留接收和忽略两个声明各自的证据。合并回读校验所有其他教学字段及完整 payload 逐项一致。范围、历史绑定及上限见 [scope.json](scope.json)。

拟继续使用 DeepSeek 官方 Responses `https://api.deepseek.com/responses` 与 `deepseek-flash`，strict JSON Schema，非流式，`store=false`，`reasoning.effort=none`，`temperature=0.2`。单次修订上限 4,000 输出 tokens，本地预约 139,264 输入 tokens，请求/响应限 128 KiB/2 MiB，I/O 超时 90 秒。费用金额未知，以上限制不构成费用硬上限；服务端实际留存未独立核实，本机原件无独立抗回滚，尽力停止后仍可能迟发或继续计费。新 600 秒窗口和本批 C2 需另行批准。

1. 授权后在现有 [本机开发实例](http://127.0.0.1:5210/) 确认实际新访客并保留会话。窗口启动时填写 [批准模板](approval.template.json) 的实际 manifest、访客和两个时刻。新 vault 为 `~/.local/share/edumind/head-empty-citation-revision-r01`，目录 0700，加密原件密钥 0600。批准记录在 vault 内，API Key 仅在本机终端隐藏提示输入。
2. 执行 `backend/.venv/bin/python -I scripts/head_course_fact_revision.py --profile citation --send` 一次。现有入口先保存加密原件和收据，再严格解析。协议、限额、范围或未知问题留证停止。成功合并也写 STOP 封住继续发送。请求、原件、差异与完整新候选留在本机新 vault。
3. 将候选和唯一差异交独立全文重评，沿用 r02 的 12 项审核。评审需逐项检查原有结论与证据、作用域、13 帧、四题和解析，并在 `final-review.json` 准确绑定新候选、父稿、规划依据及程序证据。通过后使用 `backend/.venv/bin/python -I scripts/head_course_fact_revision.py --profile citation --publish --owner <批准的实际访客 UUID>`，带现有 r02 本机数据库配置，进入新私有课程。
4. 在同一访客会话做实际浏览器验收。核对全文、13 帧状态及高亮、播放控制、四题错误和正确反馈、参考答案隔离、刷新后同版及反馈记录。交付课程入口、审核及版本绑定、实际使用量和结果记录。失败按门禁封存。

执行前核对 `PYTHONPATH=backend:. backend/.venv/bin/python -m scripts.prepare_head_course_citation_revision --check` 和 `backend/.venv/bin/python -I scripts/head_course_fact_revision.py --profile citation --inspect`。待批准的准入差异见 [ADR0058 补充提案](../../ADR/0058-t118-citation-revision-supplement.md)。
