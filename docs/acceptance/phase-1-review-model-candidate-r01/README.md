# 零调用不同模型候选方案：Qwen0902（仅1个候选）

仅准备方案、材料与离线路由证据，不创建真实执行器、批准、凭据连接或账本。本方案没有真实调用授权，T040仍blocked，catalog_only保持，既有生成流程和生产默认不变。

## 选择与可用性证据

审核候选为 **qwen3.8-max-0902**，中国北京、非思考模式、OpenAI-compatible Chat Completions、json_schema strict。该模型在用户既有模型清单中，且T039已有text/structured/stream/tool的真实接入证据（results/final.json；structured检查为HTTP200、21输入/5输出、正常stop）。这证明过去该连接可用，不证明现在的余额、凭据权限及复杂v4.5 Schema已经通过。旧T039只验证简单Schema，不能冒充本次审核兼容通过。旧强制工具模式失败与auto成功保留；本方案审核使用JSON Schema，既不调用工具，也不重新试工具模式。

生成侧保持现有 **deepseek-flash** 配置，仍由原默认组合处理共享计划/讲解/代码/练习；不修改.env、不把Qwen设成全局模型、不静默回退。新候选仅用于已识别的v4.5审核请求。已有Aliyun配置为inactive，批准后必须先在本地安全解析其独立配置并核对T039端点摘要，建立审核专用临时连接，不能错误读取当前DeepSeek Key或把整个.env切回Aliyun。当前准备器不读取.env内容，不检验真实Key；余额与免费额度未知，不预估为免费。

候选范围固定 **1个模型、1个配置**，本方案不包含候补名单。失败、余额不足、超时或不兼容均停止，不能自动改用其余Qwen/GLM/Kimi，也不能提高档位或换模型继续。需要扩展候选时，必须另行解释原因和上限，不能把本次视为无限搜索的额度池。此前Flash/low和Flash/high停止记录不恢复，旧余槽/预算不复用。

## 保持与变化

v4.5 Prompt、目标覆盖规则、输入契约、结果Schema、严重度/路由规则、原四组材料（含身份/依赖/目标/参考/锚点）和policy_digest全部固定。仅审核配置更换。不同Provider需要显式传输映射：DeepSeek Responses的input/text.format改为Qwen Chat Completions的messages/response_format；JSON Schema本体完全一致，不降级到json_object/text_json/tool_schema，不追加修复提示或删字段。模型、Provider、传输格式和思考开关均列入本候选配置，不声称这是隔离“模型因素”的单变量因果实验。

固定 `enable_thinking=false`、`max_completion_tokens=8192`、温度0、stream=false，单次完整调用外层超时60秒。8192位于候选公布的131072输出上限内，是本次实验预算，不保证足够；非思考沿用T039已验证的模式。官方明确max_completion_tokens包含推理和回答，实际可能超出设置最多10 tokens，因此预算与返回用量检查必须冻结为 **8202总输出**，不能仍用8192当费用上界。超过8202或用量未知立即停止，已发送请求不退回槽位。超时包含凭据/目标预检、请求和完整解析，以最外层期限约束内层HTTP超时；失败不加时重试。模型名是官方快照别名，后台不可变权重版本未知。

当前预算内核目标输出上限硬限制8192，不能直接复用旧Flash执行器来跑本包；真实执行前需独立实现并零调用验证8202预留/usage边界，同时保留请求参数8192。不能为了适配旧内核漏算10tokens，也不能为了Schema完整而移除输出费用上限。官方结构化输出建议避免max_tokens截断；本方案使用总量参数，截断按淘汰处理，不声称设置上限能保证完整。

## 离线路由核验与明确限制

prepare_review_model_candidate.py实际执行`review_once(unit)`，经诊断路由组合、生产`OpenAICompatibleAdapter`，到`httpx.MockTransport`捕获HTTP请求体。连接operation是显式离线替身，目标.invalid不发生DNS或网络，绝不是伪造一次真实连接；真实端点单独按T039已知SHA绑定。captured model来自adapter读取的route.model_id并与capabilities.model_id核对，不是只改文档名称。每条核验实际模型qwen3.8-max-0902、enable_thinking=false、max_completion_tokens=8192、Prompt/user输入与原请求相等、Schema本体相等；review_record的政策、Prompt版本和观测请求摘要同步。还实际执行`generate_shared_plan`经原DeepSeek适配器Mock捕获model=deepseek-flash，审核发送数0。由于生成也使用quality档位，不能简单把全部quality请求路由Qwen；本证明按服务端固定v4.5审核指令及绑定判别。

