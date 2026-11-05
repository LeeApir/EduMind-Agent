# T109 B候选：单次局部修订准确包（未授权执行）

**当前只准备，真实Provider0，新窗口未启动。拟1修订/0规划/0全文。** 依照用户新指令及[ADR0054 §3](../../ADR/0054-head-course-evidence-supplement.md)，准确补充契约见[本批ADR](../../ADR/0054-head-b-local-revision.md)。T109 r01仍STOP/blocked，原稿和原审核不改。

## 准确请求与允许替换

- 父`63323703659f109f164752680e95ca20870cda31dbe720f63aa32d7dcc05b3dd`；证据`3d7bbd32b2ca6895fc62ce46dc1f1396488e6edd78b4dd21fac09eb4c0a8c754`，程序核原候选/同版材料和证据完整重建，不用省略号匹配。[完整输入](input.json)、[准确HTTP请求](request.json)、[输出Schema](output.schema.json)。这些是实际构造字节，不含未来规划或父稿占位。
- [scope数据](scope.json)限定两项完整替换：failure_scope字符串、paragraph_5对象（text/fact_ids）。[允许叶差异](allowed-diff.json)只有failure_scope、paragraphs[5].text、paragraphs[5].fact_ids；payload另只增加独立程序证据，不改原材料/代码/轨迹/答案/依据/来源绑定。
- `failure_scope`明确两次成功分配/两次判空执行且false后继续；掩码不分配与真实malloc失败均未展示。`paragraphs[5]`算法解释已正确，提示词优先逐字保留其原文，把引用改为独立计算对照 `head_evidence_v1.discard_return_comparison`。没有提供助手编写的替换正文。
- 模型只返回这两个替换项，不能输出总结或全文；程序严格合并、完整Schema/新证据/场景/帧核验，拒绝额外字段、错ID、重复键和越界。任何模型字词变化完整保留并交独立语义重评，不能静默恢复原文。

## 实际入口、预算与停止

[配置](execution-config.json)、[待批准模板](approval.template.json)、manifest.json冻结当前请求/来源/代码。入口复用现有单前台收集器：

```
backend/.venv/bin/python -I scripts/head_course_fact_revision.py --profile evidence --inspect
backend/.venv/bin/python -I scripts/head_course_fact_revision.py --profile evidence --send
backend/.venv/bin/python -I scripts/head_course_fact_revision.py --profile evidence --publish --owner <实际应用owner>
```

批准后先复用原开发环境并重启既有API加载本提交（仍禁后台Provider/Worker）；只有新准确批准后才建新vault/登记600秒/请求用户getpass，发送命令的Key不能来自.env、环境、argv或聊天。单次完成或失败均STOP，拒绝再次发送；保留原输出/收据/父稿/差异/派生候选，失败和未知原件不删。新源为`head-reuse-evidence-revision-r01`，不是重开旧r01。

DeepSeek官方Responses/deepseek-flash；reasoning none/temp0.2/stream与store false/max_output4000，输入本地预约139264、请求131072字节/响应2MiB/I/O90秒。无重试回退/重复成员恢复/探测。本批C2需新接受：尽力停止仍有暂停后迟发/继续计费、无可验证金额硬限、本机证据无独立抗回滚；T102继续blocked。旧额度0继承。

## 调用后的完整交付要求

1. 先原件完整保存、再严格解析和合并；教学文字只能来自父原稿和新真实输出。首稿首次结构pass/r01教学stop不追改，新证据标程序补充，新修订单独记模型结果。
2. 交独立评估助手：准确父/候选/basis/evidence绑定；重评全文/13帧/四题，尤其范围声明、原段算法职责、引用来源、无复制遗漏或泄题。final-review必须verdict pass、blocking_findings=[]并明确全部约定检查；模型字词变化不能仅凭Schema记教学成功。
3. 通过后 `--publish` 沿现有服务进入新私有子课程，原failed/v1不改，原真实规划仅准确复制并保存来源。来源UI展示“模型局部修订 · 程序证据补充”、新摘要和证据摘要，不借旧回放身份。导入无需Provider Key/新HTTP，且不得重开已STOP请求。
4. 实际应用完整阅读、13步状态/代码行/作用域/播放暂停前后重置、四题错答与正确解析、刷新scene/attempt版本相等且无重复提交后交评估，T109才可能完成。失败即记录并停止，不自动扩修或再调用。

当前无模型修订稿、真实教学重评或真实新课程。定向检查/MockTransport/专用PG只证明准备接线，不计模型或课程成功。

本轮[定向检查记录](CHECKS.md)保留准备验证的实际命令与边界，尚未开展真实修订及教学效果评估。
