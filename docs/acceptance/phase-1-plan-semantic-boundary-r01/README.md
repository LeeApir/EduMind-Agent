# T089：计划审核机械边界与语义输入

本批只实现一个通用分工修复：代码在外部审核前验证摘要、身份、版本和引用绑定，模型评审语义内容。未改生成模型、审核模型/high/8192/60秒、学生内容生成Prompt、模型审核输出Schema或发布硬门；H封存，T040 blocked，当前catalog_only不变。本目录不是新真实调用授权。

## 前置门及语义视图

生产路径先从SQL读取当前operation归属、单元最新plan ID/版本/四类摘要，再与实际计划对象核对；正确的复用操作可显式绑定当前op，旧版本或跨owner/unit/op拒绝。随后重算快照摘要，核对活动政策、正整数版本、计划schema、输入metadata/参考条目版本和digest/参考来源信息。错误绑定在**审核请求前**阻断；若先生成计划，其先前生成请求仍如实计入，不冒称整条链0调用。独立离线入口只检查显式传入的可信绑定/快照一致性，不声称没有DB也证明了当前数据库授权。

模型只收到完整原文、目标/场景关联、示例状态与预期、相关参考正文、已知学习证据以及引用片段。只按已知服务端结构字段投影，不按哈希正则删除教学内容或用户文本。全局ID、存储/容器摘要及图谱/路径/引用条目版本留服务端；局部objective ID和scene依赖仍作为语义关系。没有硬编码P01、f83f、b333、17或19。

## 引用及兼容

`plan-check-prompt-v2`＋`plan-semantic-input-v1`；模型输出仍完整`plan-review-result-v1`。出站仅保留可达model_result/finding定义，未发送绑定/证明/审计Schema。真实适配器Mock捕获验证Prompt、出站模型/high/8192及Schema内无服务端绑定摘要和owner/plan UUID。

模型锚点仅含ID、来源角色、语义字段位置与实际原文摘录；完整JSON Pointer、UTF-8范围、不可变摘要和身份在服务端保存。新`plan-check-record-v2`可引用`reference_context`，按input_digest绑定参考正文，不冒称用户要求。v1记录与摘要规则不变、可读取；v1不能伪造新锚点类型。没有新表/迁移、人工批准权限或验证器；旧待审授权因政策摘要改变失效，旧发布历史读取和旧失败不回写。

## 验证与限制

新增通用回归覆盖正确绑定、18种错误绑定（含重算hash后仍版本/参考错配）、真实语义冲突完整透传、哈希教学字面量保留、实际适配器出站和v1/v2隔离PG保存/读取。合成模型返回的pass/reject只证明协议与证据链路，不能当真实误拦截/漏检结论；下一T090冻结唯一一批真实开发对照和准确预算。

历史6个停止SQLite与H封存字节见[historical-seals.json](historical-seals.json)，仅做摘要维护，不读H材料进入Prompt或评分。旧执行包原manifest不重写；修改前源码从提交5f17bf6独立归档在[prior-source-snapshots.json](prior-source-snapshots.json)，当前运行已使用新版本，不能再用旧runner复现旧请求或恢复旧额度。用户未提交的旧结果README编辑保留且不包含在本任务提交。

首批隔离PG31文件398通过，后续增加来源操作身份、实际适配器及参考正文完整性回归；最终PG结果见pg-integration-03.json。最终25个非PG边界用例通过。初始18通过2失败是负例把原本全0摘要再写成全0，未实际形成坏绑定；改为不同值后验证阻断，不削弱断言，原失败JSON封装保留。5源码mypy/Ruff/workflow/diff检查及证据明细见[validation.json](validation.json)。
