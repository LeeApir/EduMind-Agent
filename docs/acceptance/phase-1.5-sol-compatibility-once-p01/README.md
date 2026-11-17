# sol已知差异最小合成验证p01

用户在兼容方案交付后明确“执行”。本次按该直接指令实现并冻结新单次入口，登记直接执行授权，不声称用户独立逐SHA审阅了新生成执行包。接受ADR0036的窄兼容规则仅限本合成验证；不复用旧停止批次。

仅一次POST https://aiapi.world/v1/responses，gpt-6.1-sol / low / store=false / strict / 非流式，请求max_output_tokens=1536。准确输入request.json仅两句合成数组说明（一对正确/明确错误）；expected.json及gold不发给模型。引用根为source，精确源摘要与原文quote保持，不自动修路径。

最多1HTTP/120秒/无重试回退/无课程调用。实际费用unknown、token/金额不限，不把max_output_tokens当硬界。原已用6请求，本次最多合计7，原绝对截止2026-10-27 13:21:21 Asia/Shanghai不延长。到期或剩不足完整120秒即预检拒绝。

仅允许原instructions或准确原文后追加37字符后缀；low/推理总量算术/至多一个空明文reasoning元数据项及单一最终JSON。加密字段仅原私有响应保留，不解密/不转发/不输出。未知差异、引用/Schema/对照错误、HTTP失败/重定向、超时或密钥回显立即停止；exclusive输出目录及发送前持久标记防重启，未知不补发。

```sh
backend/.venv/bin/python scripts/run_p15_sol_compatibility_once.py --check
backend/.venv/bin/python scripts/run_p15_sol_compatibility_once.py --execute
```

专用审核Key优先，否则仅在服务端BaseURL准确为AIAPI时使用该服务现有Key；不读DeepSeekKey。执行以公共地址固定IP/Host/SNI、禁重定向/HTTP自动重试，私有原件/tmp/edumind-p15-sol-compatibility-once-p01，Git不保存Key或加密字段。

44离线通过（10单次边界+34窄兼容规则），0skip，见offline-validation.json。实际结果另附不反写冻结材料。即使该一次通过，也不是完整教学验收、原20审核探针通过或T038完成，不自动继续诊断/生产/push/merge。