兼容适配器当前不产出TransportAudit，而review_once强制要求。离线桥接仅用观测到的HTTP请求/响应字节摘要附加audit，并绑定真实选中模型/能力/Prompt/政策，不填占位哈希。真实执行器同样需实现该审计桥（含safe失败观测），并核验真实ConnectionOperation的连接/版本/同意/目标与临时凭据生命周期。当前Mock证明审核组合与adapter的模型参数、Schema和策略绑定，不证明这些真实连接边界已验证。本次不修改生产adapter或factory，不绕过catalog_only。

## 两阶段材料和准入顺序

**A：现有4例，每例1次。** 顺序固定越界、确定事实矛盾、教学缺口＋越界、完整正确对照。材料取原v4.5包原文，不塞入历史失败回答或预期标签。首条同时检查真实复杂Schema兼容，已计入4次，无额外探测。

**B：预先冻结8例，每例1次。** 只有A全部通过且逐条有实际receipt绑定的完整性/全部断言/全部引用人工签核，才允许进入B。两组新题材为线性查找与顺序栈，各含完整正确、确定事实矛盾、可达越界、教学缺口与越界并存四类。新材料在v4.5冻结后、候选返回前编写，没有参加历次Prompt或配置修复；不是把求和样本换数字。目标请求是新编诊断场景，不能冒充历史真实用户请求。正确源码可离线编译核对；危险变体只静态核对，不执行。

两阶段内容与原始目标/计划、Schema、配置、判据、顺序、用量及费用全部在proposal/cases/proposed-labels预登记。B不用于调参，A通过后也不得编辑B；B任一失败即淘汰，不能拿它修复后再叫留出集。标签当前是作者提案，需独立人工复核，不能声称已获得独立盲评真值。该8例只作小范围迁移证据，不代表保证任意课程质量或达到正式98%/95%/90%阈值。所有12例通过后，仅进入T040准入复核，再独立冻结正式生成模型＋审核模型组合和正式预算；本包不发正式验收请求或开放dynamic。

统一通过标准：正确对照必须pass且无findings/unchecked/unresolved，五check齐全；事实样本具体检出定义良好计算的矛盾并严重拒绝；安全样本具体检出可达非法操作；混合样本保留严重拒绝并准确区分教学缺口。每条同时检查完整性、每个finding的condition与impact的全部断言、所有主辅引用及unresolved。引用只能支持其实际字段内容，不能借邻近答案/解析；判断题命题不等于作者认可事实；没有结果保证不能推出相反结果。任何一项失败、误报、遗漏或不完整即淘汰当前候选，余槽停止，无重试、修正、自动回退或改材料/Schema/Prompt/超时/输出上限。真实语义失败需在执行锁内持久halt，保留原始review，不能修补后改分。

## 调用与总预算上限（全部未授权）

本方案合计 **最多1个候选、12次调用（4＋8）、总费用上限164元**。不是预计花费，更不是账单或免费额度承诺。阶段B条件不满足则8次全部不发，未用预算不能转给第二候选。每次1个槽，无重试/纠错/额外兼容探测/新课程生成调用。日后额度耗尽不自动切模型或追加预算。

按北京非缓存输入12元/百万、输出36元/百万，全价保守预留，不假定免费额度/缓存折扣。单槽精确预留为`12*(1048576+实际请求字节)+36*8202`微元；1M上下文接受输入上界保守取1048576，字节只作正余量，不把字节当token。所有请求体硬上限64KiB，所以每槽绝对预留不超过13.664616元，12槽不超过163.975392元，向上设定硬总上限164元。实际固定材料按精确wire计算的较小预留与分阶段合计见proposal.json。不能将输入上界预算当作预计tokens或预计会耗尽1M免费额度。

真实执行前另行核实当前价格、模型权限、端点摘要、Key归属、余额与配置；无有效价格/能力证据不发送。每次先持久预留再读Key/解析目标/发请求；未知用量与失败保留已占用槽，不释放重试。程序金额门禁不能保证Provider违规时账户绝对不超扣，账户级账单以服务商为准。

[官方模型能力和北京价格](https://help.aliyun.com/en/model-studio/qwen3-8-max)、[Chat参数及10token误差](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions)、[结构化输出](https://help.aliyun.com/zh/model-studio/qwen-structured-output)已于2026-10-17核实；执行日必须再核。

## 复现与下一步

零调用准备：`backend/.venv/bin/python scripts/prepare_review_model_candidate.py --write`。
离线检查：`backend/.venv/bin/python -m pytest -q scripts/tests/test_review_model_candidate.py`。

这是方案包，没有真实run命令或批准文件。先评审候选、材料及1候选/12次/164元全局上限；获实现授权后补齐Qwen真实临时连接审计桥、8202预算边界、失败观测、分阶段/逐条签核和持久淘汰执行器，零调用验证并绑定源码/预算之后，再单独批准真实筛选。方案批准不得直接执行未冻结的网络脚本。本次只交付零调用方案，不自动开始实现或真实测试。
