# Qwen 修复版剩余11例续测包：零调用准备

用户要求继续原冻结包，经明确澄清确认compatibility-01实际结果的完整性、语义及引用通过，按源码表达式对比理解instead of16，原“no particular return guaranteed”保留。绑定原receipt0714575a1e6eaa38373c9c3da28690e5dfaa77c4fd9ae43b834cc21130a2f885及独立human确认，不改原回答/原待人工意见；这不是重跑首例或恢复旧预算。

本包只准备后续测试，无新的真实调用批准或私有账本。原qwen-review-execution-r01继续停止，已用完的compatibility-r01也不续费。所有旧历史账本/失败/费用保持，生成仍deepseek-flash，生产catalog_only，T040 blocked。

## 材料与请求

保持原4+8判据和材料，首条实际已确认结果作为带来源的筛选证据导入，不计新请求。新11条顺序：事实矛盾、教学缺口+越界、完整正确对照；之后原8条线性查找/顺序栈各正确、事实、安全、混合缺陷。迁移材料为事先冻结作者材料，未独立盲评，不称泛化保证。

所有消息/目标/Prompt/Schema业务契约/v4.5/政策和学生内容沿用原材料；仅传输Schema使用已实测成功的qwen-strict-20261017-v1投影（去uniqueItems、裁剪未引用defs），本地保留完整Schema校验。模型qwen3.8-max-0902非思考/strict json_schema/8192请求，实际输出预算8202，60秒外层截止+最多10秒本地清理；新有界错误解码仍raw64KiB/decoded128KiB。不改默认生成模型。

## 独立预算与签核

待批准新准确最多11次/146.144880元（3条筛选39.841788元，8条迁移106.303092元）。按北京12/36元每百万全价、输入窗口加wire字节保守预留，不假定免费/缓存，非预计账单。不使用旧停止余额；无重试/纠错/探测/回退/换候选，任何技术/用量/Schema/语义或引用失败首败停止，余槽不复用。

批准后仍每次只一个样本；下一条前必须绑定上一真实receipt的Lee确认，完整性/全部断言/全部引用均true且issues空。新第3条后，须将导入首条+新3条四份准确receipt合并screen-pass人工admit_generalization，才可进入迁移。最后一条也须签核。--check-complete最多报告DIAGNOSTIC_SIGNED_PENDING_T040_ADMISSION，不自动发T040或开放dynamic。歧义按实际证据交人工，不通过预算批准预签结果。

新执行器先验证批准/来源/导入确认/当日价格条款，再建私有状态和预留，后取唯一inactive Qwen组/端点摘要/配置元数据及隔离PG临时连接；真实Key不持久化，单send/准确wire/Host/SNI/公网IP、撤销检查保持。出错完整review若已得到也保留。eliminate可单独持久语义停止，不改原receipt。

## 复现

零调用生成：backend/.venv/bin/python scripts/prepare_qwen_continuation.py --write。
离线验证：backend/.venv/bin/python -m pytest scripts/tests/test_qwen_continuation.py -q（真实ConnectionOperation/MockHTTP的11条需专用测试PG环境，无云调用）。
真实单槽入口（当前未批准应拒绝）：backend/.venv/bin/python scripts/run_qwen_continuation.py --run-one。完整签核只读检查：同入口--check-complete。批准文件需绑定本proposal摘要和准确11次/146.144880元，执行当日条款另复核。
