# 单组 B/C 请求草稿：独立复核

评估者：`/root/deadline_feasibility_review`，独立子助手，身份 `assistant`；共享工作区不构成物理隔离。结论：**七个文件可作为非执行的合成请求草稿；尚不能形成可执行准确包，也不能作为真实接口准入结果。**

只读核对版本：

| 文件 | SHA-256 |
|---|---|
| [草稿生成与观察器](../../../scripts/isolated_diagnostics/prepare_p15_manual_probe_draft.py) | `eccd3a3c7b78d0a0494b12f29bb6d9afb735385cfd036182bd9cb21c701d5e80` |
| [离线测试](../../../scripts/tests/test_p15_manual_probe_draft.py) | `bb77a506fb142068bf969e780acf32e3e016dcda1d81161a667c005c4112c512` |
| [草稿索引](role-draft/DRAFT-INDEX.json) | `2a4412eb7aba6b3178b6f113038f2b059bce3553eae103859db52572ba38afa2` |
| [截止反例](reproduce_post_check_pause.py) | `cd3853854116cebc89153a7f5bbbf5605c8d0f969528bebcecb31b3571b06c8b` |

七个请求的阶段、模型、推理参数、完整 Schema、请求摘要及输出上限与索引一致。system 使用固定 echo 指令，角色指令作为 user 数据携带，不能据此证明教学指令实际执行。S6/S7 分别有 272／218 个可见单元及非空问题，引文能定位到其实际发送视图。

S4/S5 的 `expected_output` 包含合成答案，S5 的 `role_input.original` 包含模拟前一候选及答案；它们只是协议回显夹具，不是模型独立作答或真实 B 基线。真实 B 修复必须来自实际 B 回包，不能复制这些夹具。草稿所用合成归档与旧审查清单的摘要一致，本地摘要不提供外部来源认证。

独立评估者在清空进程环境、拦截 `.env` 及 DNS/socket，并将 pytest 临时目录放在 `/private/tmp` 后：

- 草稿 `--check` 通过；[独立测试](../../../scripts/tests/test_p15_manual_probe_draft.py) **14 passed**。
- 合成反例中的错模型、`strict=false`、输入用量超预约、请求篡改和 S6/S7 不可见引文均被拒绝；缺少回显单独标 `unavailable`，准入裁决保持 `not_evaluated`。
- 在时间检查后暂停的合成路径再次到达截止后的模拟派发标记，晚约 **237.7 ms**。该复现没有运行真实 watchdog，也没有真实网络。

新观察器不发送或保存原始响应，不能验证实际 HTTP 状态、端点、Provider 身份或请求确已外发。S6/S7 不适用旧七槽审核校验器；新观察器仅作合成检查。截止后首次派发、可信启动与跨角色密钥隔离、迟到原件完整性、真实传输和账户费用硬界均未闭合。S6/S7 大于旧 65,536 字节上限，新容量策略须另行明确决定。未读取真实密钥或调用 Provider。
