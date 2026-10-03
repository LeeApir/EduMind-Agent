# T046 签核交接

Lee 已明确实际审阅并批准 `linear-course v0.1.0`，摘要 `92bb0dd4778391e23aae978b8a411b466d8b5988d1cff61cff01654604af21a1`。按 ADR-0007 保存独立签核、30资源及demo摘要和受信 allowlist；确认登记时间为 `2026-10-03T15:30:26+08:00`，原审阅起止时间未知。旧 pending 文件和冻结证据未覆盖。

`python3 scripts/verify_catalog_release.py` 返回 `HUMAN_APPROVED / Lee / publishable=true`，退出0。v3独立隔离PostgreSQL/HTTPS TestClient核验6项测试全部通过：实际签核版本原子登记与幂等、10节点/30资源来源hash/30题评分、重做不刷掌握度、预设演示恢复、两种T045真实缓存动画的MP4/SRT下载、owner/CSRF及撤回后的读取/计分/媒体/重新批准拒绝。仅测试库登记，最终测试版本已撤回；未部署到开发或生产数据库。

v1/v2结果与各自冻结协议保留：v1误认为资源REST包含`catalog_release_id`，现改为实际DB查询30资源并核对来源/hash；v2以空answers验证撤回，先被schema以422拒绝，现用合法原答案核验404。两次均是新增测试与现有契约不一致；未修改生产代码或课程内容。

离线预检/答案一致性16通过，19个显式Docker项目未启用而跳过；本轮数据库测试6通过，无跳过；Ruff和原T045冻结/保护hash核验通过。完整命令及结果见 `mvp-0.3-catalog-signed-verification-20261003.json`，最终原始结果为 `mvp-0.3-catalog-signed-v3-result-20261003.json`。

本轮不是新浏览器/Worker/P95基准；原T045实际浏览器和真实渲染工程证据独立保留，不重评分。新增Provider请求0，累计2033/2500；T033保持blocked及旧成绩不变。T046完成后停止，T034仍todo；未push、merge或部署。
