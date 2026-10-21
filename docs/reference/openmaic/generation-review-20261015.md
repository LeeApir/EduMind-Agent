# OpenMAIC生成与审核：2026-10-15源码核对

固定提交：`ecb940c136cc5b4ea56dc81b2505e64eff1dea29`，来自本次读取的公开main树。只读下载到临时目录，不把上游代码复制为本项目实现。现有overview/architecture/prompts笔记保留早期分析，不据此声称当前仍为v0.2.2或主链仍依赖早期目录。

## 实际看到的职责

- [run/plan.ts](https://github.com/THU-MAIC/OpenMAIC/blob/ecb940c136cc5b4ea56dc81b2505e64eff1dea29/lib/server/generation/run/plan.ts)：资料分析（有资料时）、研究、大纲、确认、角色，逐场景content/actions/narration。
- [run/engine.ts](https://github.com/THU-MAIC/OpenMAIC/blob/ecb940c136cc5b4ea56dc81b2505e64eff1dea29/lib/server/generation/run/engine.ts)：checkpoint与事务、wait/countdown/auto大纲确认、场景有界并行/顺序组装、前序讲解与画像传入动作、重试后暂停。结构检查为validateAppScene。
- [scene-generator.ts](https://github.com/THU-MAIC/OpenMAIC/blob/ecb940c136cc5b4ea56dc81b2505e64eff1dea29/packages/@openmaic/generation/src/scene-generator.ts)：不同场景Prompt、JSON解析、元素规范化/坏元素丢弃、KaTeX、测验选项/答案引用契约、交互脚本语法检查。答案存在于选项中不能证明答案知识上正确。
- [research.ts](https://github.com/THU-MAIC/OpenMAIC/blob/ecb940c136cc5b4ea56dc81b2505e64eff1dea29/lib/server/generation/steps/research.ts)：需求/资料摘录改写查询，搜索结果作为大纲上下文。能力由调用者配置，不是每次必定搜索。
- [outline-review.ts](https://github.com/THU-MAIC/OpenMAIC/blob/ecb940c136cc5b4ea56dc81b2505e64eff1dea29/lib/generation-run-client/outline-review.ts)：用户大纲预览/确认，不是自动事实ReviewAgent。
- [content-validation.ts](https://github.com/THU-MAIC/OpenMAIC/blob/ecb940c136cc5b4ea56dc81b2505e64eff1dea29/lib/edit/content-validation.ts)：空讲解、无目标动作、空讨论、无标题等编辑有效性检查。

## 能推断与不能推断的内容

核对的主生成步骤没有本项目那种必经的“正式资源独立事实/代码安全审核→最多两次修正→全部通过才发布”节点。这是本次核对范围内的观察，不是声称上游所有插件、分支、部署或未来版本都无审核。仓库还有eval目录，不能把“有评测”推断成与本项目20严重错误等冻结门槛完全相同，更不能推断它已通过本项目验收。

采用：共享大纲、场景职责分离、内容/动作分离、显式进度与失败状态。适配：大纲由系统内部管理、保留独立审核、人工只处理无法可靠判断的语义。暂不采用：通用编辑器/PDF研究/TTS/自由交互HTML、上游具体重试数量、所有课堂角色和全部媒体种类。

旧prompts笔记中的“EduMind应用”是当时建议，不是OpenMAIC源码的已实现功能；其中赛题/星火强制要求也不是现行PRD。本次不把这些历史建议作为重构依据。
