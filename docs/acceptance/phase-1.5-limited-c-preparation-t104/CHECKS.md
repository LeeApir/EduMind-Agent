# T104 离线检查记录

日期：2026-11-03。执行者：Codex。本轮仅准备，不生成真实课程。没有读取真实 API Key、启动真实 Provider 请求或创建真实授权文件/证据库。

## 最终结果

- `PYTHONPATH=backend:. backend/.venv/bin/python docs/acceptance/phase-1.5-limited-c-preparation-t104/prepare.py --check`：准确输入/候选/Schema/源码与运行时摘要可重建。
- `env -i PATH=/usr/bin:/bin /Users/apir/Code/EduMind_Agent/backend/.venv/bin/python -I /Users/apir/Code/EduMind_Agent/docs/acceptance/phase-1.5-limited-c-preparation-t104/execute_once.py --inspect`：proposed_not_authorized，live_calls=0；仅检查，不解析DNS或读真实Key。
- `PYTHONPATH=backend:. backend/.venv/bin/python -m pytest docs/acceptance/phase-1.5-limited-c-preparation-t104/test_preparation.py -q`：**10 passed**。检查固定输入和独立手算期望；缺失/错帧拒绝；非法JSON加密原件先于解析；准确父稿/请求/一次修复且第三次拒绝；缺原件阻止后续；C02等C01独立评估；超限加密前缀和截断检测；过期/STOP本地检查；明确复现迟发风险；脚本文本安全转义。Mock传输核对固定公网连接IP、Host/SNI，未做真实TLS/网络验证。
- `PYTHONPATH=backend:. backend/.venv/bin/python docs/acceptance/phase-1.5-limited-c-preparation-t104/check_player.py`：实际Chromium两份合成材料，C01全部13帧/C02全部10帧、同帧模型文字位置/高亮、独立最终链、播放暂停前后重置、四题错/对/解析、键盘及390px移动布局通过；页面异常0、HTTP请求0。见 [browser-check.json](browser-check.json)。浏览器须通过工具审批在沙箱外启动，未放宽页面CSP。
- `backend/.venv/bin/ruff check docs/acceptance/phase-1.5-limited-c-preparation-t104/*.py`、`python3 scripts/check_catalog_workflow.py`、`git diff --check`：通过。
- 文档相对链接、manifest摘要、旧103个Task对象不变、process日志只追加以及T102 blocked：通过；用户三处无关改动保持。新执行器不修改历史原件。依赖锁文件与当前runtime版本一致。

初始实现曾因按运行时已加载模块构造manifest导致后续调用的摘要不稳定，已改为源码导入图与锁文件的确定性摘要；最终完整检查通过。Ruff格式问题已修正，不削弱断言或修改旧测试。浏览器材料始终是标注“合成离线夹具”的临时产物，没有将其提交为真实模型课程。

## 故意保留的失败反例

`test_same_entry_discloses_pause_then_late_send` 在真实入口的request登记后通过合成检查点模拟暂停，让时间超过期限且创建STOP，再恢复入口。**仍有一次Mock发送**，随后保留body并停止/unknown，不导出候选。这个测试的通过表示成功复现风险，不是停止契约通过；不发真实请求，也不证明物理网络时序。

本包仅适用于用户准确接受 ADR0050 较弱单请求语义后的探索。若坚持 T102 原来停止返回后不得新建/首次派发及独立锚保障，当前入口仍不合格，本轮不追加通用修复。

## 尚未获得的证据

真实新Schema支持、真实课程中文/教学质量、上游上下文或模型权重身份、真实账单、独立学生学习效果均未验证。没有模型审核pass、真实生成成功或正式评分分子。本轮无独立准备包审查记录；执行后的独立教学评估仍是下一任务必须交付项。
