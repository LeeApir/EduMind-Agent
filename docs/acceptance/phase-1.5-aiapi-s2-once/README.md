# S2 单独一次执行

用户看过S1输出上限未证实/停止结果后明确“执行S2”，此前已明确批准S1/S2项目Prompt及Schema外传和费用不确定性。本包仅豁免S1通过的前置条件，准确S2原字节/模型/Prompt/Schema/512输出请求上限不变；不是重启原r01，不重发S1，不自动补测。

仅POST https://aiapi.world/v1/responses、gpt-6.1-sol，stream=true、reasoning=none、store=false、default。Key来自.env，不改配置。1HTTP/1生成，无重试/重定向/回退，curl40秒，响应1MiB。输入本地占额8192、输出请求512、本地USD0.035留额；并非供应商发票硬限，actual_invoice_usd未知。准确请求SHA与新入口SHA见execution-authorization.json，原包manifest同时校验。

命令：backend/.venv/bin/python scripts/run_p15_aiapi_s2_once.py --execute。无参数纯离线check，不读密钥/联网。独占/tmp/edumind-p15-aiapi-s2-once，已有即拒绝。无论结果立即终止，不接着发其他请求。接收末尾response.completed并直接JSON/完整Schema校验，输出上限回显null仍单独记未证，不为通过而忽略。完整内容需另做规划语义验证，不把Schema通过当教学质量通过。

不改业务/数据库/catalog_only/旧阻塞，不发布课程或push/merge。
