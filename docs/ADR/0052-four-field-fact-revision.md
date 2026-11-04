# ADR0052 补充提案：F01/F02四字段事实修订

2026-11-04。准备实施已由本轮指令授权；真实调用及本批C2仍待准确批准。T108仍未完成，T102保持blocked；历史冻结包/恢复父稿/失败/STOP不变。

## 相对既有契约的唯一教学修复例外

原规则只允许普通教学措辞修复，不允许事实问题自动修复。本提案为F01/F02单独允许一次**模型事实纠错**，不是挪用旧额度：新批次 `head-goal-fact-r01`，最多1 HTTP，新窗口600秒，在用户确认终端隐藏输入就绪后才登记。规划和全文生成各0，旧r03不恢复。输入父候选固定7fde0859549aef0e0e64415880ed67e541dbf3f0d302e7eeae6faf76090b0779，包含同版代码、事实、轨迹、规划依据和原两条审核意见。

远端 `head-f01-f02-four-text-v1` 只包含四个必需字符串：paragraph_1_text→paragraphs[1].text，paragraph_5_text→paragraphs[5].text，paragraph_6_text→paragraphs[6].text，learning_summary→learning_summary。不得返回全文或额外字段；原完整教学Schema不变。程序deep-copy准确父稿后按固定路径覆盖，原引用、其他文本、题干、解析、步骤、代码、事实、轨迹、参考答案和payload全部保持原值。严格重复键拒绝，不把之前相同重复恢复扩大到这次响应。

新候选记录父摘要和独立新摘要，仍是r03原文＋模型四字段修订，不能称全文重新生成或原首稿结构通过。程序重新装配全文和head-state.text_alternative，两者统一读新learning_summary，不对某一页面位置单独手改。

## 请求、凭据、费用及证据

固定 api.deepseek.com/responses，deepseek-flash，Responses/json_schema，reasoning none，temperature0.2，stream/store false，max_output_tokens4000，无工具/自动重试/回退。请求字节上限131072，输入本地预约139264 tokens，完整响应上限2MiB，I/O90秒。实际请求/Schema/配置见准确包，不用示例请求代替实际请求。

复用既有域名/DNS固定校验、逐块加密fsync原件保存、响应phase适配（仅缺省/final_answer）、严格JSON/Schema。只在新的0700私有目录运行，raw.key0600只加密正文；Provider Key仅getpass隐藏输入，不读项目.env或凭据环境、不写聊天/argv/记录。尝试前写唯一attempt，响应先留全原件再解析；成功也写STOP，失败保留failure及ACTIVE/partial/unknown，禁止第二次请求。新批准只适用于准确manifest。

本批C2需新接受：单前台请求尽力停止，最后检查后暂停仍可能迟发/继续计费；没有可验证金额硬上限，本机原件没有独立抗回滚保障。Ctrl-C或独立写新目录STOP均不承诺撤销已发请求。T102反例不解除，不新建监督器。

## 审核、应用与停止

程序只作完整结构/事实ID/场景/轨迹/固定差异检查，不能签语义pass。调用后交完整原输出、四处新旧差异和新候选全文，由评估助手重评整个课程，特别是F01/F02、作用域/返回值/可达性/答案及泄题。失败即保留准确位置与影响，不自动追加调用或手改。

独立pass后才接入实际应用的新不可变版本，保留父版和既有作答，使用原私有答案和播放器/反馈；再检查页面正文/演示替代文本同步、13步/四题及刷新。必要来源投影为 `evidence_kind=targeted_fact_revision`、prompt_version=head-f01-f02-four-text-v1、parent_digest准确父稿，显示“模型四字段事实修订”，不能沿用“仅程序格式恢复/新调用0”的父版标签。这个来源扩展仅服务该候选，不改变教学输出Schema、正式签核或掌握度权限。

本轮准备不改当前课程/公共API或数据库，不伪称页面接入已通过；真实候选及独立pass后实现上述最小来源准入接点并做实际页面验收，不需要再调用模型。未通过前T108不done，完成后停止交评估，不启动其他主题或T038。
