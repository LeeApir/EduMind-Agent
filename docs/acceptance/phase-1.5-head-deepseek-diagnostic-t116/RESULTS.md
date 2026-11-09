# T116 · T115 封存正文离线诊断

**派生稿程序校验通过，独立全文教学评估结论为停止。** 评估发现两处事实错误和两道答案不唯一的题目，另记录四项非阻断问题。导入恢复以全文通过为前提，当前未满足。[独立全文评估](ASSESSMENT.md) · [准确评估记录](teaching-review.json)

T115 原始正文仍触发 `HEAD_QUESTION_SCENARIO`。本次从本机加密封存回读原响应，重验请求、收据、冻结包、独立规划和程序材料绑定。诊断规则只接受完整一致的情境代码，或仅缺末尾一个 LF 的情境代码。它从题干内首个 `#include <stdlib.h>` 比对至题干末尾，逐个字符核对。四道题各只补了一个 `0a` 字节。逆转这四个字节后，结构化输出的规范字节与原输出一致。代码内部、教学文字、解释、程序材料和参考答案均保持原值。[T115 封存记录](../phase-1.5-head-deepseek-live-r01/RESULTS.md) · [四处变更及摘要](diagnosis.json)

用原校验器重跑 Schema、字节容量、事实引用、教学证据绑定、帧编号与题目代码。离线装配得到 13 帧、13 个播放动作和四题原答案。程序校验通过。窄边界检查覆盖精确一致及只少尾 LF 两种正例，拒绝内部缩进变化、CRLF、尾空格、额外 LF、缺花括号、代码值变化和重复代码头七种负例。两次派生输出逐字节一致。[诊断脚本](../../../scripts/diagnose_head_course_t115.py)

此次 Provider 请求为 0，诊断输入只写入本机私有临时目录。T115 原操作保持停止，本次应用写入为 0。

在拥有原封存的本机运行以下命令。

```sh
PYTHONPATH=backend:. backend/.venv/bin/python -m scripts.diagnose_head_course_t115 \
  --output /tmp/edumind-t115-diagnostic/review-copy.json
PYTHONPATH=backend:. backend/.venv/bin/python -m pytest -q scripts/tests/test_diagnose_head_course_t115.py
```

诊断输入包含题目答案，仅供私下审核。
