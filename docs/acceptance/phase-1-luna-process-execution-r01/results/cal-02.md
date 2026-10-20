# cal-02：分散覆盖未获pass，本轮首败停止

实际HTTP200、gpt-6-luna正常完成，原完整业务Schema/六项必检、准确wire与raw15705字节完整摘要均通过。模型及本地路由needs_human，findings=[]、unchecked=[]，unresolved一段；未满足事前确认的干净pass，执行器记录FROZEN_CRITERION_FAILED并持久halt。不是接口/Schema失败，也不是安全缺陷漏检。

Provider报告输入16019、输出221，共16240tokens；调用部分5122ms。推理细分和实际账单未知，原始响应/思考正文未保存。完整最终回答见cal-02.json；所有断言核对见cal-02-claim-review.json。

## 未决内容及全部断言核对

模型认可实现、状态轨迹和过程题已经存在。它准确观察到：讲解指向代码关键步骤及q2解析；代码步骤列累计状态，但没有在该处单独列i=3退出；退出解释在练习反馈中。

当前PublishedLearningWorkspace.vue在提交评分后展示反馈解析，此时序观察有实现支持；本次没有用这份合成单元做浏览器实测。不过原始目标只承诺追踪/检查过程，没有“必须做题前讲完”的时序承诺。已确认口径允许过程支持分布在练习解析中。实际发送的未改Prompt也写明：post-answer explanations可教学，只有显式承诺before quiz时才不能替代，且禁止凭空发明此承诺。因此从上述位置观察推出必须补做题前解释，不满足本轮冻结判据。

模型还称给定锚点未定位完整讲解主张或代码，因而无法完整锚定缺口。这与实际请求矛盾：

| 锚点 | 实际完整字段 | 范围核验 |
| --- | --- | --- |
| a1 | /markdown，含证据分布说明 | 0–188 UTF-8字节，覆盖完整字符串 |
| a6 | /source，含完整total函数与循环 | 0–117字节，覆盖完整源码 |
| a12 | /items/1/explanation，含i=3检查失败、不执行a[3] | 0–109字节，覆盖完整解析 |

已从准确冻结wire解析实际anchor_catalog，逐项解析resource_id/JSON Pointer并重算完整字节长度；不是由邻近字段补证据。模型没有发出finding引用，所以不能误称“finding引用ID违规”；这是unresolved中的附带证据定位说法不实。

这份分散覆盖样本内容/标签不改，实际needs_human及失败保留。cal-01的新显式推演正确对照曾干净pass，不能用它抵销cal-02失败，也不回写历史旧状态判断题。

## 停止状态

本轮实际2/4次：cal-01 pass且用户确认，cal-02 needs_human未满足冻结pass。累计输入32054、输出286，共32340tokens；调用部分合计9106ms（不是P95或整轮耗时）。cal-03/04未发，剩余2槽不得复用。halt原因保持TECHNICAL_OR_CRITERION_FAILURE，具体错误保存在receipt中为FROZEN_CRITERION_FAILED。

不为cal-02预签人工接受，不重试、不调Prompt/样本、不开启新轮或后续事实/安全/混合/新材料检查。正式T040未准入，catalog_only、历史所有标签/失败/旧11槽保持。源码未改，原84项离线证据沿用8e49321，本次实际检查452源、原Schema、准确wire、收据、锚点及旧停止；辅助定位曾遇shell未匹配glob/不存在views路径，后改为准确已存在组件路径核对，无模型重试。
