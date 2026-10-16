# plan-only-gap单次位置诊断包

先完成零调用契约复核：见../phase-1-plan-gap-contract-audit/audit.json。没有明确字段/层级/类型冲突；unresolved是字符串数组，顶层禁止额外说明字段。实际wire没有few-shot审核输出示例；合成输出示例仅离线校验、未送模型。Prompt的findings only字样不够精确，但上下文是不提供修复，并未明确要求丢弃Schema必填字段；当前不据此修改Prompt。Provider Responses配置json_schema/type/name/schema与官方已列字段一致；未额外加入未列明的strict配置，不把工具Beta strict混作响应格式开关。文档配置一致不保证Provider内部严格约束。

仅plan-only-gap:candidate，完整原case及41439字节请求逐字不变，wire SHA5cfdfa15cc68e61959d10e5ef60d2a6e8bd53e0f17e24bc4872e8df3fa46798b。deepseek-flash/low/8192总输出（含思考）/60秒、目标、Prompt、Schema、判据、温度0.0不变。新诊断记录首个Schema违规的安全位置/字段名或未知名摘要，不记录原文/字段值，不放宽校验、不删除字段或重分类。

最多一次/2.245566元保守上限，输入上界1048576+41439=1090015，总输出上界8192，按峰值未缓存单价2/8元每百万计算。非实际消费预测；预留不是账单，Provider违反假设时硬停。无探测/重试/修正/回退，不冻结整套七条，不继承旧6槽。独立标签/运行批准与私有账本，成功或失败之后都停止，任何human continue也不能增加第二次。

判据仍为needs_human，具体指出学生可见循环状态与退出边界教学支持不足；计划轨迹不算学生交付，不能把缺调用方示例编造成fact。完整性与语义分别核对。Schema失败仅定位首个问题，不能推断模型语义；旧额外字段继续未知。之后只依据新证据决定修复，不预先改Prompt、Schema或Provider参数。

入口：backend/.venv/bin/python scripts/run_plan_gap_location.py --run-one。准备：backend/.venv/bin/python scripts/prepare_plan_gap_location.py --write。当前未授权真实发送、无run-approval/labels-human/新私有账本。旧suite-r01及其他运行保持停止，生产catalog_only不变，T040未完成。
