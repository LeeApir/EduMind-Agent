# 目录版工程验收（不含人工内容批准）

| 独立组件 | 完整分母 | 结果 |
|---|---:|---|
| 两模板质量矩阵 | 100 | 100/100；20种输入实际渲染、80次审核缓存校验 |
| 10节点冷/暖首屏 | 20 | 20/20；HTTP P95 0.107111s，可读正文P95 0.959118s |
| 缓存点击到可播放 | 100 | 100/100；P95 0.1506s，最大0.2274s |
| 新缓存真实Worker到播放 | 20 | 20/20；P95 8.0897s，最大8.1015s |
| 核心浏览器旅程 | 10节点/30资源/30题 | 评分、重复不刷掌握度、预设/刷新返回、4个媒体下载、本人笔记、已登录跨owner/CSRF/动态拒绝/撤回通过；另有2次真实Worker绑定 |

执行：`backend/.venv/bin/python scripts/run_catalog_acceptance.py`（v1–v4）、`backend/.venv/bin/python scripts/run_catalog_core.py`（v5）；最终 `python3 scripts/verify_catalog_acceptance.py` 离线核验通过。135项前端测试、typecheck/build、定向ESLint及Ruff通过；6项离线分母/组件闸门测试通过。

[质量原始证据](mvp-0.3-catalog-20261003-v2-quality.json)、[完整性能矩阵](mvp-0.3-catalog-20261003-v4-result.json)、[独立核心旅程](mvp-0.3-catalog-20261003-v5-core.json)分别保留。每次执行前冻结代码/配置/内容hash；[v5协议](mvp-0.3-catalog-20261003-v5-protocol.json)明确引用未变的质量与性能组件，核验同一生产工作树/内容/模板hash及原执行器快照，不把v4失败的核心旅程改成通过。v5改用真实Chromium fetch验证Secure Cookie身份，生产Secure/HttpOnly未变。

首次质量8槽RENDER_UNAVAILABLE（底层原因未记录）、localhost502、401正文未读取、队列定位器歧义、Node HTTP客户端缺Secure Cookie均保留在旧批次。401及练习/路径404响应清理有生产修复与3条回归测试；其余为执行器/环境问题。v3保存停止记录及未运行槽，未将部分样本拼入完整性能矩阵。

仅适用于本机单并发和冻结工作树；冷首屏是新owner/浏览器/单元，API/DB进程仍热，HTTP口径见冻结协议。测试批准为TEST_ONLY，真实课程仍待人工签核。Provider key未加载，后端非回环出口与浏览器外部请求尝试均0；新增Provider 0、累计2033/2500。T033仍blocked、旧指标/成绩/冻结/.env hash不变；不宣称动态质量或正式课程发布通过。
