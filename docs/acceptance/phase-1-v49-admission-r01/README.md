# v4.9 新诊断准备草稿（未冻结、不可执行）

2026-10-19：用户授权按配置、完整材料/独立标签、小诊断准确预算、正式T040顺序推进。准备过程中用户提出GPT-6 Luna新候选，并报告自行测试一次调用通过。目前组合选择及该次调用的实际Provider/端点/模型/传输/参数证据未登记；不将用户自测计入本项目验收台账。

**本目录所有文件目前均为草稿，不是冻结执行包或真实预算申请。** Qwen的出站捕获及160.605480元保守信封仅为被暂停的组合草案；不能转作Luna预算、授权或质量结果。不存在新run-approval、独立人工标签或真实账本；真实Provider调用0，T040仍blocked，生产catalog_only保持。

已准备12份完整学生材料及原始目标/计划/教学绑定；8份筛选（完整、分散、教学缺口、考查缺口、事实、安全、混合、完整节点承诺遗漏），4份新材料（栈正确/事实/越界、明确授权的指针先修）。新材料在v4.9冻结后编写，未参与此前Prompt修复；对准备者可见，不能称为统计盲测。预期标签由Codex起草，独立人工状态pending；不能把Mock pass或起草者自查当作独立签核。

scripts/prepare_v49_materials.py可离线复现材料。scripts/prepare_v49_admission.py离线通过当前生产agent/adapter捕获12单元审核、3资源审核和4生成请求；HTTP为MockTransport、DNS/同意/数据库连接为替身，只有请求构造证据，没有真实出站或模型语义质量证明。捕获的脚本化pass不写为诊断结果。生成请求2048/4096，none；Qwen审核8192/非思考/60秒，仅为暂停候选，不更改生产默认。脚本尚未完成专项回归/代码审查，禁止直接据此真实调用。

准备时首次材料术语数组为空、判断题标记缺失分别触发本地契约拒绝；修正材料后通过，未修改任何业务校验。普通Docker清单读取因沙箱socket权限失败，未创建数据库或容器。Git新分支创建首次受沙箱限制失败，升级权限后成功；没有自动审批拒绝。

下一步先确认用户自测Luna的实际API渠道与精确模型ID，再决定是否采用“DeepSeek生成＋Luna审核”作为唯一候选；该建议不代表已实施。固定v4.9/Schema/材料，完成新传输适配与实际请求捕获，核实渠道能力、推理/上限/超时及价格，重新计算预算并补可执行单槽门禁与回归；独立人工标签及准确费用授权后才可发出请求。任一语义/引用/完整性失败按新冻结规则停止，旧Qwen/DeepSeek失败账本不恢复。小诊断通过之后仍须正式T040准入及独立全集/预算；Schema98%、自动95%、严重错误召回90%不降低，人工不补自动分子。

官方只读核验：
- [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna)：支持结构化输出及none/low/medium/high/xhigh/max；标准短上下文输入0.10美元/百万、输出0.50美元/百万；长上下文/区域/处理档位价格不同。第三方渠道不自动套此价。
- [DeepSeek](https://api-docs.deepseek.com/quick_start/pricing)：deepseek-flash目前由DeepSeek-V4.1-Flash-1017服务；别名不能被当成固定权重快照。
- [Qwen模型](https://help.aliyun.com/en/model-studio/qwen3-8-max)、[参数](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions)、[Schema](https://help.aliyun.com/zh/model-studio/qwen-structured-output)：暂停草案依据，未代替新Luna核验。
