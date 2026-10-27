# T058 场景形式契约修复

来源：r01真实诊断D01-known的primary和format_repair均多出计划外visualization。未修改返回内容或放宽验证，旧失败保存于466a015。

场景Prompt升级free-scene-generation-v2：在系统说明中明确只使用当前场景允许类型，并为结构修复说明移除意外块及其引用动作、补齐缺失必需形式、不得改计划。用户数据载荷增加由服务端当前scene.forms派生的response_contract（必需/允许/禁止类型及结构修复规则）。不是取整课其他场景的形式，也不推测用户事实。字节限制覆盖新增字段后的完整载荷。

原完整Schema、validate_response/forms集合和机械/安全准入不变。必需text保持原逻辑；不支持的额外visualization和缺失练习仍拒绝，原候选只追加保留，不剪裁后发布。没有对外API/数据库/生产准入变更。

新10单元+1实际隔离PG-Mock以及旧生成54/机械准入40/调度39，共**144 passed，0skip**。真实PG测试刻意先返回错误可视化，再由Mock按准确形式契约修复；首个错误settlement仍保存，只有合规场景ready且课程unendorsed。Mock结果不能证明DeepSeek真实已修复，本任务新增真实请求0。

首次合并运行11passed/133环境setup错误，因为三组旧测试各强制t010/t011/t014专用前缀；已分别使用正确专用DB重跑，未削弱断言。最终命令、数据库、XML/SHA及警告见validation.json。Starlette弃用和旧生成rollback测试连接回收警告仍如实记录。

历史冻结包绑定旧源码；当前树升级Prompt后不再匹配旧包，不能重启它们或改写SHA追通过。已在临时归档的**466a015原Git源码**下重新验证r01包（0）、r01真实失败结果（预期2）及旧DeepSeek小探针冻结包（0）；均0新增调用，路径见validation.json。旧真实失败不被本次离线修复抵消。

交接：T058完成后T038仍需冻结含v2的新诊断配置并真实验证；保留用户不要求token/金额上界和已明确的合成外发授权范围。用户委托助手复核仅按助手来源登记，不能补造独立human标签，不自动推进T039–T042或部署。
