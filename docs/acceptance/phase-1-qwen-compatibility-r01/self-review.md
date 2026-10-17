# 修复自查记录（非独立评审签核）

本记录为当前执行者逐项代码自查，未冒称独立第三方评审，也没有代替用户的修复评审或真实调用批准。

- 显式schema_profile只改变strict wire投影，其他Provider/default full-v1保持；不是根据模型名推断能力。能力profile与实际审核审计配置digest绑定，完整review_once+ConnectionOperation+CompatibleAdapter+MockHTTP验证发送参数。
- 完整业务Schema先自校验，独立深拷贝投影去uniqueItems，闭包裁剪root $defs，保留传递/递归引用；属性名或注解内文字不误删。未知关键字/不支持引用发送前拒绝。最终只用原完整Schema检查返回值，重复且长度合法的checked数组被明确拒绝，不能靠maxItems掩盖去重退化。
- 新错误transport对原始stream读取，原始64KiB/解码128KiB两重上限，增量zlib输出设限；不读取不受控全量解压结果。gzip和zlib-deflate可用；br/多层编码显式拒绝且请求只声明gzip, deflate。JSON/非JSON/错误对象形态/截断/无效压缩/炸弹/尾随成员分别分类。
- 错误headers只保留媒体类型和编码枚举，错误字段名/类型及有限code和technical tokens输出；未知词/值/URL/Key不落盘，uniqueItems在白名单内。未承诺保存服务端原始报错或任意字段。
- 原始审核Prompt、目标、材料、业务Schema、政策摘要、生成模型未改。旧证据字节不变，旧冻结因3项明确源码修复失效，账本仍保持停止，不恢复或退款。
- 新包单独1次预算、准确wire和658来源冻结，审批先于Key/DB/私有状态，真实临时连接/目标/准确字节/撤销/10秒清理沿用；请求仍8192/预留8202/60秒，结果只有兼容性状态，无T040 pass。批准还须执行日条款核验，当前0真实调用。

局限：官方不支持uniqueItems已核实，修复不构成真实Provider兼容性证明。历史400是否经过压缩、是否仅由该词造成，均无充分证据。必须修复评审后另批一次完整请求，取得完整审核结果后再人工核对全部断言/引用；本自查和114 Mock测试均不计模型质量分。
