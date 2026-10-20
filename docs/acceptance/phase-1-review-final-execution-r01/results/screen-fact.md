# C/screen-fact：具体检出17与15矛盾，reject符合预期

cal-04经用户“确认”后，B四例实际核对齐全。本轮C阶段第一条screen-fact真实1次：HTTP200、gpt-6-luna正常完成，准确high请求/原完整Schema/六项checked/raw20154字节完整与usage通过。模型及本地reject，单一finding为fact/major，unchecked/unresolved均空。

> The explanation says the function returns 17, but the supplied C code sums 3 + 8 + 4 and returns 15; the explanation also later says it returns 15.

影响判断：This gives conflicting return values for the central example and can teach an incorrect result.

## 全部断言核对

1. 讲解前文确实写“函数total返回17”；同一段后文又写“退出，返回15”，两条不一致，没有借用其他字段。
2. 实际C代码初始化a[3]={3,8,4}、s=0，循环i=0/1/2分别累加3/8/4，i=3条件失败后返回s=15。计算有定义、下标安全，不从未定义行为推出数值。
3. “核心示例返回值冲突可能教错结果”的影响判断有直接依据，不推断真实学生已经形成错误认知。fact/major、整单元reject符合冻结缺陷及协议，没有冒称code_safety或添加教学/画像/时序问题。

## 全部引用核对

| 引用 | 精确字段 | 完整范围 | 支持内容 |
| --- | --- | --- | --- |
| a1 | explanation /markdown | 0–209 UTF-8字节 | 返回17及同段后文返回15，两条主张都实际包含 |
| a6 | code /source | 0–117字节 | 数组、初始和、循环界限及return s，独立推算实际15 |

已从准确冻结wire取anchor_catalog与实际record对比，按resource_id和JSON Pointer解析字符串，核对resource_digest及全文UTF-8范围。没有借用相邻答案/解析来支持源码或声明。两处主/辅引用均支持所需论据；本例只有这一个finding，无附带发现或未决。全部断言及引用逐项证据见screen-fact-claim-review.json。

当前只是Codex证据核对，仍待Lee对本条实际结果确认。不能由这一例正确检出及引用正确推论严重错误总体召回≥90%或全部引用可靠。

本条输入16020、输出464，共16484tokens，调用部分13947ms；累计6次输入96000、输出2646，共98646tokens，调用部分53973ms。推理细分、Provider内部实际档位与账单未知。原始响应/思考正文不保存；receipt摘要`447e5bee40895d2f0baa7209978241cde73883eb03e7cd5f2d1a0b105368433a`。

## 当前门禁

WAITING_HUMAN_REVIEW，无halt；实际人工完整性/全部断言/全部引用/判据确认后才发screen-safety。安全、混合及四旧未参与近期修复材料共6条未发，不把未测记通过。含人工原截止**2026-10-21T09:44:16.144212+08:00**不重计；最后唯一候选任何失败停本批研发讨论交付范围，不追加候选/修正追测。

四cal的实际确认完成只是校准，不是正式独立全集成绩。T040 blocked、catalog_only及旧low退役失败/未发保持。源码未改，原106离线证据沿用9288782，本次复核484源、完整Schema/wire/收据、锚点与旧停止。
