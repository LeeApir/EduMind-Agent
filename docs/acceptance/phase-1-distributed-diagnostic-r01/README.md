# 单例诊断冻结：原分散覆盖low

仅选择旧配置对照r01失败的`trace-distributed:candidate`。本包的完整case、原始目标快照、学生材料、锚点和wire逐字等于原冻结包；保持v4.4输入/Prompt/JSON Schema、`deepseek-flash`、`low`、温度字段0、**2048总输出token（含思考）**、60秒截止不变。不新造示例、不加入错误日志或示范答案到请求。

相同的是旧冻结请求；旧失败的实际网络请求摘要/响应/用量仍未知，本包不伪造其恢复。旧r01、r05及所有更早运行继续保持原halt与成绩，本包不改生产默认。

## 唯一样本与判据

原目标：用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。

讲解简短，代码`key_steps`给total=2/7/16及i=3退出，题目/解析要求中间状态和退出知识。原判据保持：`pass`，五检查ID齐全，无finding/unchecked/unresolved或附带误报；无需在讲解重复所有跨资源支持。路由匹配不是语义自动签核，实际材料和回答仍需复核。

原wire：42247字节，SHA256 `4bdf42a82166858698e18ff88e922b0876653b94b2cec02e0afa65735c3e0ea3`。输入字节数不是token估算。完整材料见`human-review.md`，实际wire十六进制见`cases.json`，来源及摘要见`proposal.json`。

## 最多一次并停止

独立入口`run_distributed_diagnostic.py`创建新诊断执行器的独立模块实例，硬绑定单槽、1次上限、新运行ID和私有目录。它不修改原14槽入口的全局状态。输入body不变，变化只有本地诊断留存与单例预算门禁。

- 一次预留最多一次传输尝试，无重试、修正、fallback、并发或额外兼容探针。
- 成功后单槽耗尽，重复运行即使补签continue也不得发送第二次；不自动进入其他样本或旧剩余槽。
- 任何失败持久停止；未知用量保持null，预留不退款。记录允许的细分原因/计数/状态/完整性摘要，诊断写失败也不能允许重试。
- 成功或失败后均保存实际证据并停止；本次不开放动态模式、不给T040正式通过分数。

默认新目录`local-materials/phase-1-distributed-diagnostic-r01`；不会使用任何旧账本。

预算内核旧Schema要求`corrections_per_resource=2`固定字段，保留其兼容值不代表本包有修正调用预算；本包唯一槽只允许`probe`一次，整个运行上限1，没有correction stage或第二槽。

## 独立准确预算

**最多1次；保守预留上限2.198030元；总输出上限2048token。** 输入预留上界为1048576+42247=1090823token（整窗再加字节作为冗余，绝非预计输入token数）。按高峰未命中输入2元/百万、输出8元/百万计算：`2×1090823 + 8×2048 = 2198030`微元。

这是应用预算预留，不是预计账单或Provider账户硬限额；实际费用、缓存/时段以账单为准。价格、上下文和包含思考的输出上限按2026-10-16官方索引文本核对，执行日须再核，不一致或不可验证则停止。出处：[价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)、[Responses参数](https://api-docs.deepseek.com/api/create-response/)。

当前`requests_authorized=0`、`fees_authorized=0`，不创建`run-approval.json`或`labels-human.json`。用户本次授权冻结单例，不等于准确新费用与包绑定的发送批准。原14次批准/余额不继承。本包有效期截至2026-10-18 23:59:59（北京时间），日期及条款门禁保持。

## 可执行接口

零调用准备：`backend/.venv/bin/python scripts/prepare_distributed_diagnostic.py --write`。准备器仅lstat凭据文件元数据，不读取key，拒绝覆盖不同冻结包。

唯一真实入口：`backend/.venv/bin/python scripts/run_distributed_diagnostic.py --run-one`。在独立准确批准和标签绑定前，应退出2，Key/DNS/新账本均0。可在无批准下构造只读预算结构预览；它不登记批准、创建账本或预留。

冻结闭包绑定新入口、单例准备器、新诊断执行器、安全诊断模块、旧源基线、原始case及实际wire、价格证明和判据。离线Mock只验证执行与留存，不证明本次真实兼容或质量，也不能解释旧失败根因。
