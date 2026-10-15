# T040 逐断言审核检查 r08

状态：审核指令 v6 与离线回归完成，新增真实请求 0；2 次 / CNY 0.18 独立预算待批准。

r07 已检出队列计数错误，fact 分类正确，但没有指出空满条件错误，未满足事前冻结的
两项具体检出要求。部分检出与漏项分别保留；原 CONCRETE_DEFECT_MISSED 台账停止不恢复。
核查 ReviewAgent、schema、私有保留回答后，未发现代码截断为单条 issue，实际模型仅返回一条。
现有证据不能唯一解释模型为何遗漏第二条。

修复候选：审核 Prompt v6 增加通用逐断言覆盖要求：

- 独立核对候选实际写出的定量断言、公式、状态谓词及操作规则，结合表示方式和实现检查正常、边界及失败状态。
- 找到一处错误后继续核对其他断言；所有独立具体缺陷都要定位并给条件或反例，不能只报告代表性一条。
- 共享原因不代表是同一错误；同一错误不重复报告。不凭空要求完整课程主题或固定 issue 数量。
- 覆盖过程内部完成，只返回原 schema；正确资源仍应 pass，保留 findings-only 范围和独立修正/完整复审。

没有注入队列答案、历史标签、案例 ID、固定 verdict 或额外模型请求，没有扩展公开 API/schema。
指令只能表达要求，无法在本地保证模型已逐项检查。Mock 多问题修正/复审测试不作为质量分数。
原 schema-v3、分类、两轮修正上限、安全/上下文规则与正式阈值保持。

r08 与冻结 r07 相比只有 system 审核指令 v5→v6；继续同模型 deepseek-flash、Responses、
low、8192 总输出（含推理）、120 秒总期限/60 秒 HTTP read。候选、参考上下文、schema、
序列、评分维度不变，不读取正式新样本调参，不切生产 none/catalog_only。

两次逐条执行：

1. 原 queue:explanation:1：具体检出回绕计数及空满条件两项错误，fact 分类；反例真实，不夹带修复方案。
2. 原 correct-list-concept：pass 且 issues=[]。

检出、分类、审核职责/回答事实、schema/完成/模型/用量分别记录，正确检出的部分不因其他失败改记漏检。
任一失败停止，串行、无重试/回退/修正。修正质量 NOT_RUN。
成功也不替代完整四组诊断、人工事实签核或正式 T040/T041，不能由两例推断可靠性或因果。

预算：2 次 / CNY 0.18。保守预留 0.092476 + 0.085366 = CNY 0.177842，向上取整到分；
按完整 UTF-8 wire 字节加 1024 输入 Token、8192 总输出上界，以及峰值输入未命中 2 元/M、输出 8 元/M。
不依赖缓存/时段折扣，实际账单未知，无旧预算转入。官方人民币价格直读超时，已通过官方搜索缓存核对。
[官方定价](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)。

[proposal.json](proposal.json) 与 [requests.json](requests.json) 固定源文件及锁文件、原标签、确切两条正文和维度。
批准后再冻结执行来源与独立台账。保留白名单完成状态/未完成原因与输出项计数，不存推理正文或供应商错误正文。

```sh
backend/.venv/bin/python scripts/t040_reasoning_check.py --round r08 --check-proposal
# 仅在本轮获得确切预算批准并保存批准记录后：
backend/.venv/bin/python scripts/t040_reasoning_check.py --round r08 --freeze
backend/.venv/bin/python scripts/t040_reasoning_check.py --round r08 --run-one
```

验证：148 项离线测试、Ruff、mypy 166 源文件、批准/历史冻结/任务校验通过。
新增多条独立问题完整传入一次修正、修正后整个候选重新审核的回归；
r08 与 r07 除生产 system 外完全一致、原评分维度不变的测试通过。
旧 r07 wire 对比测试改为直接核对已冻结 r07/r06 文件，继续严格断言两者只有 effort 变化，
不会用当前 v6 重生成的 prompt 假冒历史 v5 请求；旧冻结文件不改。
r07 的 186 个来源按 3c5936c 归档核验，只读 SQLite 仍 1 条且停止。
