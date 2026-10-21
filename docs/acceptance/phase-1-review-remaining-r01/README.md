# 其余五类审核诊断r01（零调用冻结）

按用户表格顺序仅五槽：assessment-gap → fact-contradiction → reachable-safety → gap-and-safety → trace-complete。原suite-r01对应五条完整case及wire逐字相同，不再调用plan-only-gap或分散覆盖，不冻结整套七条。历史plan-gap单例符合预期仅作参考，不伪造实际人工签核或正式验收通过。

固定deepseek-flash/low/8192总输出（含思考）/60秒/温度0.0，保留原输入、原始目标、Prompt、Schema、锚点、学生材料和判据。继承已离线验证的安全Schema位置诊断，记录首错路径/白名单字段名或未知名摘要，不保留正文值、不放宽Schema、不预猜旧额外字段。Provider原配置text.format=json_schema/name/schema保持，不添加strict或换模型。

|顺序|样本|具体准入判据|
|---|---|---|
|1|assessment-gap|needs_human，准确指出过程问题未考；现有讲解和key_steps已明确教total2/7/16和i3退出，不能误报成未教；findings空，不编造fact|
|2|fact-contradiction|具体定位讲解声称sum返回18，与数组/实际循环/题目支持16矛盾；保留major/severe fact和reject|
|3|reachable-safety|长度3合法0..2，实际代码return a[4]可达越界；major/severe code_safety并reject，不执行不安全代码|
|4|gap-and-safety|同一真实a[4]越界仍major/severe code_safety和reject；教学/测量缺口不能掩盖严重错误或全部转人工|
|5|trace-complete|pass，五项coverage.checked齐全，findings/unchecked/unresolved空；不得附带调用示例、动画或其他图谱目标误报|

每条均核对完整性与实际语义；路径/类别/路由相同不等于具体检出正确。技术/结构失败自动halt；助手/人工识别语义误报或漏报时也必须停止、不签continue。前一条必须有proposal与实际receipt摘要绑定的真实用户continue，下一槽才允许发送；不预签任何结果。末条后停止，不能自动进入正式验收。需要汇总全部五条真实证据，未运行项明确记未运行，历史正例不能代填本包对照。

准确预算最多5次/11.235560元保守预留，每槽1次，无重试/修正/额外探测/回退。输入每槽上界1048576+实际wire字节数，总输出8192，峰值未缓存价2/8元每百万；不是消费预测或实际账单。独立运行批准/标签与私有账本，不继承旧剩余6槽、预算或失败状态，不改生产catalog_only默认，T040保持blocked。

准备：backend/.venv/bin/python scripts/prepare_review_remaining.py --write。执行：backend/.venv/bin/python scripts/run_review_remaining.py --run-one（每次最多一槽，未批准则Key/DNS/新目录前拒绝）。当前真实批准/标签/账本均未创建，Provider0。
