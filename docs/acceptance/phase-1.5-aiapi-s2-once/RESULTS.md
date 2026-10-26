# S2 单独一次结果

实际1HTTP/1生成，HTTP200，curl正常退出，response.completed恰好一次，增量正文与终态正文完全一致。没有重试/修改请求或再生成。

## 内容与协议

生成了可读中文栈课程规划，JSON语法可解析，但生产完整Schema失败，共10个校验错误（含条件/联合分支的派生错误，不视为10个独立缺陷）。主要实质错误：objective.source写自然语言而非user_requirement/planner_suggestion；scene.forms写讲解全文而非text/code/exercise/visualization；无需澄清分支的reason不为null、source_keys不为空。

请求max_output_tokens=512，终态usage报告output_tokens=802（其中reasoning128），超过请求值。服务端自报数据并非独立计费核实，但本次已经不能只以null回显解释为“上限未知”。终态缺少model/instructions/max_output_tokens/store字段，这只能记缺失/未证，不能误称模型被替换或教学指令被改。

报告input1291（其中缓存640）、output802、total2093，算术一致。按公开输入$2.5/M、输出$15/M且缓存不打折估算USD0.0152575，低于本地0.035预约；真实Key费率及发票未核实，actual_invoice_usd=null。整槽留额保留unknown；此前S1的0.015亦保留，两槽合计0.05无自动退款。

结论：S2真实复杂规划Schema未通过，输出请求上限与报告不符；该模型/中转不能据当前证据作为EduMind可靠结构化规划后端。中文内容看起来合理不补结构合格分子；不修改Prompt/Schema追通过，不自动改成宽松JSON或重试。catalog_only/旧验收阻塞保持，T038仍blocked。

去敏完整事件与准确校验路径见results.json。原S2字节与r01所有冻结文件不变；本次只依据“执行S2”单独新授权，原r01不重启。原始私有执行收据位于/tmp/edumind-p15-aiapi-s2-once/results.json。
