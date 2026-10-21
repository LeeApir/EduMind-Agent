# v4.9 / DeepSeek生成＋Luna审核：新诊断候选

**零调用准备包；尚无独立人工标签签核、12次准确请求批准或真实诊断成绩。** T040保持blocked，默认catalog_only、旧失败/淘汰候选/账本保持。用户报告的单次接通单列为self-reported，不计本包Schema/质量分子。

## 1. 唯一候选与实际路由

| 环节 | 服务/精确模型 | 推理/输出/超时 | 请求路径 |
| --- | --- | --- | --- |
| 生成配置 | DeepSeek / deepseek-flash | none；计划2048、每场景4096；每次60秒，正式单元仍180秒/20 formal调用原限 | https://api.deepseek.com/responses |
| 审核候选 | 第三方www.cbbb.fun / gpt-6-luna | **low**；8192总输出（含推理），返回用量超过8192或缺失即停；每次60秒 | https://www.cbbb.fun/v1/responses |

来源是用户2026-10-19更新后的.env：active Luna、inactive DeepSeek；审核low按实际env保留，未采用此前medium建议。候选只一个、轮次只一轮，不加Qwen对照或自动回退。

**只在env填模型/档位不足以完成分流。** 生产默认factory本身不会按这一个.env同时分出两路，且不会自动消费EDUMIND_PROVIDER_REVIEW_REASONING_EFFORT。本包使用独立显式路由器：精确审核system指令→Luna adapter(low/8192)，已批准的生成agent调用→DeepSeek adapter(none/2048或4096)。生产业务源码/环境文件未改，不声称生产已切成双Provider。

离线请求由实际generate_shared_plan、PlannedScenes.generate、review_once和Responses适配器构造，使用MockTransport接住真实序列化字节。generation-route-capture.json含4次生成；resource-route-capture.json含3次资源审核；requests.json含12次整单元审核。Host/SNI/path/model/reasoning/schema/输出参数与wire摘要核对，审核请求policy绑定v4.9/inputv4/scopev6/unit六ID。适配器类历史名称为DeepSeekResponsesAdapter；该名称不等于请求发送给DeepSeek，捕获Luna实际Host/SNI均为www.cbbb.fun。

HTTP连接IP8.8.8.8是离线替身，**不是该渠道真实IP**；无DNS或真实HTTP模型调用，脚本化pass仅帮助协议走完，不是质量标签或成绩。真实单槽使用ProviderTargetGuard云端公共IP校验，单次DNS后固定选定IP、Host/SNI/HTTPS/path，发送前核对原请求逐字节与授权。不接受重定向、代理、重试、回退或其他model。

服务端继续完整业务Schema和动态scope/检查ID/锚点Schema验证，本包不套Qwen投影、不移除uniqueItems。线上请求text.format.type=json_schema，未声明strict:true，因此不声称第三方提供strict保证；完整性最终由本地验证。官方Luna说明只证明官方产品能力，不证明第三方的真实后端身份、参数支持或计费。真实首条需验证此完整契约；若HTTP400/截断/Schema/模型/用量失败，本轮停止，不现场调参续发。

## 2. 完整材料、标签和新材料

[材料核对册](materials-review.md)逐条展示原始目标、授权教学分段、计划、三个完整学生场景、动作、预期理由与边界。[cases.json](cases.json)保存不可变业务快照；[proposed-labels.json](proposed-labels.json)保存本地预期，不进入模型wire。

12例=8筛选＋4新材料。新材料在当前v4.9源码冻结后创作，未用于此前Prompt修复；对准备者可见，不能称为统计盲测。所有12例画像未知，用于检查“不因未知画像本身拦截”；先修例明确recommended授权，只要求指针小节，不能把原链表目标冒充已完成。

标签目前为Codex起草＋独立语义核对**pending**。材料作者/Mock回复/模型自己不能签为Lee；没有独立人工逐条确认不能启动。机械真值可独立重算：3+8+4=15，栈top0→1→2→1返回9；越界不推断固定数值。没有运行新C代码，本包不扩展ADR0019的固定两样本执行权限。

| 顺序 | ID | 预期 | 关键证据/必检 |
| --- | --- | --- | --- |
| 1 | screen-complete | pass | 显式状态3/11/15与i=3退出、过程题，全项清洁通过 |
| 2 | screen-distributed | pass | 轨迹在key_steps和练习解析中，不要求讲解重复 |
| 3 | screen-teaching-gap | needs_human | 正确循环仅可推导，学生内容没有明确关键状态/退出教学；题目只测算术/长度 |
| 4 | screen-assessment-gap | needs_human | 已教但未考；不能误报没教或fact |
| 5 | screen-fact | reject | 声明返回17，程序返回15；引用声明和实际程序 |
| 6 | screen-safety | reject | total仍正确；配套可调用extra对长度3访问a[5]，不能断言UB必非某值 |
| 7 | screen-mixed | reject | 越界严重拒绝保留，并具体说明教学/过程考查缺口 |
| 8 | screen-full-node-promise | needs_human | 原局部目标已交付，但学生正文又承诺插入/删除而未交付，不能忽略自身承诺 |
| 9 | holdout-stack-complete | pass | 只执行明确两次入栈/一次出栈，容量2足够；无凭空通用接口要求 |
| 10 | holdout-stack-fact | reject | 程序返回后入的9，正文声称返回6 |
| 11 | holdout-stack-safety | reject | 两次push后top2直接a[top]越界，且未递减top/未交付所承诺出栈过程；保留真实缺口，不推断确定返回值 |
| 12 | holdout-prerequisite | pass | 明确先学指针，p指向仍存活value，读取12后返回值；不声称完成链表头插 |

