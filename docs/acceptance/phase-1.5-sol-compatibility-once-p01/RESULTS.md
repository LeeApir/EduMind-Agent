# p01单次合成兼容结果

用户“执行”后按直接指令冻结新包479937db并调用一次。实际1 POST/HTTP200，耗时5.009秒，无重试/重定向/补样，无课程/PG调用；本轮此前6次保持，累计7次。报告输入834、总输出203、总计1037；两轮课程探索加本次累计输入19355、总输出8306，实际收费未知。token与金额不限，不用报告用量冒充供应商硬上界。

请求/回显reasoning均low，报告推理token为0；本次没有验证非零推理元数据路径的真实兼容，该路径只有离线规则测试与此前r02原始观察。系统指令仍回显准确37字符编码助手后缀，本次仅按明确限定规则接受，upstream_context_verified=false。

最终JSON静态Schema、source_sha256、以source为根的准确引用及原文quote校验通过；唯一问题正确定位/scene/items/1/text，指出按下标直接读取应为O(1)，返回revise/major。正确对照未被标记。expected/gold未发送；两句题目与期望均由助手构造，非独立人工标签，不代表严谨审核质量统计。

结论：**这个准确合成请求通过兼容验证**。不能把1错1对扩展为整批审核准确率，不能声明全部课程/20审核探针或T038通过，也不自动启动下一槽。r01/r02原失败、unknown账本及收费未知保持；生产模式未切换。

44执行器/兼容离线+3只读结果回归共47项passed/0skip。只读核对命令：

```sh
backend/.venv/bin/python scripts/check_p15_sol_compatibility_once_results.py --check
```

实际请求/dispatch/状态/原响应和summary私有保存于/tmp/edumind-p15-sol-compatibility-once-p01；Git仅统计与SHA，未输出或解密任何加密推理字段。evidence-index.json与results-manifest.json可复核。独占输出目录已消费，本包不再执行。

下一步如继续课程诊断，应准备采用已验证窄兼容规则的独立新课程执行包、精确源码和累计预算/原截止，保留助手复核与教学门槛，另获该准确范围授权；本次单次批准不扩展到课程外发。原13:21:21截止不自动延长。
