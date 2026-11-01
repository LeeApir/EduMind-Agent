# 单组 B/C 探索：准确执行包准备进度

**状态：未就绪，不可执行。** 用户已批准准备准确执行包，但没有批准新的真实调用、材料外发或费用例外。T102 仍为 `blocked`；本目录仅保存独立前置工作，不是最终冻结包，不解除 T038、`catalog_only` 或 H 封存。原 238 文件候选冻结、旧失败和停止批次不改，旧窗口和额度不继承。

## 已完成的离线准备

- [七个合成角色请求草稿及摘要](role-draft/DRAFT-INDEX.json)：S1–S5 为 C 规划/内容/修复、B 生成/修复，S6/S7 为 B/C 审核。各 JSON 是规范化的实际请求 body 开发样例，均无凭据；[构造器](../../../scripts/isolated_diagnostics/prepare_p15_manual_probe_draft.py)只能生成和检查这些文件，不能发送。其版本、字节和摘要均未被宣布为最终执行包。
- S6/S7 分别包含从已存**合成开发证据**重建的完整可见视图，包含目标 ID 和非空问题引用；其完整外层请求分别为 93,115 和 70,039 字节。两者超过旧 65,536 字节策略，低于[拟议新策略](../phase-1.5-manual-bc-exploration-t102/PROPOSAL.md)的 262,144 字节；新策略仍需准确决定，不能追认旧批次通过。
- 七个请求的 system 指令均是固定的合成 echo 指令；新版角色指令仅放在 user payload 的 `candidate_role_instruction_data` 中供检查。索引分别保存两者的版本/摘要。echo 相符只证明观察到特定回显，不能证明角色教学指令实际被执行。
- **B 的准入 echo 不是 B 真实作答。** S4/S5 的 `expected_output` 包含开发夹具给出的合成答案，S5 的 `role_input.original` 也包含合成前一候选和答案；它们仅用于协议回显。S4 的 B 生成输入及 S5 的 `original_input` 未放入引擎参考。真实 B 课程的输出和修复原件必须来自本次 B 实际回包，不能复制这些夹具；独立选样时还需排除与已外发 echo 开发例完全相同的规格，不能用“避免泄题”规避对支持边界的诚实记录。
- 草稿构造器提供纯离线 `observe_synthetic_echo()`：检查准确请求、角色 Schema、回包用量、固定回显，并用新版可见视图核对 B/C 的短 ID 和原文引用。旧七槽观察器仍读取 `artifact`/`target_catalog`，不能直接验证新版 S6/S7。新函数不发送、不封存，也不作准入裁决；缺失指令、reasoning 或格式字段回显分别记 `unavailable`，`admission_decision` 始终为 `not_evaluated`。Schema 内容匹配不证明远端实际启用 `strict`、完整上下文或模型身份。

当前草稿的七次本地输入预约合计 **272,673**、请求输出上限合计 **16,896**；输出上限按各槽具体值计算。请求字节、本地预约和服务商实际 token 分开记录，不能将本地预约当作上游 token 硬限或账单。

## 截止门禁仍阻塞

独立子助手发现并执行 [纯合成反例](reproduce_post_check_pause.py)：在现有 Mock 的时间检查成功后暂停，然后继续执行，模拟派发标记晚于截止。执行者复现为 **232.1 ms**、独立评估者复现为 **237.7 ms**；实际数值会随调度变化。这个反例不启动真实 watchdog，模拟的是其同时暂停的代码路径；脚本禁用 DNS/socket 连接并拦截文件写入，不证明发生过真实网络派发。即使设备没有休眠，普通进程调度和阻塞也会形成这种时隙。

