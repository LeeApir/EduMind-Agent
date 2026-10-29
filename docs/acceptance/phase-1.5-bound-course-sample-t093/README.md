# 头插法离线课程样例

打开 [可操作的课程页面](course.html)。讲解为手写开发材料，代码、11 个状态、31 个动作及四类观察答案由现有头插引擎派生；固定规格为初始 `[9]`、插入 `[1,2]`、`normal`、两次抽象成功。完整数据见 [sample.json](sample.json)，页面中目标→内容→证据表、逐动作状态和代码高亮均可逐项检查。

此样例不是模型生成、独立教学质量验收或正式课程。引擎不执行 C；`allocation_success=true` 仅允许尝试 `malloc`，实际分配可能失败，因此状态明确以成功为假设。B 模型独立求解、真实模型教学质量、完整角色接口兼容及 T038 均没有因此通过。页面播放器是此离线样例专用的动作重放，不代表现有产品播放器已接入此协议。

[生成器](../../../scripts/isolated_diagnostics/generate_p15_bound_sample.py)基于引擎重建 `sample.json` 与自包含 HTML。SHA-256：`course.html` 为 `943935ac3d9fb568a784eb675bd3dfb38f4d5bf7e8b189bab930e70908fd066e`；`sample.json` 为 `71ea05685151ba75e4d71e2eb61a8afaa072ba145f5ff6928c645ac9c2fea262`。播放器读取样例的完整动作序列，按顺序重放 `show_state`、`highlight_code`、`advance_step`；不会执行代码或连接外部服务。

## 验证

- `PYTHONPATH=backend:. backend/.venv/bin/python docs/acceptance/phase-1.5-bound-course-sample-t093/check_sample.py`：引擎重新生成与文件逐字节核对，手写预期四答案一致，状态摘要逐项核验；Chromium 实际检查全部 31 个动作的状态与代码高亮、前进/后退、自动播放、暂停、完整播放与重置，四题展开可见，页面 JS 错误与外部请求为 0。11 状态、31 动作、4 题通过。全页截图 `/private/tmp/edumind-p15-bound-sample-t093.png`。
- `backend/.venv/bin/ruff check scripts/isolated_diagnostics/generate_p15_bound_sample.py docs/acceptance/phase-1.5-bound-course-sample-t093/check_sample.py`：通过。
- `python3 scripts/check_catalog_workflow.py` 与 `git diff --check`：通过。

首次沙箱内启动 Chromium 因本机 Mach 端口权限失败；随后在沙箱外运行同一仅打开本地文件的测试，通过。没有 Provider 调用。课程解释仍需用户评估；后续真实链路须完成新角色接口准入和准确执行授权。
