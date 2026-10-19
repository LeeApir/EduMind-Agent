# EduMind 单链表头插法：2026-10-19 同输入测试

**结果：产品在生成前拒绝了输入，没有课程输出，不能评价 DeepSeek 的代码质量。**

2026-10-19 09:56:26–09:56:27（Asia/Shanghai），通过实际 Web 页面只点击一次“开始学习”。HTTP 200 的 SSE 依次返回 `agent_start/planning`、`error/GOAL_CLARIFICATION_REQUIRED`、`done/failed`。HTTP 成功不代表业务生成成功。原始响应见 [learning-response.sse](learning-response.sse)。没有重新生成、改写输入、关闭自动审核、手动指定节点或让 OM 修改答案。

## 输入、授权与实例

- [submitted-input.txt](submitted-input.txt) 保存实际 POST 的 goal，无末尾换行；与 OM 的 `docs/reference/openmaic/head-insertion-20261019/submitted-input.txt` 字节完全一致。SHA-256：`ca258576f14b3298728b2ea18ce9c808d31314db7a453c64e6583a128afc6e2e`。
- 用户对“独立实例、单节课、保留自动审核、5元/22次上限”提案回复“无上限”。本轮据此不设费用上限，仍只提交一次；保留产品自身调用/超时限制，观察层最多22次，不恢复任何旧余额。未因此授权修改生产模式或自动质量验收。
- 原 EduMind API/Web 未运行。新建独立数据库 `edumind_head_insertion_20261019`，使用 Alembic 完整迁移至 `0030_learning_phases`；API 为回环8029，Web为回环5199，独立匿名会话。未复用 OM 服务、代理、数据目录或数据库。
- 源码基线 `0f21463c1dad1244d07f306bdd4ed591bd618b13`，原功能分支 `codex/phase-1-continued`。启动器只在本次进程设置 dynamic；没有写入 `.env`，没有修改业务源码、正式门禁、task.json、旧账本或旧签核。原有未跟踪 OM 目录未纳入本次提交。
- `serve_test.py`（临时启动脚本，现已清理） 使用原应用及 Provider 工厂，独立实例增加只读观测：捕获学习请求/响应，以及适配器出网请求体和响应（不保存凭据头）；没有代理或改写模型请求。**本次没有真实模型请求，观测层的真实转发能力未被验证。**

## 模型、思考模式、输出上限与路由

这里严格区分“配置/源码”和“本次实际请求”。本次没有到达模型，因此没有响应模型 ID、usage、指纹或实际模型修订号。

| 项目 | 配置/源码检查 | 本次实际执行 |
| --- | --- | --- |
| 模型 | 服务端 `EDUMIND_PROVIDER_MODEL=deepseek-flash` | 无模型请求 |
| 界面选择 | 当前学习入口没有“DeepSeek Flash”下拉框；此次使用已配置的服务端模型，没有伪造界面选中记录 | 只提交学习目标 |
| 协议/端点 | `responses_json_schema`；DeepSeek Responses 适配器，配置 `https://api.deepseek.com`，预期 `/responses` | 无实际上游路由 |
| 思考 | `build_default_provider_gateway → configured_provider_adapter` 默认 `reasoning_effort=none`；新共享计划链路把同一个 Gateway 传给生成和审核 | 未发送 reasoning 参数；不能写成实际模型非思考运行 |
| 计划输出上限 | `shared_learning_plan.py`：2048总输出 tokens | 未生成计划 |
| 场景/纠正输出上限 | `planned_scene_generation.py`、`hybrid_resource_review.py`：4096 | 未生成场景或纠正 |
| 资源/全课审核输出上限 | `hybrid_resource_review.review_once`：2048 | 未审核 |
| 其他默认输出上限 | `provider_gateway.py`：4096，仅调用未明确覆盖时适用 | 未使用 |
| 环境中的审核变量 | `.env` 存在 `EDUMIND_PROVIDER_REVIEW_REASONING_EFFORT=low`、`EDUMIND_PROVIDER_REVIEW_MAX_OUTPUT_TOKENS=8192`；当前 Web 共享计划调用链未读取它们，不能据此称本次为 low/8192 | 未生效于本次任何请求 |
| 档位/回退 | 共享计划入口直接构造默认服务端 Gateway，未经过用户档位偏好路由；没有在测试中更换模型或回退 | 无发送或回退 |

