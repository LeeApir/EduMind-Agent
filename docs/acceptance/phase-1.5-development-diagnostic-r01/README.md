# T037 有界开发诊断准备（blocked，未完成）

用户明确继续T37；随后选择“用env里的”。仅提取.env的公开Base URL、模型与structured_transport，未输出、持久记录或使用Key，不发模型/型号探测。候选公开配置：`https://www.cbbb.fun/v1`、`gpt-6-luna`、`responses_json_schema`；reasoning_effort按当前configured_provider_adapter默认`none`。未自动沿用旧DeepSeek生成/Luna审核路由、旧预算或旧标签。模型是本中转的别名，实际版本/计费和总输出上界没有证据，不能标已验；公开站点文档读取未成功，限定该站点的型号/价格搜索亦无结果；未访问/v1/models或发生成请求。

已准备courses.json十二槽/六画像对/六主题，known自述与unknown保留未知，场景范围覆盖1–8，明确代码/练习/状态图及0/1/多提及建议不当节点核定；negatives.json两工程负例另计，固定分母不把支持域失败改负例。probes.draft.json为10严重/10正确的**助手草稿**，覆盖定义、步骤、代码、复杂度、答案及跨场景一致性；每个human_review=null，绝无“人工已通过”占位记录。review-sheet.md供真人逐项核对课程预期/probe、采纳或修改并登记实际评测人/时间/准确标签。未读取H内容，旧A/G/P/D只保留历史开发归属、未导入本批真值。

budget.proposed.json是提案：单候选/单批，14课程及负例操作×13尝试+20审核probe×1=202请求；输入3440000、输出832000token；CNY30=30000000微元硬上限、10800秒。课程每操作600秒/200000输入/48000输出、每调用120秒/32000输入/8000输出，仍受原课程共享40尝试/600000输入/144000输出及并发上限；probe不进入学生可见产品。请求包括所有修复/重试/已发送未知；不加探测、静默回退、第二候选或追加抽样。30元是建议停止上限，不是供应商报价或费用预测；未知价格不按0计费。实际授权仍0。

scripts/acceptance_support/p15_diagnostic_ledger.py是**独立SQLite预算内核，不是已连接的真实执行器**：BEGIN IMMEDIATE在发送前持久预约，重复批/尝试禁止重发，完整输入/输出/费用预留，确证收据才按实际用量结算，not_executed不退请求次数；unknown保留全额并持久停止，晚结果只能结算不恢复；同批配置冻结，墙钟与单调时钟越界/异常、调用期限、严重错误/越权/独立性污染/率门槛不可达均停止，收据append-only。此内核只核对可信批准记录的摘要绑定，不证明人类签名真实性；最终组装器必须在仓库的准确批准登记中验证身份/证据，不能把CLI参数当授权。尚未注册live/authorize命令。

实际：`backend/.venv/bin/python -m pytest scripts/tests/test_p15_diagnostic_ledger.py -q --junitxml=/tmp/edumind-p15-t037-ledger-r01.xml` **21通过，0失败/skip**，涵盖缺/错授权、持久重开/重复启动/重复发送、三类预算/请求计数、unknown与晚结算、墙钟/回拨/漂移/NaN、配置变化、证明缺失/用量越界、五停止原因、四线程并发。测试批准为显式TEST_ONLY虚构数据，只在pytest临时库生效，无真人批准记录或真实请求。Ruff三新增Python文件通过。T035/T036离线原件、41批准/50历史、用户原README完整性及工作流/diff检查通过。

`python3 scripts/check_p15_development_diagnostic.py --prepare`生成本准备包及259个源码/Prompt/schema/锁文件/图结构SHA；不包含.env。`--check`仅离线读文件，输出PARTIAL/BLOCKED并**退出2（不是通过）**，核对材料分母、预算求和和源码完整性后明确缺项。此manifest是未批准准备记录，**不是最终冻结执行包**，后续候选/标签/执行器确定后另冻结准确r02，不覆盖本轮原件或追认成绩。

T037尚缺：本中转模型版本/别名映射、准确价格/币种及推理token在内的输出上界依据；probe人工构造/核定及准确标签签名、课程预期确认；据此完成真实适配/逐槽执行器绑定和离线字节/预算核验。T038才另请批准最终准确包/预算/真实执行；T037不以缺T038执行批准本身冒充完成设计的理由。收到资料后恢复T037，完成全量验收及Task-Completed提交；当前仅保存准备进展，无完成标记。

依据ADR-0027已批准contract§3/§6：人工先标后跑，模型标签只作草稿，准确模型/版本、费率/总输出边界缺失不能启动。根task.json保持T037 blocked/completed_at=null，T038–T042 todo。生产catalog_only、真实Provider0、H封存、用户无关改动保持，无push/merge/部署。
