# T084/T085：七槽合成兼容真实入口 r01

原七次范围、900秒与ADR0047 A—D已获批准；用户在T083后明确“开始真实调用”，可解除离线交回审查的等待，不记录为独立评估已通过。本入口仍只发送fb61d70冻结的七个纯合成请求，不发课程/真实学生/e03/H，不恢复旧批次。S1–S7.json逐字节等于T083的S1–S7.request.json；输入与输出Schema未改。

当前实际账户费率/币种和上游硬界未核实，原USD1硬费用上限无法由公开标价证实。已向用户单独提出**仅本批**费用风险例外；未获明确答复前execution-approval.json保持accepted:false/费用标记false，入口在Key/DNS/创建真实目录之前拒绝。七次范围不重复审批；没有把“开始”改记为“接受金额不限”。

## 准确范围

S1 C规划、S2 C内容、S3 C修复、S4 B完整生成、S5 B完整修复，均为DeepSeek官方api.deepseek.com/responses / deepseek-flash / none；S6审核B、S7审核C为AIAPI aiapi.world/v1/responses / gpt-6.1-sol / low。原样echo固定合成expected_output，修复/审核为合成包装，不执行教学流程或独立答题。全部回显不能计作一份课程或质量指标。

最多7HTTP，前槽完整通过才后槽，S7任何结果终止；新登记起900秒含等待/处理，单HTTP60秒、每目标DNS9秒。输入总占额57344，每请求8192；输出512/2048/2048/4096/4096/2048/2048、总16896。请求≤65536字节、响应≤262144字节。无传输重试、重定向、自动模型/Provider回退、Schema修包补发或旧批续用。具体配置见policy.json，原字节与源码闭包见manifest.json。

当前公开标价占额参考$0.130048，详见pricing.json及[DeepSeek](https://api-docs.deepseek.com/quick_start/pricing/)、[AIAPI](https://aiapi.world/docs)。它不是实际账单或USD1上限；账户/推理/缓存/币种、中转路由/完整上下文/留存和取消后计费仍未知。若用户明确接受本批实际金额不设硬上限及风险，只解除这次新900秒窗口的费用门禁，不继承任何旧例外。

## 响应校验与停止

沿用源闭包中已冻结的严格wire校验，原件保持：completed、准确模型/reasoning、usage三数一致、无拒绝/截断/工具、单个assistant output_text、strict JSON/完整本地Schema和上下文ID、准确echo与分槽token上限。phase只接受缺省或final_answer。审核instructions如回显，只接受原文或已知37字符后缀；最多一个≤4096字符summary及指定同UUID的成对turn_id元数据只隔离、不信任身份；未知字段/内容继续拒绝，不新增容错。

本包更保守地要求准确Schema回显：缺Schema回显即停止，存在回显时type/name/strict/Schema矛盾即停止；不启用缺回显条件准入。即便准确echo/Schema均通过，也不保证未来强制执行或完整上游上下文。instruction回显缺失记录unknown，不把它当完整指令送达证明。

任何HTTP非200、连接/读取超时、unknown发送、来源/协议/Schema/echo/使用量/窗口/安全异常即整批终止；已发未可信校验保留unknown占额，后续保留未运行，不退款重发。七槽全部在窗口内通过才protocol_admission_complete。之后只可另备课程包，不自动发课程。

## 凭据、证据与一次性入口

scope/package/费用条件/有效窗口/既有输出/路径安全检查均先于凭据。生成只取EDUMIND_DEEPSEEK_COMPAT_API_KEY；审核优先EDUMIND_AIAPI_REVIEW_API_KEY，仅当通用Base URL准确为https://aiapi.world/v1才可沿用通用Key。Key不写入参数、事件、Git或响应；完整Key回显拒绝落盘。

每Provider一次有界空环境子进程DNS，拒绝非公网地址并固定此次IP；保持HTTPS Host/SNI、禁环境代理/重定向、retries=0。真实目录/private/tmp/edumind-p15-minimal-live-r01只创建一次，0700/0600；预约/唯一dispatch/返回/可信校验/终态逐事件落盘。不可重启，后续只读从原件重算摘要链、请求、来源、时钟、校验和汇总，不相信可改的summary；Mock不能冒充real。本机时钟验证不是外部时间或账单认证。

```sh
PYTHONPATH=backend:. backend/.venv/bin/python scripts/run_p15_minimal_probe.py --check
# 仅准确费用条件和新窗口满足后运行：
PYTHONPATH=backend:. backend/.venv/bin/python scripts/run_p15_minimal_probe.py --run
PYTHONPATH=backend:. backend/.venv/bin/python scripts/run_p15_minimal_probe.py --check-results
```

T084只交付入口/离线证据并先提交；T085在费用条件满足后领取执行。新适配及旧冻结、T038/catalog_only/H和教学标准不变。未获费用答复时不出站，不把执行器准备完成冒充真实兼容完成。验证记录见verification.txt；任务状态以根task.json为准。
