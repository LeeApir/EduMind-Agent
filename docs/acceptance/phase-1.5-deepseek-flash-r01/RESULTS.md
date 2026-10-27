# DeepSeek 官方 Flash 两例合成观察结果

2026-10-27，按用户“直接执行，不用批准”及配置专用Key后的“填好了”指令，仅执行本包。此前一次执行命令在凭据预检退出，0HTTP／0生成／未创建目录；配置后才发生以下2HTTP／2生成。无重试、重定向、回退、审核或课程调用。

| 项目 | S1 非流式 | S2 流式 |
| --- | --- | --- |
| HTTP／终态 | 200／completed | 200／completed恰好一次 |
| 请求／响应模型 | deepseek-flash／deepseek-flash | 相同 |
| 本地完整探针Schema／固定对象 | 通过 | 通过 |
| instructions | 原样回显136字符，未观察到追加 | 相同 |
| 请求／回显输出上限 | 128／128 | 512／512 |
| reported输入／输出／总量 | 147／25／172 | 205／28／233 |
| 缓存／推理token | 0／0 | 0／0 |
| store | false | false |
| 流正文 | 不适用 | 增量与终态完全一致、序号递增，无失败／不完整终态 |

返回的合成对象分别为：

```json
{"role_marker":"EDUMIND_COMPAT","result":"OK","learner_level":null}
```

```json
{"objective_source":"user_requirement","scene_forms":["text","exercise"],"learner_level":null}
```

## 能得出的结论

DeepSeek官方当前Key及`deepseek-flash`可以完成本包两例非流式／流式JSON Schema合成请求。本轮没有观察到cbbb的额外指令追加，也没有AIAPI S2中报告输出超过请求值的现象。回显正常及单次未超限不是对所有请求、真实最终上下文或供应商内部强制机制的独立证明。

这足以支持继续准备更接近真实课程契约的开发诊断；本包本身不是完整课程Schema、教学质量、审核质量或性能准入，不把两例合成对象算进课程验收分母。T038仍blocked，T039–T042未领取，生产catalog_only／H封存不变。sol尚未因此获生产审核准入。

## 未决项与费用

没有调用独立输入计数接口；响应model只是别名标签，上游日期快照未独立核实；实际发票未知。合计reported输入352、输出53、总405，算术一致。按冻结峰时输入0.30/M、输出1.20/M且无缓存优惠估算USD0.0001692，仅为参考，不冒充已扣费金额。

账本保留8192输入／640输出／USD0.01两槽全部unknown本地占额，没有按report释放预约或伪造账单结算。终态为`two_synthetic_observations_only_unsettled`，不是完整兼容或课程验收通过。

## 证据与复核

manifest SHA256：`c9476868e01c82b93c4382e8bfc0a5302399e28eb2e6f606671179c3290628b7`，314份准确源码／依赖锁／请求／方案材料保持原字节。执行登记基于明确用户指令，未声称用户独立逐哈希审阅。

私有原件：`/tmp/edumind-p15-deepseek-flash-r01`；关闭执行器后由零WAL数据库备份形成DELETE journal只读核对快照：`/tmp/edumind-p15-deepseek-flash-r01-snapshot`。原始响应不提交Git；公开结果摘要和快照文件SHA见`results.json`，无凭据正文。

```bash
backend/.venv/bin/python scripts/run_p15_deepseek_flash_r01.py --check
backend/.venv/bin/python scripts/check_p15_deepseek_flash_results.py
backend/.venv/bin/python -m pytest scripts/tests/test_p15_deepseek_flash_r01.py scripts/tests/test_p15_deepseek_flash_preparation.py scripts/tests/test_p15_aiapi_minimal_r01.py scripts/tests/test_p15_aiapi_review_probe.py -q
```

52项离线测试passed、0skip；Ruff、314冻结SHA、旧准备包、工作流及diff检查通过。无独立人类内容签核。当前单次批次已结束，不能重启该目录或自动扩大为课程诊断；下一步需独立课程兼容契约／准确生成与审核候选／预算及来源冻结。
