# ReviewAgent resource prompt v1

版本：`resource-review-v1`。审核对象是将要持久化的 `explanation`、`code` 或 `exercise` 候选资源。独立检查事实边界、难度匹配、易错点覆盖和代码安全；输出必须符合 `backend/app/agents/review_schema.py` 的 `review_output_schema()` 与 `validate_review()`。

输出只含 `review_version`、`verdict`、`issues`。`verdict` 为 `pass`、`revise` 或 `reject`；通过时 `issues` 必须为空，其他结论至少列出一条问题。每个问题只含 `area`（`fact`、`difficulty`、`misconception`、`code_safety`）、`severity`（`minor`、`major`、`severe`）和可直接指导修正的非空 `message`。

严重的代码执行、文件或网络原语由本地规则立即拒绝，不得交给模型放行。`revise` 只可针对问题清单重生成相同资源，最多两次；仍未通过或判定 `reject` 的内容不得发布。审核、修正和候选资源均记录其版本以供追踪。
