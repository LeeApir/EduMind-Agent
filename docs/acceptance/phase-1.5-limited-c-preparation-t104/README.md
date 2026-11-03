# T104：有限 C 完整课程真实验证准备 r01

**状态：可审查的拟议包，不是执行授权。真实调用 0。** 本任务只完成执行准备；[ADR0050 A–D](../../ADR/0050-limited-c-course-feasibility.md)及[条款差异](CONTRACT-DIFF.md)待准确采纳，实际请求待绑定本包 manifest 的明确授权。T102 blocked，不追加修补，不迁移框架。

## 下一项核心成果

获得本批**未经助手补写的真实完整中文课程及独立教学评估**，连同失败/未运行及必要修复版本。不是更多通用执行器测试或Schema试错。当前没有新课程生成成功证据。T103 的模型/程序/助手来源逐项见 [所有权审计](T103-OWNERSHIP.md)。

最小流程：固定目标/有据前提＋共享代码/轨迹/事实/帧 → 真实模型完整教学文字 → 程序原样转义装配页面 → 独立评估助手手算和实际浏览器学习 → 允许时一次模型措辞修复及重评。不会把 T100/T103 的正文或逐步解释填进新课程，不把缺失文本自动生成“兜底”句子。

## 有限开发样例与准确输入

| 槽 | 初始/插入/分配掩码 | 目的和手算期望 |
| --- | --- | --- |
| C01 | [9]；[1,2]；[true,true] | 与T103同例，检验模型能否替代助手中文和步骤说明；最终t1→t0→i0→NULL，值[2,1,9]，terminated，失败0 |
| C02 | []；[-3,5]；[false,true] | 空链表、首尝试由掩码强制不分配、第二次假定实际malloc成功；第一次无t0且返回NULL，最终t1→NULL，值[5]，terminated，失败1 |

样例均为 `normal`，没有新增引擎能力。false 是合成不分配，而不是观察到一次真实 malloc 失败；true 允许调用 malloc，仍假定实际成功。没有环、未知链接、任意C或真实C执行。C01是公开旧开发例，不冒充新留出样本；两例不估计稳定率，不替代原双臂实验。不得看结果后挑新样例补分母。

- [candidate.json](candidate.json)：准确路由、规格和资源参数。
- [C01-input.json](C01-input.json)、[C02-input.json](C02-input.json)：目标、已知前提、完整代码/轨迹/事实和展示帧。
- [C01-request.json](C01-request.json)、[C02-request.json](C02-request.json)：准确规范化 HTTP body，无 Key、无 echo 预期答案夹具。
- [output-schema.json](output-schema.json)：模型返回段落/四题/逐帧说明/前提/总结/生命周期/失败范围。逐帧说明只能绑定准确 frame_id，程序不代写语义。
- [manifest.json](manifest.json)：以上输入、Prompt/Schema/引擎及实际入口/装配/条款文件摘要。现有引擎版本与模板版本不变，新增候选 `limited-c-full-course-r01`。

条件修复尚无实际回包，故**不存在可提前伪造的准确修复请求字节**。`prepare.body(slot, previous, issues)` 是冻结构造规则：带完整本批原输入、准确父稿和摘要、独立评估意见（最多8条、minor difficulty/misconception、原文精确引用与字段path，例如["questions","caller_head","explanation"]），同Schema完整输出。每次发送前保存真实构造的请求字节/摘要，仍受131072字节边界；超限即停，不改Schema/压缩正文/补发。评估若认为事实、答案、安全、严重问题或unknown，不能走普通措辞修复。

## 模型、路由、外发和预算

固定 `https://api.deepseek.com/responses`，model=`deepseek-flash`，reasoning=`none`，temperature=0.2，max_output_tokens=8000，stream=false，store=false。复用现有approve_target校验全部A/AAAA公网并连接固定IP，保留Host/SNI，DNS同步调用可能阻塞、无硬DNS时限。无厂商自动回退、无AIAPI审核调用、无工具、无联网搜索/文件上传；外发仅合成规格、教学目标/已知前提、共享代码/事实/轨迹和本批真实父稿/定位意见，无学生数据、Key、H、旧独立真值或T103修订正文。

