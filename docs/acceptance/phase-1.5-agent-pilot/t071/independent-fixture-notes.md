# T071 独立手写批次事件fixture

作者：pilot_independent_evaluator，身份assistant（非human）。依据用户准确批准d82cb8e的限定T071离线任务，由独立助手在读取新Reducer实现之前编写。仅查看原Journal事件接口及批准提案；未读取将新增的Reducer实现或独立e02真值，未运行引擎、Provider、C、网络或状态模拟器。

文件：`scripts/tests/fixtures/p15_pilot_batch_manual.json`。版本`p15-pilot-batch-manual-v1`。SHA256：`fcec4421aaf162af0d9e6c3a8da044cd5fd7dc748f73babb52374dbecfc4452c`。

## 组织与独立期望

事件池中的每个kind/payload/epoch、前缀和病例扩展顺序、expected状态/拒绝位置/语义理由都是显式手写。序列化只使用固定字典和重复字符SHA占位，不用Reducer、生成器或待测代码推导结果。测试封装只可按prefix+append展开事件ID并补seq/摘要链，不可重新计算或更改expected来适配实现。

正常路径是一个slot的B/C两臂槽：B生成和审核2调用，准确结果的独立accept后C才开始；C规划/内容/审核3调用，再准确accept后收集完成。预期最终position=2、reserved_calls=5、trusted_settlements=5、independent_accepts=2、pending为空，均由接口语义手算。model pass本身的B结果应暂停position=0。

窗口固定1000≤epoch<11800，跨度10800秒，覆盖原三小时；正常路径不延长窗口。允许同一时刻的多个receipt，所以时间规则是非递减，而非严格递增。反例单列截止等号、起点前以及窗口内倒序，不把“都在窗口内”当成“时间因果正确”。

停止后仍允许已发送ticket的迟到wire观察，未知ticket不可冒充迟到；停止不得新预约/发送/可信结算/接受推进。已有候选在窗口耗尽后可用late_slot_result保留，不能打开有效检查点或增加成功；给未运行C臂记录迟到候选必须拒绝。stopped可保留历史pending源信息，fixture不强制删历史，但不能据此重新授权。

## 范围与限度

本fixture只核批次生命周期，不执行模型、代码或课程，不承诺合成SHA有真实原件、不把synthetic报告checks当教学通过，也不替代逐槽Replay/严格角色Schema/完整原件摘要检查。正例中target/transport采用现有接口允许的事件顺序，使用mock及固定合成公网地址，无DNS。

覆盖正常B→accept→C、模型通过暂停、独立stop、workflow stop、迟到观察/候选、accept前出站、跨臂/跨槽、重复发送/结算、未发送结算、错误报告摘要/臂、stop后新请求/推进、缺失开始/检查点、全窗口边界、时间倒退和同批重启。小fixture不覆盖全部90请求组合，相关额度/逐槽限制仍须开发侧既有回归和最终独立代码审阅。

当前只完成独立fixture准备，不作Reducer通过结论，不解除T069阻塞，不选e03，不授权真实调用，亦不宣称T069/T070完成。等待限定候选完成后，按本轮授权仅作一次正式独立复审。
