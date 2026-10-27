# T038 完整开发诊断 r05 执行准备包

状态：**仅准备，真实执行批准false，当前新增真实调用0**。基线T060提交11d6909、T061提交0d6ccfc；具体设计为已批准ADR0037及[ADR0038 A—B](../../ADR/0038-approval-20261027.json)。本包的实际执行仍需独立准确授权。旧r04及所有旧批次继续停止，unknown和失败不回写。

## 准确配置与范围

- 单候选组合、单批次，原slots.json字节保留：12课程/6画像对＋2负例＋20审核探针。材料已暴露，仅为开发诊断，不作独立留出集；H01–H08继续封存。
- 生成：`https://api.deepseek.com/responses`，准确模型ID `deepseek-flash`，reasoning none，free-course-plan-v1、free-scene-generation-v3；准入free-scene-hard-gate-v2。不保证远端别名背后的模型快照不变。
- 审核：`https://aiapi.world/v1/responses`，准确模型ID `gpt-6.1-sol`，reasoning low；场景development-scene-review-v2、原20探针PROBE_PROMPT/resource-review-v3。独立合成建议适配器使用isolated-review-observability-v1，不推广到生产网关。
- T060规则：缺失/null instructions记echo_unavailable；存在时仍仅准确文本或一次固定37字符后缀可接受。reasoning最多1项且content空；summary至多1项、精确type/text、summary_text且≤4096字符；不透明密文≤262144且不解密。摘要只核对形状/大小，正文不展示、不解释、不转发；原响应私有封存。
- 每次实际审核另存review_protocol_observation，准确绑定ticket、身份、stage、源SHA、请求/响应原始字节SHA。instruction_delivery_verified/upstream_context_verified恒false；不能用回显或token数量证明完整上游。最终只读assessment重新校验原始字节、Schema/来源/引用/工具/用量，并拒绝缺失/篡改/重复观察记录。
- T061要求每题明确初始/执行状态、有限唯一答案域与输入格式，解释保留讲解/solution。code等每种块只包含原Schema允许字段。候选答案和模型pass均非可靠评分资格，仍须助手逐题实际核对；原Schema和教学门槛未变。

## 新预算与外发

拟新最多**250 HTTP，登记起10800秒（3小时，含助手复核）**：最多182生成＋68审核（48场景＋20probe），每课程13生成/600秒，每请求120秒且不能超过绝对截止。原14请求保留，此组实验累计最多264；历史报告输入81890/总输出14958保留，其中unknown不转可信结算。不是全项目历史累计。

本包拟**token/金额不设上限**，需要本次明确接受；当前实际费率、币种、计数收费及服务硬上限未验证，不套用其他服务的公开价格。每请求max_output_tokens=8000只是请求参数，不能证明服务硬限；客户端取消后可能继续计费。没有计数探测或额外试发预算。

仅外发本批合成目标、画像自述、计划/正文、私有参考答案、动作及必要上游，分别用于DeepSeek生成和AIAPI审核。不含真实学生、旧签核课程或封存材料。中转完整上游上下文及留存未独立验证。

禁止传输重试、重定向、自动回退、未知重发、补样本、自动新批或重启旧批次。仅原13生成预算内已有的结构修复；首次Schema失败保留原分母。未知发送、协议/安全/请求/时间边界问题即停；模型非pass先交助手核对，确认真实质量问题按原门槛停，准确误报仅登记有源证据裁决后审核剩余场景，不重做已有生成。

## 执行与实际复核

`backend/.venv/bin/python scripts/run_p15_full_diagnostic_r05.py --check`纯离线核对冻结文件；不读Key、DNS或PG。未批准的`--step`在读取凭据、数据库及创建输出前拒绝。

准确授权后才登记新独立窗口，使用独立目录`/tmp/edumind-p15-full-diagnostic-r05`和PG库`edumind_catalog_p15_t020_diagnostic_r05`（127.0.0.1:15437）。准备阶段不创建真实目录/真实库。只用现有专用DeepSeek Key；审核优先独立AIAPI Key，若缺失仅允许在通用Base URL准确为https://aiapi.world/v1时使用通用Key，两者必须不同；不把Key写入Git、输出或日志。

`--step`每次推进一个新槽或余下场景审核，在助手检查点停下。助手先读课程再核对模型意见；`--review`导入实际逐块事实、逐题答案/可接受与拒绝输入、原始目标/画像和画像对的证据，`--adjudicate`只接受准确来源/意见绑定的真实误报裁决。review_type=delegated_assistant、reviewer=Codex assistant、independent_human_truth=false，不伪造独立人类真值，不让用户填材料。

`--assessment`只读核对原始证据后使用原固定分母及阈值：首次Schema≥98%、完整生成≥95%、个性化≥90%、事实≥99%、答案100%、严重错误召回≥90%、审核精确率≥90%、正确控制误阻断0、自然严重错误0。缺失/失败/未运行不剔除；零指控不算100%精确率。通过也仅开发候选，不等于独立质量/性能或生产开放。

## 离线验证与交接

实际共128项通过、0skip（126离线＋2隔离PG/Mock）；命令及证据摘要见validation.json。新测试验证缺回显＋有界摘要的真实适配器接线、原Schema与来源拒绝、观察记录篡改拒绝、私有摘要不外发、完整窗口/预算/停止边界、固定分母、委托来源和隔离PG/HTTPX Mock。Mock工程成功不代替实际教学质量。

本包所有新代码在隔离诊断/CLI/测试；既有T060/T061及生产业务代码不再改动。ADR0038原准确批准仅覆盖离线工作；真实执行须本manifest独立批准及新窗口，原r04的费用例外和过期窗口不继承。不push、merge、部署或推进T039。

首次PG启动就绪竞态导致2项setup错误，确认就绪并建立offline库后按原断言重跑通过；归档脚本已增加就绪和专用容器保护，实际重跑通过。最终仅Starlette弃用警告，专用PG容器已恢复exited。
