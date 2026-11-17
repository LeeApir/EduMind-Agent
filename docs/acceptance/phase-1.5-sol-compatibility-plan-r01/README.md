# sol已知差异兼容准备r01

用户选择保留sol，本轮只准备。具体方案见[ADR-0036](../../ADR/0036-sol-known-difference-proposal.md)，未获契约或新真实执行批准，无r03执行入口，不恢复r02。

拟议变化：系统回显仅允许原文或原文+准确37字符后缀；后续显式low并记录总输出含推理；仅允许有限reasoning元数据，加密字段不解密/不转发；只取单个最终JSON。旧指令完整性保持未证，不放宽未知变体。场景审核v2明确引用根为source，Schema严格限制；不自动修正模型路径。生成Prompt v2、原教学标准及20探针标准不变。

原r02失败保留，原始3HTTP/全部usage/回显/路径差异已只读核对。场景形式修复真实有效，sol意见3条minor仍因协议及原路径无效未记入通过。助手复核来源明确，不补人类真值或独立验收分母。

离线规则原型无transport、Key或PG接线：34项规则测试+8项r02结果测试共42passed/0skip，命令/XML/SHA和首次异常类型修正见validation.json。可接受变体仅为提案，不代表供应商真实兼容或质量通过。

```sh
backend/.venv/bin/python scripts/check_p15_sol_compatibility_proposal.py --check
backend/.venv/bin/python scripts/check_p15_sol_compatibility_proposal.py --execute
```

前者离线核对冻结文件；后者固定退出2 PROPOSAL_ONLY_NO_REAL_EXECUTION_AUTHORITY，在凭据/DNS/输出/数据库前拒绝。新路径Schema/Prompt、policy及代码SHA见manifest.json。

后续最小真实提案仅1次纯合成场景审核，low/1536输出请求/120秒，无重试回退、token/金额不限、实际费用unknown，仍需准确请求与代码包独立授权。原累计6次不可退款，原绝对截止13:21:21不延长；到期后需另批时钟。此处无准确新执行包或授权，不能凭“继续”隐式发请求。教学正文问题留待专门修订，不借兼容工作调低质量门槛。
