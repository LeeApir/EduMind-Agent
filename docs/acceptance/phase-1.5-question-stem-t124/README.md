# T124 四主题题干格式约定

空链表头插、栈、队列和二分查找的正文首稿可选择 `course-question-stem-v2`。该版本在实际请求的 system 消息中加入同一段格式约定，落实 [T123 M03](../phase-1.5-t038-gap-review-t123/GAPS.md#二最小实现缺口本任务不实施)。

| 项目 | 提示词要求 | 本地检查 |
| --- | --- | --- |
| 单行 | 写一行非空白的简体中文题干。JSON 解码后的字符串也不得含换行。 | `strip()` 判断非空白，`splitlines()` 判断单行，末尾换行和 Unicode 行分隔符也会拒绝。 |
| 代码回抄 | 引用下方代码，由程序追加准确的 C 情境。题干不回抄情境代码或写 C 语句。 | 现有词法检查拒绝 `#include`、多行和下列字符。题干是否准确引用情境仍由教学审核判断。 |
| 围栏 | 不写反引号或波浪号代码围栏。 | 拒绝字面标记 `` ``` `` 和 `~~~`。 |
| 花括号 | 不写 ASCII `{` 或 `}`。JSON 整数数组使用方括号。 | 拒绝任一 ASCII 花括号，方括号通过格式检查。 |
| 分号 | 不写 ASCII `;`。 | 拒绝 ASCII 分号。 |

沿用已发送过的严格 JSON Schema。题干和解析仍为必填、长度受限的字符串，空链表头插上限为 4,000 字符，其余三个主题为 1,200 字符。非空白、单行及上述字面标记继续由本地代码检查。事实引用、情境及答案准确性和教学审核沿用原契约。校验只接受或拒绝模型原文。

新包构造首稿时，空链表头插在 `head_course_materials.body(payload, stem_prompt_version=PROMPT_VERSION)` 选择新版，其余主题在各自的 `request(stem_prompt_version=PROMPT_VERSION)` 选择。`PROMPT_VERSION` 来自 `course_question_stem`，版本同时写入 system 消息，随请求字节参与现有摘要绑定。省略参数时仍能生成旧请求的准确字节。非空链表头插沿用它原有的题内代码契约。历史冻结包按各自的冻结提交复核源码摘要。

定向验证从仓库根运行：

```sh
PYTHONPATH=backend:. backend/.venv/bin/python -m pytest -q \
  backend/tests/test_course_question_stem.py \
  backend/tests/test_head_course_empty.py::test_exact_new_requests_and_closed_content \
  backend/tests/test_stack_course_trial.py::test_model_cannot_change_materials_or_reference_unknown \
  backend/tests/test_queue_course_trial.py::test_mechanical_validation_rejects_non_queue_fact_and_wrong_frame \
  backend/tests/test_binary_search_course_trial.py::test_teaching_contract_requires_exact_frames_and_fact_ids
```

18 项通过。检查读取实际构造并序列化的请求，对照完整 Schema 和原材料，并在四主题校验入口核对正反例。三个固定主题的旧请求和两个空链表头插的旧正文模板逐字节匹配冻结文件。定向 Ruff、任务工作流和 Git 差异检查通过。Provider 调用 0。下一批采用新版时，在新执行包中显式选版并冻结请求。
