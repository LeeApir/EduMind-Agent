# T109零调用定向检查

2026-11-05，执行Codex。结果只支持接线与准备，不是新课程教学效果。

| 实际命令/检查 | 结果与范围 |
|---|---|
| `PYTHONPATH=backend:. backend/.venv/bin/python -m pytest -q backend/tests/test_head_course_reuse.py -k 'not actual_entry_and_private_application'` | 15 passed：实际规划请求含准确B/同版依据，正常/澄清/错来源/错引文/错场景引用/选A拒绝；strict首稿、相同重复恢复、冲突/范围外/截断/未知phase拒绝；审核驱动动态位置、text+fact_ids、父稿/材料不变、邻段复制/超范围拒绝；旧请求与最终候选及旧公共Schema原样复核 |
| 专用本机PG，最小`/tmp/edumind-t108/env.json`仅测试配置；同文件`-k actual_entry_and_private_application --tb=short` | 4 passed（原四条）+1 passed（新增修订4001 token超限）：实际API创建/规划持久/原发送入口MockTransport+加密回读→直接/恢复/修订三条准入；未知phase/用量超限修订失败保留准确错误码及STOP/ACTIVE且二次发送拒绝；私有答案/正确反馈/刷新绑定；请求/审核/材料/响应篡改拒绝。HTTP mock均明确offline_fixture，新真实Provider0 |
| `backend/.venv/bin/mypy --follow-imports=silent` 五个变更业务源 | passed：新复用服务、generation、materials、本地planner、planning持久化；范围不扩展到无关模块 |
| 变更Python源/测试/脚本`ruff check`；`pnpm --dir web build`；两变更前端源`eslint` | passed；构建包含vue-tsc。仅来源UI、API类型改动，无播放器行为改动，无需重跑既有全站回归 |

首次检查失败也保留说明：恢复测试发现共享PilotError没有`.code`属性，改用其固定错误码字符串进行精确判断后通过，未放宽断言；首次PG因沙箱回环socket权限失败，允许本机数据库连接后重跑；修订分支发现旧DB `sent_attempts≤1`约束，改为最终生成行只记最后一次请求，父稿/之前请求及用量留完整lineage，不改表/不改约束。上述都发生在真实授权前，无Provider调用。

准备包重建/CLI inspect、workflow/diff/历史目录只读不变和独立准备评估结果在本轮交接时登记。真实浏览器新课程学习验收待另批真实生成后执行，不能用上述API夹具替代。

独立准备审查发现共享历史wire按8000封顶，修订请求实际上限4000；在新记录适配显式按request.max_output_tokens拒绝，新增实际入口4001 token拒绝、保留原件/REUSE_USAGE/STOP及重试拒绝通过，未修改历史wire。包清单生成器首次list与set类型不匹配已修正为set，随后生成/check/inspect通过；无真实调用。
