# T004 API 与 SSE 契约交接

[OpenAPI 0.3.0](../api/openapi.yaml) 在保留现行 MVP 0.1/0.2 路径的基础上，固定已批准 [ADR-0004](../ADR/0004-trusted-animation-jobs.md) 和 [ADR-0005](../ADR/0005-classroom-session-and-scene-version.md) 的 MVP 0.3 接口。本任务只交付设计契约与静态测试；新增运行端点仍由 T012–T028 实现，不把 OpenAPI 版本当作服务已上线。

| 范围 | 路径入口 | 关键语义 |
| --- | --- | --- |
| 动画 | `POST /api/learning-units/{learningUnitId}/animations`、`/api/animation-jobs/{jobId}` 的查询/取消/重试/事件 | owner绑定、同键同摘要重放；Job终态及取消竞态；GET EventSource 持久ID、Last-Event-ID、410快照恢复 |
| 媒体与导出 | `/api/animation-media/{mediaId}/mp4`、`/srt`；`/api/learning-units/{learningUnitId}/notes.md` | 只读owner已审核结果；Markdown无多视角仍可导出，下载不调用模型或发起渲染 |
| 课堂 | `POST/GET /api/learning-units/{learningUnitId}/classroom` 显式建立默认专注会话并读取快照，另有消息/模式/控制 | Cookie+CSRF+幂等，If-Match revision；POST fetch SSE临时token与已提交消息分开；`GET /api/classroom-operations/{operationId}`查断线状态；关闭角色后旧generation失效 |
| 场景与演示 | 场景`reexplanations`、`debate`、退出及反馈 | 基版本CAS、审核后发布；结构化单次SSE演示；显式反馈绑定已发布结果 |

所有新增写接口统一使用会话Cookie、同源Origin、`X-CSRF-Token`、`Idempotency-Key`；适用的课堂写接口加`If-Match-Classroom-Revision`。幂等命中先于版本冲突检查。匿名/跨owner读取与猜测ID统一隐藏为404。Job事件以Job内递增ID持久重放；课堂消息用独立单调`message_cursor`，临时POST token不保证重放；流开始后的审核错误由content_retracted/error/done事件表达，无法再改HTTP状态。`content_retracted`是ADR-0005已批准的临时内容失效信号，不改变ADR-0002其他待批边界。

稳定错误码新增`JOB_STATE_CONFLICT`、`CLASSROOM_VERSION_CONFLICT`、`SCENE_VERSION_CONFLICT`、`EVENT_CURSOR_INVALID/EXPIRED`、`MESSAGE_CURSOR_INVALID/EXPIRED`、`RENDER_UNAVAILABLE`、`MEDIA_NOT_READY/UNAVAILABLE`和`REVIEW_UNAVAILABLE`等；详情在OpenAPI Error枚举与响应描述。MP4支持授权Range，SRT不声明Range；媒体默认inline供播放器使用，download=true改attachment；三类导出使用服务端安全文件名、nosniff及private/no-store，Markdown和SRT使用UTF-8。能力不包括P1多模型、BYOK或三Agent真并行。

验证入口：`cd backend && UV_CACHE_DIR=/private/tmp/edumind-uv-cache uv run --frozen pytest -q tests/test_mvp03_openapi_contract.py`；静态检查所有组件引用、路径参数、owner写请求、SSE事件及只读导出。运行端点、容器恢复与真实Provider验收须后续任务分别完成。本轮0 Provider调用。
