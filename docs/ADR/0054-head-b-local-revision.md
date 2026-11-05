# ADR0054 §3准确补充：B候选单次局部修订包

2026-11-05。**用户已授权本轮准确包准备；新真实调用、准确manifest及本批C2待确认。** 本提案只落实原ADR0054第3节，不修改其历史原文、T109 r01停止记录或原审核。当前Provider0，T109 blocked/T102 blocked。

## A. 准确父稿、证据与唯一允许差异

父候选`63323703659f109f164752680e95ca20870cda31dbe720f63aa32d7dcc05b3dd`，独立程序证据`3d7bbd32b2ca6895fc62ce46dc1f1396488e6edd78b4dd21fac09eb4c0a8c754`。父完整raw/payload、原stop审核、同版代码/事实/13帧/答案/规划依据及证据补充一并输入。上述绑定及允许路径保存在准确scope数据中，由程序复算核对，不将新最终候选摘要写入源码。

只允许输出：`failure_scope`完整字符串，和`paragraph_5`对象（完整text/fact_ids，映射`paragraphs[5]`）。事实引用限定单独对照ID `head_evidence_v1.discard_return_comparison`，不能保留旧接收路径引用冒充忽略返回证据。该段算法解释已经正确，提示词优先要求逐字保留原文；若模型实际改字，保留完整diff并由全文重评核对原教学职责，不能由助手补写或自动把模型文字换回原文。

failure_scope必须准确区分：主13帧两次分配成功，两次判空实际执行且为false、继续插入；掩码不分配和真实malloc失败都未演示。保留正确的NULL返回旧head/不写p字段/成功假设/没有C实际执行边界。仅字段替换，不改总结、题干解析、步骤、先备/生命周期或任何程序材料。

程序deep-copy父稿并严格合并：raw只允许上述三个叶位置，payload只允许增加经完整重建的`teaching_evidence`。旧materials/catalog/basis/plan/goal/source_binding全部不变；派生关系独立标记为program_evidence_supplement，不修改旧digest或给旧材料塞新ID。新候选parent_digest仍指向准确原父，候选摘要重新计算。Schema保持现有完整教学Schema，修订远端采用封闭基础对象/数组/字符串，仅两项替换，不返回全文。缺字段/多字段/错父或证据/错ID/其他位置变化/精确邻段复制拒绝，不恢复重复字段。

## B. 新单次请求与C2

拟新批`head-reuse-evidence-revision-r01`，**1次修订HTTP、0规划、0全文生成**，新600秒窗口，在用户确认终端隐藏输入就绪后才登记。旧r01/旧余1不恢复或继承。固定DeepSeek官方Responses：`https://api.deepseek.com/responses`、deepseek-flash、json_schema strict、reasoning none、temp0.2、stream/store false、输出上限4000。请求131072字节、响应2MiB、I/O90秒、本地输入预约139264 tokens。无工具/重试/回退/额外探测，实际金额未知，无可验证金额硬上限。

复用`head_course_fact_revision.py --profile evidence`的单次前台HTTP、已验证phase适配（仅缺省/final_answer）、严格JSON、域名/DNS固定、逐块加密fsync原件。没有新增发送器、监督器或运行框架。新0700 vault、0600 raw.key仅加密body；Provider Key只能新getpass隐藏输入，不能读.env/凭据环境或放入argv/聊天/日志。保存完整原件后再解析；成功也STOP，失败保留failure/ACTIVE/部分或未知证据，不追加请求。

**新批C2需准确接受**：单前台尽力停止，检查后暂停仍可能迟发/继续计费；本机原件无独立抗回滚；金额无可验证硬限。T102已知反例仍适用，T102不恢复。Ctrl-C或STOP不保证撤销在途请求。窗口过期/协议/结构/事实/引用/用量/安全或未知问题均保存并停，不补字段续试。

## C. 完整重评与实际应用

单次原输出严格合并后保留完整候选及新旧差异，交评估助手全文重评，不只看问题句消失。审核需准确candidate/parent/basis/evidence_digest，空blocking_findings，并核全文、引用逐项支持、段落职责、无邻段复制/遗漏、代码轨迹答案、无题干提示、实际展示范围和原段算法保留。程序ID校验不签语义pass。

通过后才使用既有私有快照仓储/准入/播放器/服务端答案导入新的不可变子课程，复制原真实规划并保留来源，不调用规划或冒充重新规划。原r01 failed/v1/STOP不改。新来源`head-evidence-local-revision-v1`/`evidence_bound_local_revision`含准确parent、evidence version/digest，显示局部模型修订和程序证据补充；离线夹具明确不计真实成果。子操作仍使用已识别的前台配置，budget=null，不能复发E01。

本轮把记录驱动准入和来源接点一并准备，不预填最终候选摘要；调用后应只增加数据/评估/版本证据。`--publish`为本机导入，须新准确批准、已完成的一次请求及独立pass；允许在发送窗口后做审核/零出站导入和学习验收，不能再发请求或复用STOP目录执行第二次HTTP。新子课程完整阅读/13步演示与高亮作用域/四题反馈/整页刷新版本一致后，T109才可按协议完成；失败保留准确问题，不自动追加调用或手改。

本轮仅准备，原稿教学问题并未被真实修订。新调用和最终课程验收前T109保持blocked；完成或失败后停止，不推进T038/其他主题。
