# EduMind Agent

启智学伴：面向数据结构学习的个性化学习系统。

## 后端（MVP 0.1）

后端固定使用 Python 3.11，并由 `uv.lock` 固定依赖版本。首次安装依赖：

```bash
cd backend
uv sync --python 3.11 --all-groups
```

启动 API（健康检查不需要 Provider 凭据）：

```bash
cd backend
uv run --python 3.11 uvicorn app.main:app --host 127.0.0.1 --port 8000
curl http://127.0.0.1:8000/health
```

运行测试：

```bash
cd backend
uv run --python 3.11 pytest
```
