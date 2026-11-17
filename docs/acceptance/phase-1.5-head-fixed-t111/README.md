# T111 固定头插方案的新输入端到端验证

执行包状态为 `prepared_not_authorized`，新真实调用为 0。最终交付目标是 EduMind 应用中的一份新私有可学课程。待确认的契约见 [ADR0055](../../ADR/0055-fixed-head-course-validation.md)。

[准确目标](goal.txt)保留自述先备与固定参数。程序参考结果为接收后 `[9,-2,5]`，忽略两次返回后 `[5]`，`t0/t1` 不可达。逐帧独立期望见 [independent-reference.json](independent-reference.json)。首稿补充的展示与忽略对照证据分别用 `head_evidence_v1.displayed_success_path` 与 `head_evidence_v1.discard_return_comparison` 标识。

| 入口材料 | 固定项与运行时值 |
| --- | --- |
| [规划请求](planning-request.template.json) | 实际 builder 的系统提示、输入与 wire v2 Schema。运行时填实际目标操作和来源 UUID，画像字段要求为空 |
| [本地规划 Schema](planning-local.schema.json) | 完整规划结构、范围、目标与引用复核后才交独立语义评估 |
| [首稿请求](teaching-request.template.json) | 实际 builder 的提示与严格 Schema。运行时填本批准确规划、来源 UUID，附完整程序代码、轨迹、事实、答案和独立补充证据 |
| [修订提示](revision-system.txt)、[修订 Schema 示例](revision-schema.template.json) | 精确目标由父稿与独立审核生成。示例只展示三种允许形状 |
| [配置](candidate-config.json)、[审核标准](review-policy.md)、[manifest](manifest.json) | 固定源码、模式、规则、审核及请求构造，按 SHA-256 核验 |

两条路径在本次准入验证中分别保留首稿和父子链，标明离线夹具。实际模型输出之后，冻结运行源码、提示词、Schema、模型配置、证据规则、审核门槛及修订范围如需变更，本批失败。保留原件和发现，另批再决定。

## 获准确授权后的单前台步骤

1. 执行包评估通过后，单独确认准确提交与 manifest、ADR0055 A–D、预算、600 秒和 C2。获准后在专用开发环境准备数据库及应用。用 `backend/.venv/bin/python scripts/run_head_course_goal_dev.py --profile fixed --prepare --start`。复用专用 PostgreSQL 容器的 loopback 端口，本批使用 `edumind_catalog_p15_t108_t111_live`。在 [应用](http://127.0.0.1:5198/) 以全新访客提交 goal.txt，保留实际 owner/course/operation。安排好评估与终端，随后登记窗口。操作从创建起亦有 600 秒有效期，准备与审核计入有效期。
2. 使用新目录 `$HOME/.local/share/edumind/head-fixed-r01`，目录 0700，独立 Fernet 本地加密键 `raw.key` 为 0600。使用既有开发环境启动器写入的 `/tmp/edumind-t111-live/env.json`，以干净子进程环境运行以下入口。该文件只含开发设置和数据库凭据。Key 只在单前台终端 getpass 提示隐藏输入，每阶段分别输入，聊天、环境、命令参数和项目 .env 均不提供 Key。
3. 审查实际 `context.json` 和 `plan.prepared-request.json`。用已批准的额度和窗口登记起止时刻及 context 原字节 SHA-256。用 [批准模板](approval.template.json)创建该批实际批准记录，布尔门禁只在真实批准后开启。首请求写 `approval.bound.json`，后续须沿用这份窗口与批准。
4. 规划语义独立通过后发正文。首稿或合法恢复稿审核通过即本地准入。有合规阻断且审核允许时启动唯一修订。修订后的独立全文审核通过才准入。发布也在原有效期内完成，之后实际学习验收可继续。每次仅运行一条命令。

```sh
backend/.venv/bin/python -I scripts/head_course_goal.py --profile fixed --inspect
backend/.venv/bin/python -I scripts/head_course_goal.py --profile fixed --prepare --vault "$vault" --owner "$owner" --course "$course" --operation "$operation"
backend/.venv/bin/python -I scripts/head_course_goal.py --profile fixed --send plan --vault "$vault" --approval "$approval"
backend/.venv/bin/python -I scripts/head_course_goal.py --profile fixed --send generate --vault "$vault" --approval "$approval"
backend/.venv/bin/python -I scripts/head_course_goal.py --profile fixed --send repair --vault "$vault" --approval "$approval"
backend/.venv/bin/python -I scripts/head_course_goal.py --profile fixed --publish --vault "$vault" --approval "$approval"
```

其中 vault 为上面的绝对新目录，approval 为实际批准 JSON 路径。启动子进程时只加载开发配置，例如用本机 Python 的 `os.execve(sys.executable, [sys.executable, "-I", "scripts/head_course_goal.py", *sys.argv[1:]], dev_env)`，其中 dev_env 由上述开发 env.json 提供，终端标准输入保持连接。开发服务的网络限制为 loopback，真实调用仅由上面的独立发送命令发往固定端点。

## 预算、停止与原件

最多三次真实 HTTP，规划和正文各一次，修订最多一次。DeepSeek Responses，deepseek-flash，strict，reasoning none，temperature 0.2，关闭 store 和 stream，无工具、重试或回退。每次输出预约 8,000／8,000／4,000 token，本地输入预约每次 139,264。上限与费用区别见 ADR0055 C。发送窗口提议 600 秒，当前尚未启动，旧额度继承 0。

入口在发前记录唯一阶段 attempt，响应逐块加密保全、回读后解析。错误写失败和 STOP，ACTIVE 遗留视为结果未知。独立审核拒绝时，先保存意见，再在该 vault 以独占创建方式写 STOP（例如 shell noclobber），之后不再运行发送命令。过期、截断、用量或字节超限、候选或源绑定漂移、无授权修订、评估不通过均按停止规则处理。成功准入写 `published.json` 和 STOP，剩余额度失效。Ctrl-C／STOP 采用 C2 尽力语义。

索引需覆盖 context／批准／尝试、逐阶段请求／收据／加密原件／结构失败、规划及评审、首稿、恢复位置、可选修订与全文复评、应用版本和真实学习检查。原件在本机新 vault 保存。索引排除本地加密键，Provider Key 不进入原件或证据导出。应用验收需另交真实 [学习流程](review-policy.md#应用验收) 记录。
