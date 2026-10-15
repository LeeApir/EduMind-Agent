# 检查项与锚点请求约束 v4.2

沿ADR-0015的既有最小必检项ID、准确锚点引用规则修复发送契约；不修改统一存储Schema、
发布阈值、人工权限或r01/r02的原结果/标签/账本。

- Prompt版本 evidence-resource-review-v4.2：checked只填mandatory_checks里的原始ID，
  不翻译、不写自然语言、不重复；真实未完成项在unchecked/unresolved说明。
- 输出投影Schema按scope将checked.items限定为五个有效ID的enum，uniqueItems=true；
  不强制checked总是全满，真实未知仍可表达并按原规则转人工，不诱导虚假覆盖。
- finding.anchors按实际server anchor_catalog枚举；无法定位不得编造ID，原本地检查保留。
- 原unit仅三结论、resource修正次数不变。请求规则进入政策摘要，旧待审仍按原版本失效。

回归直接使用r02真实prose结果：新请求Schema拒绝它，旧本地路由仍是
needs_human/COVERAGE_INCOMPLETE，不把历史文字事后解释成ID或补成pass。再验证重复、
翻译、跨scope检查ID、虚构锚点拒绝，部分覆盖/真实未知保留，实际适配器不信任厂商输出。
Schema能约束形状和ID，不能保证审核实际做过或事实正确；后者仍需真实新例与独立核对。

r03只做相同配对样本家族的校准，不冒充独立正式样本。其请求/批准/账本独立，
旧轮停止状态不解除；零调用修复批准不授予新费用权限。