严重错误判据核对具体命题/可达反例；不能只靠category字符串或出现一条finding就通过。所有主/辅断言、分类、影响和引用均需有实际证据；引用只能支持其自身字段包含的命题，不借邻近字段。纯教学不足使用needs_human/unresolved，不编造fact。混合例严重错误不能全降人工，覆盖缺口也不能因已reject而省略。

## 3. 次数、费用与停止规则

用户明确回复“**不用考虑费用，无上限**”：本轮小诊断不设金额上限，cost_cap=null明确表示用户豁免；第三方单价/币种未提供，**不使用OpenAI美元价或Qwen人民币价代算**。真实执行仍记录实际tokens（推理已包含输出）、时长和用量未知；不能把未知金额记成0或实际账单。

请求总上限**12次，串行、每个材料最多1次**；无修正/重试/连接探测/备用模型。首条完整正确对照先发，逐条停止待人工核对，前8全通过并签screen-pass后才能进入4新材料。4生成/3资源审核捕获只有离线Mock，不占真实12次数，也不授权真实发送。材料是固定单元，**不是端到端生成质量验收**。

单次外层60秒包括凭据读取、DNS、HTTP和解析；HTTP内部connect5/read60/write10/pool5受外层限制；非模型清理关闭最多5秒，不续发。整个诊断从首个持久ledger初始化起1800秒不可延长，包括人工等待；批准包到期为2026-10-21 23:59:59 Asia/Shanghai，更早者停止。暂停超过期限不能改时间恢复原包。

发送前SQLite原子预留不可返还；进程中断留下reserved就持久停止，不重发。所有技术失败/超时/限额/返回模型不符/缺用量、任何语义/引用/判据失败均淘汰此候选；余槽未运行继续保留，不追加下一轮或另一候选。正确对照必须pass且无附带问题；教学缺口需要具体说明；严重错误必须命中且所有附带意见正确。每个响应四项人工门禁：完整性、全部断言、全部引用、预期判据；任何false即halt。

## 4. 运行授权与复核

manifest.json绑定完整材料/预期标签、准确wire、非敏感配置、env文件身份metadata、执行器、预算/政策、生产源码/依赖及T070基线。不存在真实run-approval、labels-human或结果人工预签。修改源/材料/env后旧包必须拒绝，不刷新旧manifest来保留授权。

运行批准须准确绑定manifest摘要、最多12次、费用uncapped、本段逐条停止规则；独立标签签核另绑定proposed-labels文件摘要与全部材料，不因费用豁免自动获得。

```text
backend/.venv/bin/python scripts/prepare_luna_materials.py
backend/.venv/bin/python scripts/prepare_luna_admission.py
backend/.venv/bin/python scripts/run_luna_admission.py
# 以下在准确次数批准与独立标签签核前必须拒绝：
backend/.venv/bin/python scripts/run_luna_admission.py --run-one
```

--run-one每次只发一槽，拒绝未批准请求必须先于私有目录、Key提取、DNS和HTTP。真实Key只在批准/预留后从绑定的active Luna组提取，不输出/持久化Key；真实响应只保留最终审核结构、原始响应摘要、已知用量及安全失败元数据，不存思考正文或原始错误文本。诊断仅公共合成材料，无学生数据、业务库写入、人工发布/掌握度变更。

小诊断全通过且签核后，只能进入正式T040准入复核；还须冻结独立全集、真实生成执行链路和准确调用数。正式仍Schema≥98%、自动正式成功≥95%、严重错误召回≥90%；人工通过不补自动分子，失败/未决/未运行留原分母。T041/T042继续受门禁，无dynamic开放。

## 准备阶段自查记录

未冻结前的读者自查指出：先修指针计划的capacity=3无对应实体，现改为index_base/capacity=null并给出不适用理由；栈越界例除越界外还未真正出栈/未交付返回值过程，现标签明确保留这一真实缺口，不将准确指出它的意见算附带误报。只调整未批准的新样本/标签，未修改v4.9政策或旧Qwen草稿；读者自查不是Lee独立人工签核。

读者另指出安全例正文原先已直说越界，可能混入“刻意展示反例”的解释歧义；在正式冻结前改为中性介绍可调用函数，不预告错误、不声明UB的确定返回值。mixed标签另明确认可“未实现承诺的求和循环”这一实际缺口。上述都是未批准材料的准备自查，不是针对模型结果调参。签核准确格式与资格见[人工签核协议](human-signoff.md)。

最终执行器自查补充：初次未批准r01封印后，发现manifest虽记录execution_root却未显式验证，现新建**r02**加入根路径一致性门禁，防止复制目录后另建台账重用批准；原r01文件/摘要保留，并保存当时5份相关执行源码以恢复旧冻结。r01未获得请求/标签批准且真实调用0，拒绝执行未创建账本；r02不继承任何请求授权。
