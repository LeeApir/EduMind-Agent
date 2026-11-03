# T105：本批最终消息 phase 的限定兼容

2026-11-03。用户审查指出 Responses 的最终消息可包含 `phase: "final_answer"`；原共享 `wire.validate` 对该字段报 `WIRE_MESSAGE`。本次仅修正本批的响应适配，不新增真实探测或教学字段，不恢复 T102，不建设监督器。原 T104 准备提交 `68bb948` 和原 manifest 保留，见 [manifest-before-t105.json](manifest-before-t105.json)，SHA256 `1f2da5aba5531ce173c3279e07335bf3845e6c490e4c011e19d0e8f22c659c8c`。

## 精确接受规则

适配版本 `limited-c-message-phase-v1`，仅作用于 `output` 中 `type="message"` 的对象：

- `phase` 缺省：沿用现有消息校验，不推定为某个远端阶段，观察记录为 `absent`。
- `phase` 为准确字符串 `final_answer`：记录实际值，验证该白名单后仅在内存校验视图中删除这一字段，再交给**原样未改**的共享校验器。
- 其他值（包括 analysis、commentary、final、空串、带空格、null、布尔/数字/容器）一律拒绝；其他未知消息字段仍交原校验器拒绝。不是忽略所有未知字段。

原始响应仍先逐块加密/fsync并回读核对，之后才进入适配与结构校验。适配不覆盖原件、不重写 body 收据长度/摘要、不改变模型正文。即时生成/修复与已保存父候选重放均调用同一适配函数，不能只修首版而让修复父链无法回读。

## 契约和准确包影响

这是当前拟议批次的响应元数据白名单变化。教学 Schema、Prompt、两份初始请求字节、样例、预算、原件/停止条件保持不变；`candidate.json` 增加响应适配版本，manifest 更新并绑定本说明和旧摘要。旧共享 `scripts/isolated_diagnostics/p15_pilot_wire.py`、历史冻结包及失败记录不改。原 ADR0050 A–D 的更弱停止/保管保障和当批C2/窗口仍待准确决定，本修正不替代这些授权。

## 最小验证

仅运行本批实际入口的 MockTransport 回归：缺省/final_answer 成功并产生完整候选；解密原件逐字节等于含原始空白/phase 的响应；body 长度/摘要准确；父稿重放及一次修复两路径通过；非法阶段和额外未知字段拒绝且原件保留、STOP及占额保持、不导出候选。并验证历史共享校验器仍对 final_answer 字段报 WIRE_MESSAGE。

装配HTML/JS、教学Schema和模型请求没有变化，复用T104浏览器证据，不重跑无关浏览器/后端/监督器矩阵。测试均为合成，不计真实模型成功。

完成本限定修正后只交回准确执行授权决策；真实调用仍为0。

实际结果：`PYTHONPATH=backend:. backend/.venv/bin/python -m pytest docs/acceptance/phase-1.5-limited-c-preparation-t104/test_preparation.py -q` **24 passed**；本批Ruff、`prepare.py --check`、clean-env `-I execute_once.py --inspect`、工作流和diff检查通过。对比提交68bb948，output-schema、两份初始body/输入和course-template逐字节不变；共享wire无diff、旧manifest原样保存、104个旧Task对象未变。未重跑未受影响的浏览器检查，无真实调用。