2026-11-03仅阅读 [DeepSeek官方Responses接口](https://api-docs.deepseek.com/api/create-response/)及[公开价格](https://api-docs.deepseek.com/quick_start/pricing/)：官方列deepseek-flash、当前展示版本DeepSeek-V4.1-Flash-1017；这是可变化别名，不是不可变权重锁定。本包固定发送别名并保存实际回包model，不能证明上游真实权重。公开高峰cache-miss输入USD0.30/百万、输出USD1.20/百万；低峰输入0.15、输出0.60。不是账户实际费率或金额承诺。

| 边界 | 固定值与真实含义 |
| --- | --- |
| 总调用 | 最多4 HTTP：C01首版＋最多1修复、C02首版＋最多1修复；修复不用即失效，不转其他请求；无准入echo/模型审核/自动重试 |
| 在途与顺序 | 单前台请求，人工下一次；C01最终候选独立评估pass后才C02；任何协议/安全/事实/unknown异常即全批停止 |
| 请求/响应 | 每次请求≤131072字节；原始body采集≤2097152字节。响应超限只保留加密前缀并标partial/unknown，不标完整 |
| 本地输入预约 | 每次139264（请求最大字节131072＋8192余量），全批557056；只是保守本地占额，不是tokenizer或上游输入硬界 |
| 输出 | 每次请求max_output_tokens=8000，全批32000；已知服务自报超界即停，不能保证服务端遵守或无隐藏用量 |
| 时间 | 授权时明确首个starts_epoch及expires_epoch=starts+1800；发送前检查；HTTPX单项I/O timeout90秒，非请求总wall-clock/物理截止保证；不自动续窗 |
| 金额 | 拟另获本批C2：无可验证金额硬上限。按本地预约恰等实际token且全达输出上限的公开高峰算术为USD0.2055168；不是预测/上限，取消后可能继续计费、延迟账单、账户币种未知 |

## 实际入口与操作步骤（待授权，当前不得发送）

入口是包内 [execute_once.py](execute_once.py)。它使用既有 wire.validate 与受限引擎，绕开缺陷旧控制器；不是生产Gateway接线或T102完成。它**仍受检查后暂停再发送的已知风险影响**，详见差异表，不能把人工监督说成已修复停止竞态。

当前只运行以下无网络检查：

```sh
PYTHONPATH=backend:. backend/.venv/bin/python docs/acceptance/phase-1.5-limited-c-preparation-t104/prepare.py --check
env -i PATH=/usr/bin:/bin /Users/apir/Code/EduMind_Agent/backend/.venv/bin/python -I /Users/apir/Code/EduMind_Agent/docs/acceptance/phase-1.5-limited-c-preparation-t104/execute_once.py --inspect
PYTHONPATH=backend:. backend/.venv/bin/python -m pytest docs/acceptance/phase-1.5-limited-c-preparation-t104/test_preparation.py -q
```

未来准确批准后，在**本机当前用户可信目录**建立新的私有证据目录（0700），使用 `Fernet.generate_key()` 新建 `raw.key`（0600），只保存于证据目录，密钥不提交、不外发、不在工具输出打印。建议目录 `/Users/apir/.local/share/edumind/limited-c-r01`，不得覆盖已存在目录。执行记录包含本包 manifest SHA256、VERSION、`explicit_user_authorization=true`、`accept_contract_A_D_and_batch_C2=true`、1800秒的starts_epoch/expires_epoch。这个文件是授权的记录，**写true本身不是用户授权**；本次不创建它、不取得真实Key。

将记录保存为目录内 approval.json 后，实际单次命令形态为：

```sh
env -i PATH=/usr/bin:/bin /Users/apir/Code/EduMind_Agent/backend/.venv/bin/python -I /Users/apir/Code/EduMind_Agent/docs/acceptance/phase-1.5-limited-c-preparation-t104/execute_once.py --send C01 --vault /Users/apir/.local/share/edumind/limited-c-r01 --approval /Users/apir/.local/share/edumind/limited-c-r01/approval.json
```

此命令中的真实Key仅通过终端getpass输入；不能用环境变量代替，不读取项目.env，不把Key输入聊天。无后台子进程或重试，运行完就退出。独立评估后：pass时将准确候选原样复制为`C01-final.candidate.json`，意见登记`C01-evaluation.json`（candidate_digest、verdict、independent_evaluator，普通修复另加issues）；允许修复则对同槽再次启动，入口仅能生成一次repair。修复后重新评估准确新稿，最终pass才允许手工启动C02。禁止直接改候选或HTML内容。没有真实回包时不预填评估pass。

## 停止、原件保存与证据限制

- 先以x模式写唯一attempt/request，占用预算，再发送。响应body逐块Fernet加密/fsync到`slot-phase.raw.enc`，**在JSON或用量解析之前**；完整收到后解密回读比对，保存长度、摘要和HTTP状态，再解析。非法JSON也保留可解密原件。body不是完整HTTP wire，不保存Authorization/敏感响应头。当前Key的直接/JSON解码后回显会阻断明文候选导出；不是任意编码的通用DLP证明，原件始终加密。
- 完整课程候选、页面、模型usage与本地裁决都保存在私有目录；它们可以包含不合格内容，未经独立评估不冒充通过。目录不能提交到Git；敏感回显只留私有加密原件，安全摘要/失败清单进入交接，公开页面须先检查无敏感信息。
- Ctrl-C/终止当前进程是尽力停止；也可创建STOP文件供下一检查读取。停止后不再人工启动任何命令，即使在途返回正常也不推进。进程退出/网络异常/超时/断流/超限/未知均停止全批，不补发、自动恢复或把未使用额度另用。ACTIVE残留即unknown，不删除锁续跑。
- 截止/STOP若在请求完成后被发现，先保留原件再报late/unknown；已发数据无法撤回，不能保证Provider停止计费。90秒I/O超时无法保证slow stream的总时长，不设伪硬wall-clock；人工30分钟到期尽力终止。
- 本地原件没有独立锚或独立保管者，不抗所有者篡改、目录替换或所有副本共同回滚。`body_complete`只描述当时收齐的body；评估须重新解密比对request/body receipt，缺失任何预期文件即evidence_incomplete/unknown，不能凭本地摘要自证完整。人工在每次结束后保管一份完整目录的只读副本是额外留存，不冒充独立见证系统。
- 保留文件直到用户明确决定删除；丢key无法恢复，丢body或key不标成功。崩溃/被强杀可能留下未落盘片段，必须partial/unknown。没有原独立锚保障时不作崩溃恢复续跑。

## 检查与停止点

仅使用当前改动的合成HTTP、非法JSON/缺件/超限/错误帧/父链/有限调用和迟发反例，复用旧共享引擎的准确代码，避免再跑通用监督器矩阵。离线结果见 [CHECKS.md](CHECKS.md)，均不证明真实模型教学、真实网络行为或旧停止契约通过。

执行前须准确批准本包/ADR0050 A–D＋当批C2＋4HTTP/30分钟新窗口。未批准即停，不修T102或静默换入口。若获准，下一任务只交两个真实课程（或如实失败/未运行）、首版/修复版、独立逐段逐题逐步和实际浏览器教学评估；必要问题交用户决定，不追加试错。catalog_only、H封存、T038/T102 blocked、生产权限及旧课程签核不变。
