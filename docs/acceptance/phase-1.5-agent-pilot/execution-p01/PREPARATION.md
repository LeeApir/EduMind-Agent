# T069 p01 零调用准备与交接

T071 已完成于 `393b9f1`，独立复审通过。完整离线 238 passed / 0 skipped；严格类型检查 9 个源文件、Ruff、工作流和 diff 检查通过。相关命令与独立证据见 [T071 交接](../t071/README.md)及 [独立复审](../t071/INDEPENDENT-REVIEW.md)。这些结果验证离线执行和证据门禁，不能替代真实接口或教学质量验证。

## 两次冻结

先冻结 candidate-manifest.json（2026-10-28T15:53:31+08:00）：`f70afd8089cee5a8fb511de0d95a5db1ef74368700fad377c49aaaac5a976241`，共 36 份源码、Prompt、依赖、契约、政策和回归材料，基线提交 393b9f1。独立助手在此后选取 e03 并手算参考；开发者只读取公开核定摘要和调度输入，不读取 truth、ratification 或推导正文。

最后的 manifest.json 再绑定候选冻结、独立公开摘要、材料摘要、准确政策/费率和本说明。批准登记不在冻结清单内，以便在用户准确批准后如实填写新窗口；真实入口仍要求该登记绑定 manifest 的准确摘要。登记目前未批准，不从旧记录继承权限。

## 当前边界

本批真实 Provider 请求 0，未加载 Key 或 .env；没有真实执行目录、预约、出站或费用。T069 仅恢复准备，尚未完成；T070 未领取。T038、catalog_only、旧批次和 H 封存状态保持。独立助手身份是 assistant，不冒充人工；共享文件系统的程序职责隔离不等于操作系统隔离或密码学认证。

## 准备验收结果

独立 e03 在 2026-10-28T16:13:34+08:00 核定，公开摘要 SHA256 `e66977dc7b212d03c1e8d97675e47bb9ff9a5ae79f9d4f184ac5891787279996`；身份为 pilot_independent_evaluator / assistant，未冒充人工。10 支持和 4 拒绝槽已绑定，参考真值及推导正文仍仅由独立助手持有。候选 36 文件无漂移。

实际执行 `backend/.venv/bin/python scripts/run_p15_agent_pilot.py --check` 返回 0，materials=independent_e03_ratified，real_requests=0。对 pending 批准实际调用 main 的 --start、--step 均返回 2 / EXACT_NEW_EXECUTION_APPROVAL_REQUIRED；插桩将 load_keys 与 Journal.start 设为必抛错，均未触达，真实输出目录不存在。上述负测验证的是拒绝路径，未执行真实步骤。`python3 scripts/check_catalog_workflow.py` 和 `git diff --check` 通过。没有新增教学或传输实现，完整 238 项验证沿用 T071 已完成结果。

T069 准备就绪后标 blocked 等待准确真实执行批准，不创建 Task-Completed；T070 仍 todo。下一步仅在用户批准 ADR0042 A—C、合成外发、90 HTTP、新 3 小时窗口及本批 token/金额无上限例外后，如实填写 execution-approval.json，再登记独立新批次；逐槽交独立助手复核，结束后做只读证据验收和 T070。批准前不加载 Key、不调用或重启旧批次。
