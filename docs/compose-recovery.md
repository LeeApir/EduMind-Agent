# Compose 重启恢复验证

T033 在本地 OrbStack Compose 环境验证持久化资源恢复。该验证只重启 `postgres` 和 `api` 容器，不执行 `docker compose down -v`，也不删除命名卷。

## 可重复命令

```bash
docker compose build api
docker compose up -d api
docker compose exec -T api uv run python tests/compose_recovery_check.py seed
docker compose restart postgres
docker compose ps
docker compose restart api
docker compose ps
docker compose exec -T api uv run python tests/compose_recovery_check.py check
```

`seed` 创建一个归属新匿名用户、审核状态为 `passed` 的正式资源，并将一次性测试会话写入 API 容器的 `/tmp`。`check` 在重启后以该 owner 调用正式学习单元与资源读取接口，断言均为 `200`、资源仍为已审核状态且内容可读。命令输出不包含会话 token。

## 边界与注意事项

- 这是本地开发环境的恢复检查，验证 PostgreSQL 命名卷、Alembic 迁移和 owner-scoped 读取；不替代生产备份演练。
- 检查生成的已审核资源会保留在开发数据卷中，避免测试通过删除数据来掩盖持久化问题。
- API 容器 `/tmp` 中的临时测试状态只供同一容器的 `restart` 使用；若执行重建或 `down`，应从 `seed` 重新开始。
- 导出备份、保留周期、异地存储和恢复演练由部署环境负责，详见根目录 README 的备份说明。