本机 macOS 的 `SO_SNDTIMEO`、`setitimer`、Network.framework 相对发送过期和 PF 状态超时均未证明可以保证绝对截止；Apple 也说明 [PF 不是稳定的软件接口](https://developer.apple.com/documentation/technotes/tn3165-packet-filter-is-not-api)。本机可在隔离、无网络 Docker 容器中取得 `NET_ADMIN`，但当前未装或验证内核时间门禁，也没有修改宿主网络。Linux [nftables 的内核过期集合](https://wiki.nftables.org/wiki-nftables/index.php/Element_timeouts)或 ETF 只是待验证方向：必须处理实际发送边界、暂停与休眠时钟、TCP/TLS 重传、已排队数据和失败关闭，不能凭文档或单次 Mock 宣称保证。

可进一步研究的最小方向是：在单次、`network=none` 的临时 Linux 环境中，用内核侧绝对时间检查和默认拒绝策略保护本地替身，发送进程本身不持有改网络规则的权限；先验证发送及监督同时暂停、批次与单次截止、停止、崩溃、时钟/休眠、已有连接及排队数据，再独立复审。Linux 的 [boottime 时钟](https://docs.kernel.org/next/core-api/timekeeping.html)包含休眠时间，但文档并未证明当前容器的门禁实现或虚拟机时钟可靠。当前已有镜像没有发现 `nft` 工具，该方案需要先确定并固定可用工具/机制；不修改宿主网络、不以此宣称可以真实出站。若不能证明机制满足原判据，仍不能执行。

因此尚无可核验的方式保证“截止后但调用方尚未收到停止时不会首次派发”，也不能宣称可信启动、跨角色密钥隔离、真实原件加密保管、独立收据和真实传输已接线。继续把这些缺口标为执行前提；不使用有缺陷的旧控制器或其 `verified` 汇总绕过它们。已经进入网络的数据不能由本地停止撤回。

## 公开费率和预算缺口

2026-11-01 仅查看公开文档，未使用账户或 Key 查询。DeepSeek 官方[价格页](https://api-docs.deepseek.com/quick_start/pricing/)列 `deepseek-flash` 高峰 cache-miss 输入 **USD 0.30／百万 token**、输出 **USD 1.20／百万 token**；别名的服务版本可能变化。AIAPI [公开页面](https://aiapi.world/)列 GPT-6.1 Sol 输入 **USD 2.50／百万**、输出 **USD 15.00／百万**。这些是公开展示，不证明本账户分组、币种、实际路由、隐含上下文或账单费率。

先前方案建议新批总额 USD 5、生成 USD 2／审核 USD 3，但该上限尚未获本批执行批准，也未验证账户能否强制。为说明其含义，假设七个草稿的本地预约刚好等于实际输入 token、其后九次课程请求均达到各自本地最大预约且输出均达到请求上限，按上述公开费率作乘法：总计约 **USD 4.19045**，其中审核约 **USD 3.69365**，超过拟议的审核侧 USD 3。**这只是算术情景，不是费用预测或硬上限**；本地预约不是 tokenizer 上界，实际账单可能更高或更低。若无法证明服务端额度能实施拟议分额，须在未来准确包里改变预算或明确披露并另获费用例外，不能沿用旧例外。

## 本轮验证和下一步

```sh
env -i PATH=/usr/bin:/bin PYTHONPATH=backend:. PYTHONDONTWRITEBYTECODE=1 \
  backend/.venv/bin/python scripts/isolated_diagnostics/prepare_p15_manual_probe_draft.py --check
env -i PATH=/usr/bin:/bin PYTHONPATH=backend:. PYTHONDONTWRITEBYTECODE=1 \
  backend/.venv/bin/python -m pytest -p no:cacheprovider \
  scripts/tests/test_p15_manual_probe_draft.py \
  scripts/tests/test_p15_visible_review_view_v1.py \
  scripts/tests/test_p15_minimal_contract.py -q --tb=short
env -i PATH=/usr/bin:/bin PYTHONPATH=backend:. PYTHONDONTWRITEBYTECODE=1 \
  backend/.venv/bin/python docs/acceptance/phase-1.5-manual-bc-preparation-t102/reproduce_post_check_pause.py
```

结果：草稿重建一致；**141 passed**；反例按上述方式再现。Ruff 和活动账本检查通过。独立助手另检查实际草稿、回显/引用/用量反例与期限问题，记录见 [独立评估](INDEPENDENT-REVIEW.md)。本轮只访问公开技术与价格文档，没有读取真实密钥或调用真实 Provider。

在实际截止机制、可信启动/凭据、原件及收据核对、费用边界通过独立离线验证之前，只能保留本草稿；不得声称准确执行包已冻结或允许真实发送。候选和策略冻结后才可独立选新样本并准备可批准包；七项准入与课程合包会改变 ADR-0047 D 的原有顺序，也须列入准确决定。
