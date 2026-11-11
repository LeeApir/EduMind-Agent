# T127 零调用准备验收

冻结清单 SHA-256 为 `1ebc6997d556c8d0a5a3426137d30d75650d7ffc9813441ecd6fd4b7b3070df8`。Provider 请求 0，未创建正式试验窗口、原件目录或课程。模拟实际模式用临时原件目录和隔离测试库，只在测试内部注入 MockTransport。

| 检查 | 实际结果 |
| --- | --- |
| 冻结请求 | 四主题 `inspect --live-reuse` 给出同一清单摘要，主题额度合计 9。对照三份固定请求和两份头插模板。隔离库实测头插仅绑定实际 UUID 与同操作已审规划。 |
| 精确授权与窗口 | 拒绝错误清单、未接受 C2、旧模式、错配额度、重复登记、窗口过期、错批次前序准入、显式停止及离线夹具混用。CLI 拒绝未批准模板、`--mock-response` 及与 `--offline-vault` 同用，未创建真实原件目录。 |
| 修订与私有读取 | MockTransport 模拟一次头插规划、一次首稿和一次修订。拒绝未批准、错批、错父、错审核及越界路径，原首稿响应和首次审核保留。只改 `failure_scope`，用准确全文重评准入后，实际私有 API 读取 v2 并核对父子稿、规划来源及答案隔离。栈首稿直接准入。 |
| 停止与封存 | 队列 Mock 响应 Schema 失败，原始响应、回执及失败写入临时原件目录，整批 HALT。二分准备和继续准入均被拒绝。整段测试有 5 个 Mock 请求。 |
| 首轮失败与复验 | 首轮头插修订准入写入后，私有课程 API 返回 503，原因是原读取契约只接受旧批次标签。增加四个准确的 T127 来源后复验，真实批次标签和离线夹具标签互换均被拒。 |

使用既有 `scripts.run_catalog_db_tests.test_environment` 为 `edumind_catalog_p15_t127_reuse_test` 注入本机专用 PostgreSQL 连接。实测 `alembic upgrade head` 及 `alembic current` 到 `0050_head_goal_generation`。

```sh
PYTHONPATH=backend:. backend/.venv/bin/python -c '
import pytest
import sys
from scripts.head_course_goal import raw_io_audit
sys.addaudithook(raw_io_audit)
sys.exit(pytest.main(sys.argv[1:]))
' -q backend/tests/test_shared_course_trial_live.py --tb=short
python3 scripts/check_catalog_workflow.py
git diff --check
```

定向 pytest **3 passed，0 skipped**。保留测试装载和 Starlette 既有依赖警告。定向 Ruff、账本依赖、Git 差异检查通过。真实课程和浏览器学习验收待本批准确授权后执行。

[T126 修订记录字段](../phase-1.5-shared-revision-t126/README.md) · [栈独立预期](../phase-1.5-stack-lifo-t119/independent-reference.json) · [队列独立预期](../phase-1.5-queue-fifo-t121/independent-reference.json) · [二分查找独立预期](../phase-1.5-binary-search-t122/independent-reference.json)
