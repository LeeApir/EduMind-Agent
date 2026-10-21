# 最后一个审核候选：新执行包

本包落实[唯一候选方案](../phase-1-review-last-candidate-r01/README.md)，**尚未授权真实请求，实际调用0次**。前一份方案的“执行器待实现”是制作时快照，本包补齐现在的可执行门禁，不修改原方案封印或历史失败。

配置固定为 **Luna/high/v4.9**：只有推理档位low→high，原模型/端点、输入、判据、Prompt、Schema及投影、8192输出上限、60秒超时均不变。生成DeepSeek/none保持，不调用、不切换生产默认。`.env`原low字段保留用于校验原有Luna连接；本包获授权后，审核专用适配器明确发送high。它不是全局配置切换，也不证明第三方内部实际推理强度。

## 只允许这一批一次尝试

1个新候选、1个新私有运行目录、最多12次，严格顺序：

| 阶段 | 槽位 | 上限 |
| --- | --- | ---: |
| 完整Schema兼容 | compat-schema，使用完整cal-01审核请求 | 1 |
| 过程正反例 | cal-01/02/03/04，原材料、原pass/pass/needs_human/needs_human | 4 |
| 严重问题 | 原screen-fact/safety/mixed，原reject及全部标签要求 | 3 |
| 未参与近期修复的旧封存材料 | 原四holdout；仍不称盲测/正式独立集 | 4 |

兼容槽与cal-01是同一完整材料，算两次请求。**Schema技术通过不豁免语义失败**；兼容槽若已出现虚构要求或误报，也马上淘汰。每条都必须完整、实际人工核对全部断言/全部引用和判据之后，才开放下一条。各阶段依次受所有先前实际签核门禁，最后第12条也必须签核；没有第13条。

任何错误、虚构要求、错误证据声明、严重漏检、附带误报或引用失败，都会持久写入`STOPPED_SCOPE_DISCUSSION_REQUIRED`，不只是停一个请求：**本批自动审核研发停止，下一步讨论交付范围**。剩余槽位不可复用，不换模型/档位、调Prompt/材料/Schema、追加预算或兼容请求追到通过；无自动豁免。原Luna/low已退役，旧cal-03/04不补发，分散覆盖不移动退出解释。

第12条全部核对通过后只返回`DIAGNOSTIC_SIGNED_PENDING_T040_ADMISSION`，不能自动进入正式全集或开放dynamic。原98%/95%/90%阈值、人工不补自动分子和catalog_only保持。

## 准确预算与期限

- 最多12次审核请求；生成0次，重试0、回退0、修正0。失败/崩溃/未知是否发送也消耗预约，不重放。
- 每次最多8192总输出tokens、60秒；合计98304输出tokens、720秒模型等待；每次关闭传输最多5秒，靠近总期限会收紧单次超时并预留关闭时间。输入为固定准确请求，实际输入tokens未知。
- 从首个预约起**24小时总墙钟，含人工等待**；绝对到期为**2026-10-23 23:59:59（Asia/Shanghai）**，先到即停，不续旧30分钟窗口。
- 费用沿用用户“不用考虑费用，无上限”，不假定第三方单价或缓存折扣。该政策不增加候选/次数。8192/60秒不保证high足够，截断/超时同样停整批，不扩到通过。

truth-confirmation.json复核了四cal的实际人工确认和原r02相同材料的确认；不预签新模型结果。原材料、标签、失败、未运行项及所有停止台账保持。新请求需要对**本包manifest准确根、1候选/12次/停止规则**另行授权，旧4次批准不能使用。

## 可复核执行链

新`run_final_review_candidate.py`在授权前不会读Key/DNS/HTTP或创建真实私有台账。获新授权后才持久预约，再读原连接Key、审核专用high适配器、公共IP检查及IP/Host/SNI/path钉住、准确wire检查、原完整业务Schema/模型/usage/六必检与本地结论核验。

requests.json与方案捕获字节相同。execution-capture.json另外经**新实际perform → 原review_once → 显式high路由 → 原ProjectedReviewAdapter → ExactTransport → MockTransport**捕获全部12条；不是仅改模型名或手改JSON。Mock回pass只检查传输，不能计入质量/严重错误召回。示例IP8.8.8.8仅用于离线捕获。

```sh
backend/.venv/bin/python scripts/prepare_final_review_execution.py
backend/.venv/bin/python scripts/freeze_final_review_execution.py
backend/.venv/bin/python scripts/run_final_review_candidate.py
```

仅在准确新批准记录存在时，`scripts/run_final_review_candidate.py --run-one`才能发送下一条；每次命令最多1条后暂停。实际结果和不可逆退出状态保存在`local-materials/phase-1-review-final-execution-r01/`，不保存原始响应/思考正文或Key；本包assessments仅绑定实际receipt的真人确认，不提前写true。任何失败均无需额外批准即可停止整批。

validation.json为冻结前实际检查；results/preflight.json为封印后的只读检查。manifest不把新增批准/结果/签核加入自身哈希，以便保留原封印与后续审计；现有冻结文件任何变化都拒绝执行，不重封原件。