当日[官方模型与价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)将该模型名对应到 `DeepSeek-V4.1-Flash-1017`；这是官方文档映射，**不是本次响应版本证据**。接口文档链接为 [Responses API](https://api-docs.deepseek.com/api/create-response/)，本轮直接抓取该页超时，未据此新增接口默认值判断。原 OM 材料记录的是 Chat Completions、未显式思考参数/输出上限；两者不能因模型同名而视为同配置。

## 失败定位

原请求中有“刚学完……指针”“单链表头插法”。`goal_node_resolver._alias_candidates` 同时匹配：

| 节点 | 命中内容 |
| --- | --- |
| `c-pointer` | 指针 |
| `single-linked-list` | 单链表 |
| `linked-list-insertion` | 头插法 |

`backend/app/agents/goal_node_resolver.py:73` 在候选数大于1时直接返回 `ambiguous_aliases`；`backend/app/api/hybrid_learning.py:74` 随后抛出 `GOAL_CLARIFICATION_REQUIRED`，尚未执行共享计划生成。规则没有区分本次输入的“已经掌握的前置知识”和“要生成的教学主题”。

`inspect_test.py`（临时查询脚本，现已清理） 使用原解析器、实际默认10节点图谱和禁止任何模型调用的 Gateway 复现相同结果，见 [resolver-reproduction.json](resolver-reproduction.json)。这是离线定位，不是第二次课程提交。没有测试其他图谱配置，也没有绕过解析器测试生成后半段。

数据库操作 `62345851-701d-4a37-89f1-89490fe3a0fc` 为 `failed`，phase仍为 `planning`，`generation_call_count=0`；课程、计划、场景、资源、审核记录、人工待审、发布、画像均为0。详见 [database-evidence.json](database-evidence.json)；[provider-calls.json](provider-calls.json) 为空。由这两份证据交叉核实：真实 Provider 请求0，模型费用0，不是“usage缺失而假定0”。

页面只提示“原请求已失败或取消”，仍显示“正在准备教学计划”，没有把具体澄清原因和三个候选呈现给学生。这是本次观察到的第二个可用性问题；未在本轮修复。现场见 [result.png](result.png) 和 [visible-state.txt](visible-state.txt)。

## 完整课程与独立检查

| 检查项 | 结果与原因 |
| --- | --- |
| 完整课程/原生导出 | 未产生，不能保存不存在的课程；保留了全部实际输入、SSE和失败状态 |
| 讲解、可编译程序、1/2/3示例、预期输出、三题答案解析 | 未生成，均不可评价 |
| 分配失败路径 | 未执行：没有程序可供检查或故障注入 |
| 调用者赋值 | 未执行：没有头插函数或main |
| 正常/失败资源释放 | 未执行：没有生成代码 |
| 编译、ASan/UBSan、malloc第1/2/3次失败注入 | 未运行；不是通过，也不是模型代码失败 |

本样本记录为“端到端未交付：目标识别拒绝”；模型回答质量为“未测”。单个样本不支持总体成功率，更不能与旧的不同输入合并计分。已有 OM 材料含首次环境中断及独立恢复记录，本轮未重新运行或评审 OM；没有宣称两边均完成，也没有给出产品优劣排名。

## 实际检查与交接

以下命令记录测试时的实际操作。测试完成后已按用户要求删除三个临时脚本及其字节码缓存；历史脚本可通过本地提交 `5ca6504` 恢复，下面的脚本命令不再是当前可执行入口。原始输入、SSE、数据库快照、截图及验证结果保留；`artifact-manifest.json` 现仅列出保留文件。

1. `backend/.venv/bin/python -m py_compile docs/reference/edumind/head-insertion-20261019/serve_test.py`：通过。
2. `backend/.venv/bin/python docs/reference/edumind/head-insertion-20261019/serve_test.py`：首次受沙箱本地网络限制，未创建数据库/调用模型；获工具权限后成功创建新数据库、完成30版迁移并启动原应用。首次前端启动同样受沙箱限制；随后在 `web/` 启动 Vite6.1.0成功。
3. 通过 CUA 打开页面、原样填入、点击“开始学习”一次；记录09:56:26–09:56:27 SSE。没有点击恢复或重新生成。前端自行读取原操作状态不等于新生成请求。
4. `backend/.venv/bin/python docs/reference/edumind/head-insertion-20261019/inspect_test.py`：首次导出使用了ORM不存在的 `generation_protocol` 列，只读查询报错；移除该列后成功导出。该修正仅影响证据查询，没有更改产品或本次结果。
5. `python3 docs/reference/edumind/head-insertion-20261019/check_record.py`：检查请求、SSE、DB、零出网、原输入一致性及归档摘要。通过仅表示证据自洽，不代表生成质量通过。
6. `git diff --cached --check` 仅报告原始 SSE 末尾的协议空行；保留该原件，不删改协议分隔符。排除这一个原始记录后，其余暂存内容空白检查通过；SSE内容与帧结构由上述脚本验证。密钥值扫描和业务源码/task.json指纹核对通过。

测试服务在归档后停止，保留隔离数据库和文件，不自动删库。T040仍blocked，正式实例继续默认catalog_only。下一步建议单独修复前置知识/目标识别与澄清提示，再以**相同原文、独立新运行**复测；本轮没有执行修复，也不覆盖这次失败记录。
