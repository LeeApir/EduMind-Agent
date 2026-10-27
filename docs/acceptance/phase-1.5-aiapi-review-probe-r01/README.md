# AIAPI 审核建议模型合成探针 r01

用户明确要求“测试它能否识别教学错误、误报是否严重”。本轮仅新编写12条短样例（6正确/6错误），使用gpt-6.1-sol/Responses进行1次非流式批量审核；不是正式审核准入、教学质量验收或生产切换。

- 负载：request.json，含新编写审核指令、cases.json及简单审核结果Schema，不含项目Prompt/生产Schema/真实学情/代码仓库。gold.json预先冻结且不发送；标签由本助手编写，不冒称人类独立签核。
- 栈、单链表、动态数组、二分、C数组边界、BFS六类，各有正确与错误片段，固定种子打乱。成对/单批结果可能相关，不据此估计生产准确率。
- 1HTTP/1生成，无重试/回退/重定向，60秒curl/62秒进程、1MiB响应。输出请求1536，本地输入预约8192，本地USD0.05（公开参考包络0.04352）；服务端输出限额和真实费率未知，不是账单硬限。
- 本地完整Schema/唯一ID/引用精确匹配校验；错误识别tp/漏报fn/正确误报fp/正确不报tn/不确定/格式失败分别报告。6错误、6正确固定分母；格式失败不剔除样本或提取局部JSON追通过。观点或风格偏好不算教学错误。模型可读理由由助手逐条核对，非独立人工审核。
- 预设判断：若任何明确错误漏报或正确例误报，报告具体样例；即使6/6识别、0/6误报也只表示本轮简单探针表现，不获生产权限或统计可靠性。没有通过后自动增加样本/改Prompt/切模型。

执行：backend/.venv/bin/python scripts/run_p15_aiapi_review_probe.py --execute；无参数纯离线SHA/Schema检查，不读密钥或联网。独占/tmp/edumind-p15-aiapi-review-probe-r01，不能恢复或重跑。

验证：backend/.venv/bin/python -m pytest scripts/tests/test_p15_aiapi_review_probe.py -q（执行前6passed/0skip）；Ruff通过。结果写results.json、RESULTS.md，旧包和catalog_only/T038等阻塞不变，不push/merge/部署。
