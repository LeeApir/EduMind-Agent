# 人工签核记录

`linear-course-v0.1.0.json` 记录 Lee 对 manifest digest 的实际人工批准；授权原文在 `docs/acceptance/mvp-0.3-catalog-human-signoff-20261003.json`。`reviewed_at` 使用本次明确确认的登记时间，未推测原始审阅起止时间。

本地受信配置为 `data/course_catalog/release-allowlist.json`，发布预检运行 `python3 scripts/verify_catalog_release.py`。预检只读，不登记数据库或部署。部署仍需另行授权。

`linear-v1/review-status.json`、README 和旧审核 HTML 是冻结的待审核历史快照，保持原样；当前批准依据是本目录的独立签核及 allowlist。内容发生变化后旧签核失效，需新的版本和人工批准。撤回的数据库版本不能用旧签核重新批准。
