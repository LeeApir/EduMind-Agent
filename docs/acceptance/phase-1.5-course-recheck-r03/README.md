# 新首槽课程诊断 r03：离线准备包

状态：**准备完成，未执行。准确新包及新时间窗口待批准**。这是独立的 D01-known 首槽复测，不是此前完整34槽课程诊断的重启，也不沿用任何停止批次的发送权。T038仍blocked，catalog_only不变。

## 范围与请求

准确目标、画像自述与要求见 slots.json，只运行1个合成课程、1个场景。DeepSeek官方 https://api.deepseek.com/responses / deepseek-flash / reasoning none 生成，AIAPI https://aiapi.world/v1/responses / gpt-6.1-sol / reasoning low 提供场景审核建议。生成仍使用 free-scene-generation-v2 及原完整Schema；sol使用 development-scene-review-v2 及其完整Schema。

最多14 HTTP：DeepSeek最多13次（含原有有限结构修复，不增加新的重试策略）、sol最多1次；通常只需规划、场景、审核共3次。请求输出参数每次最多8000，不宣称服务实际执行此硬限。禁止传输层重试、重定向、换供应商、补样本或重发未知请求。20个审核probe不在本包，其旧Prompt/Schema不改，路由明确拒绝。

此前实验累计7 HTTP、reported19355输入/8306总输出全部保留，不退款、不改旧unknown；若本包获准且用完，跨这些包累计最多21 HTTP。旧250次/3小时批次已在2026-10-27 13:21:21（Asia/Shanghai）到期，剩余额度与时间不继承。

提议单独新窗口：**明确登记的起点起最多900秒**，单课程最多600秒、单请求最多120秒且不晚于新绝对截止。批准登记同时冻结起止epoch；到期拒绝，不能靠重新运行CLI或修改登记延长既有账本。当前execution-approval.json为approved=false，不读Key、不建输出/PG、不DNS、不出站。

沿用用户要求作为待批准提案：不设token和金额上限，两个服务的实际收费/币种未知；费用0不是结算事实。请求参数不是硬上界，服务可能忽略限制或在客户端取消后继续执行计费。本包不引用官方费率冒充中转收费，也不将生产bounded_output_verified改为true。

## 传输及复核边界

只发送本包新合成目标、画像自述、生成课程、私有参考答案、动作与必要上游；无真实学生、旧签核课程或H01–H08封存样本。sol是第三方中转，其完整上游上下文无法独立验证，store=false只是请求/回显观察，不证明供应商留存政策。

sol仅接受准确系统文本，或准确文本后恰好一次固定37字符后缀 `\n\nYou are a helpful coding assistant.`；low须准确回显；推理元数据最多一项、摘要与明文为空，不透明密文不解密、不转发。总输出包含报告推理，不重复相加。缺用量、未知差异、工具/多消息/截断、错误根路径或不精确引用即停，原输出不修正。

Host/SNI/公共IP绑定、来源摘要、owner/course/version核对及原机械准入保留。模型revise/reject/uncertain暂停给受用户委托的主助手；模型pass仍要求助手检查。实际复核必须标明Codex assistant / delegated_assistant / independent_human_truth=false，不写成人工独立真值或正式发布资格。

复核特别检查r02遗留的数组名与指针转换措辞、按下标访问复杂度、每题参考答案，以及计划给出的“三步格式”是否适用于概念题和数值题。不可忽略一致性缺陷、改写旧意见、降低原验收分母或用助手通过补自动质量分子。

## 工程入口

离线核对：`backend/.venv/bin/python scripts/run_p15_course_recheck_r03.py --check`。

待准确授权后才可用的单步入口：`--step`；复核导入入口：`--review <准确助手报告路径>`。当前两者均在凭据、输出、数据库和网络前拒绝。批准登记不在manifest内以免循环绑定；须准确匹配manifest SHA、两个服务的具体外发范围、14请求、新900秒窗口、token/金额例外、真实人类消息及来源。

独立输出计划 `/tmp/edumind-p15-course-recheck-r03`；独立数据库计划 `edumind_catalog_p15_t020_exploration_r03`，仅专用测试PG的127.0.0.1:15437。**本轮仅创建了不同的离线测试库** `edumind_catalog_p15_t020_course_r03_offline`。不会重启原r02；本包完成首槽也不宣称T038完成，不自动继续其他槽/T039或部署。

## 验证与已知限制

见validation.json。实际PG＋HTTPX Mock已走通规划、场景、来源冻结、显式low审核及不可绕过的生产拒绝；不是模型真实调用。首次PG运行正确拒绝旧250请求适配器，已分离出只接受新类/14请求的实验调度副本后重跑，生产和旧实验源码不改。测试容器角色最初两次猜测失败，无数据库改动；核对真实角色后使用独立库。

p01真实小探针仅见推理用量0；本包非零推理通过Mock覆盖，仍非真实课程/真实非零推理验证。新调用尚0，准确批准未登记；助手须先实际读课再对照模型意见，不把测试输出当真实复核材料。
