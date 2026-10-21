# 零调用审核配置替换方案：单候选 high

当前决策：只筛选 `deepseek-flash / reasoning.effort=high`，对照是已停止的 v4.5 `low` 配置。本包不改生成流程、生产默认、v4.5 Prompt、输入/输出 Schema、学习目标、材料、审核规则或政策摘要。候选是否更好尚未验证；不是提升质量的保证。T040仍blocked，catalog_only保持。新请求及费用授权均为0。

## 唯一实验变量和真实路由证据

实际JSON请求只改变 `reasoning.effort: low → high`。模型、Provider、目标快照、身份与依赖摘要、学生原文、参考、锚点、Prompt、Schema、温度参数0、stream=false、8192总输出上限和60秒超时不变。温度在思考模式不生效，不把温度0当作输出可复现保证。Provider公布版本为DeepSeek-V4.1-Flash，权重不可变版本仍未知。

准备器执行真正的 `hybrid_resource_review.review_once(scope=unit)`，使用原SceneCandidate/绑定，经诊断专用 `CandidateReviewGateway`、真实 `DeepSeekResponsesAdapter` 到 `httpx.MockTransport`。Mock只返回显式合成响应，不读.env、不解析DNS、不接触网络；捕获实际HTTP请求体，不记录headers/凭据/思考内容。四条逐一证明：入口TaskProfile实际为quality；传入Prompt及原policy_digest一致；适配器实际model为deepseek-flash且reasoning=high；adapter config digest含high与8192，review_record准确回写该digest；请求体与旧low逐项比较仅reasoning.effort不同。见offline-capture.json、cases.json和测试。

业务入口仍使用2048默认值；与已停止low诊断一致，本包的诊断组合层保持原8192覆盖。不能把本实验说成生产2048直接切high的验证。专用网关拒绝非quality、非v4.5指令或不匹配政策请求，不截获生成请求；该网关未安装为生产默认，也未改环境变量。

执行器是旧冻结安全内核的隔离模块实例，使用全新BASE/PRIVATE/RUN_ID，不修改旧模块、批准或账本；重放离线捕获的准确审核请求，经同一适配器再核验实际wire摘要。候选配置与原policy/prompt分别绑定，候选摘要进入预算能力proof，proof摘要进入预算target，源文件/实际wire进入运行manifest。请求effort或其他字段偏移即在读取Key前拒绝，不允许仅换名称而发送low。模型返回和路由门禁通过仍不代表语义正确。

这证明诊断执行器实际会发候选审核请求，不宣称生产已启用high。若后续筛选合格，仅进入T040准入复核；正式生成/审核组合、待审来源失效及生产接入仍须独立绑定和批准，不能沿用此诊断合成结果发布内容。

## 冻结筛选材料和淘汰条件

完整材料、原目标、原计划和逐项判据见human-review.md，机器绑定见proposed-labels.json。保持旧v4.5原材料，原失败回答单独作为已知负例；不把这些已反复见过的例子当独立留出集，不承诺泛化或统计稳定性。

| 顺序 | 材料 | 必须达到 |
| --- | --- | --- |
| 1 | 此次越界 reachable-safety | major/severe code_safety并reject；不可从UB推出固定数值、必不等于16或必崩溃；区分判断题命题与作者认可事实 |
| 2 | 确定事实矛盾 fact-contradiction | 具体检出定义良好循环实际16与声明18的矛盾并reject；每个辅助引用都支持其实际命题，不能用答案F证明数值 |
| 3 | 混合缺陷 gap-and-safety | 保留严重可达越界拒绝，教学缺口不可吞掉严重错误，也不能凭空编造事实错误 |
| 4 | 正确对照 trace-complete | pass；五check齐全；findings/unchecked/unresolved空，无附带误报 |

每条同时检查完整性、所有finding的每个condition_or_counterexample和impact中的全部断言、每个主/辅引用的版本/资源/字段/UTF8片段与对应命题。合法ID与正确主finding不豁免其余错误。严重度与结论不得强于证据；无法保证P不能推出非P。没有定义良好的数值轨迹，不可借算法意图作为实际越界程序运行结果。

**任一完整性、语义或引用失败，立即淘汰本固定候选并持久停止。** 超时、截断、Schema/模型/用量异常也淘汰当前high+8192+60秒配置；不据此推断该模型在所有配置都无能力。每例最多一次，无重试/修正/回退/额外探测/追加调参，无删finding后算通过。剩余槽不再运行，不能在本包中改Prompt、材料、上限、超时或判据后重跑。下一候选必须另行提出理由和预算，不能自动围绕同例反复调到通过。

通过一条后也不自动运行下一条：必须保存完整原回答、逐断言/引用核对及真实用户receipt绑定三项确认；最后一条同样签核。四条都通过仅表示通过这组已知小筛选，之后才复核T040正式验收准入，不自动运行正式验收或开放dynamic。

## 独立调用与预算（待批准）

最多 **4次、9.010516元** 保守预留，每例各一次，按上述顺序串行，首败淘汰。首条兼做真实结构化输出兼容检查，已计入4次，不额外探测；不重跑low对照、不生成新课程。当前真实请求0、授权费用0、没有新真实批准/标签/账本。

| 槽 | 精确请求字节 | 单槽保守预留（元） |
| --- | ---: | ---: |
| reachable-safety | 45142 | 2.252972 |
| fact-contradiction | 45189 | 2.253066 |
| gap-and-safety | 44256 | 2.251200 |
| trace-complete | 45295 | 2.253278 |

以官方高峰未缓存单价输入2元/百万、输出8元/百万，单槽预留 `2 × (1048576 + 精确wire字节) + 8 × 8192` 微元。1M窗口作为接受输入的上界，字节仅作正余量，输出另计是保守留量；不是将字节当token或预计实际花费。本包总上限远高于通常消耗，实际费用由Provider计量，不能把预留说成账单。high可能更耗推理token或触及60秒/8192边界，本实验保持这两个约束，失败即停，不自动增加。

[官方模型与价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)与[Responses参数](https://api-docs.deepseek.com/api/create-response/)于2026-10-16核实：支持high及JSON Schema；max_output_tokens包含可见输出和推理。执行日再核官方支持与价格；变化、不可核实、冻结来源变化、批准缺失均停止。max8192是实验上限，不保证足够。旧所有停止运行继续停止，旧v4.5余3槽不恢复或继承。

## 可复现操作

- 准备和离线捕获：`backend/.venv/bin/python scripts/prepare_review_replacement.py --write`
- 离线回归：`backend/.venv/bin/python -m pytest -q scripts/tests/test_review_replacement.py`
- 获批后每次仅一个真实槽：`backend/.venv/bin/python scripts/run_review_replacement.py --run-one`

未获本包准确4次/9.010516元及冻结材料判据批准时，执行器在Key/DNS/私有目录/账本之前拒绝。冻结有效期至2026-10-18；不创建伪造的预算或标签批准，不把用户批准本方案理解成预签未知实际结果。
