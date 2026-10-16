# v4.4小型审核诊断包r01（零调用）

保留原输入、Prompt、Schema、材料和判据，使用deepseek-flash/low/8192总输出（含思考）/60秒。独立7槽，不复用任何旧账本/余额/批准；不改生产默认，T040保持blocked。

顺序：plan-only-gap → assessment-gap → fact-contradiction → reachable-safety → gap-and-safety → trace-complete → trace-distributed。前五条优先验证未解决缺陷，后两条同配置检查误报。旧正例作为历史参照，不替代本包对照；这是人工构造的诊断集，不是独立留出集。

纯教学缺口必须needs_human且具体说明，findings为空，不能编造缺调用示例fact；过程测量缺失不能误称没有过程教学。事实矛盾应指出18与实际16；安全应指出长度3却读取a[4]；混合仍保留major/severe code_safety及reject，教学不足不能覆盖严重错误。正确对照必须pass且无findings/unchecked/unresolved。每条完整性与语义另核；分类命中不等于具体错误检出。

准确保守预算由proposal/token-cost-proof冻结：每槽最多一次，7请求，无重试/修正/回退/额外探测。逐条运行并停待人工核对；前一条必须以具体receipt摘要和真实用户确认绑定continue后才能运行下一条。任何技术失败、结构门禁失败或语义判据不符立即停止，不重试、不自动换模型或抬上限。若人工识别出结构门禁未捕获的误报，不写continue，不运行下一槽。本包无自动批量执行命令。

未创建真实run-approval、labels-human、账本，不读取Key、不联网调用Provider。获得整包准确预算和材料判据批准后，首条只发plan-only-gap。此后保留逐条实际结果人工门禁，不预签结果。

执行入口：`backend/.venv/bin/python scripts/run_review_suite.py --run-one`（无批准时发送前拒绝）。准备：`backend/.venv/bin/python scripts/prepare_review_suite.py --write`。旧冻结文件及运行保持停止。
