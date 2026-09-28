# MVP-0.3-T007 链表删除模板验收与交接

[确定性步骤](../../backend/app/animation_templates/deletion_plan.py) 按保存后继、改前驱连接或 `head`、释放目标的顺序生成七段状态。[Manim 场景](../../backend/app/animation_templates/linked_list_deletion.py) 在改连接时显示已脱离可达链的目标，释放之后完全不再显示或引用目标。空表、负索引和越界删除在渲染之前拒绝；单节点、头部、中部、尾部四种合法情形由同一源码实际渲染。

## 可重复构建

在 `backend/` 执行下列命令。入口与 T006 使用同一固定 Manim v0.21.0 镜像摘要 `sha256:89ab433ce59134a4dcf351deb2511e067ab354393c0bb7d1859f3e8f0b2406a3`，禁网、只读根文件系统和源码挂载，限制 CPU/内存/进程。产物写入 Git 忽略的 `data/videos/cache/t007/<case>/`。

```bash
UV_CACHE_DIR=/private/tmp/edumind-uv-cache uv run --frozen python scripts/render_linked_list_deletion.py --case single --parameters '{"values":[7],"index":0}'
UV_CACHE_DIR=/private/tmp/edumind-uv-cache uv run --frozen python scripts/render_linked_list_deletion.py --case head --parameters '{"values":[1,3,5],"index":0}'
UV_CACHE_DIR=/private/tmp/edumind-uv-cache uv run --frozen python scripts/render_linked_list_deletion.py --case middle --parameters '{"values":[1,3,5],"index":1}'
UV_CACHE_DIR=/private/tmp/edumind-uv-cache uv run --frozen python scripts/render_linked_list_deletion.py --case tail --parameters '{"values":[1,3,5],"index":2}'
```

源审核摘要 `9cc7219e43d482b54b4886fcefcd937ef3c84c02b54d45247d3113258b02de6d` 覆盖删除步骤与场景文件，注册表在 `approved` 加载时核对。场景仅从固定环境变量读取至多 256 字符的 JSON 值对象，再执行白名单 schema 与相对索引校验；未构造动态 Python 或使用用户路径/URL。模板审核边界限于此固定删除场景，正式 Worker 的通用静态审核、超时和产物控制仍属 T008。

## 实测证据

四次 Docker 命令退出码均为 0；MP4 均为 854×480、15 fps、630 帧、42.0 秒，符合 PRD 的 30–90 秒。SRT 均为七条连续 6 秒字幕，末尾 `00:00:42,000`，包括“释放后不能再访问”的明确提醒。英文画面标注配合默认中文 SRT。生成媒体被 `.gitignore` 的 `data/videos/*` 规则忽略。

| 情况 | MP4 SHA-256 | 逐帧目视结果 |
| --- | --- | --- |
| 单节点 | `c05520dbd13c08dde7f4bb460ca7cbac41a67e475d5da38f9aed5ccc245f8920` | 15 秒保存 `NULL`；21 秒 `head→NULL`、目标 7 已脱离；27 秒目标消失。 |
| 头删 | `4d5e58fdb761ada9777e9abcccdcf2dd8ba5ad6709ea125e576d3965acb1dbb4` | 15 秒保存 3；21 秒 `head→3→5`、目标 1 脱离；27 秒目标消失。 |
| 中删 | `95d4ab163dc455156477cb5325733577b7ec089b3db6a4250ec645a73ee690ae` | 15 秒保存 5；21 秒 `head→1→5`、目标 3 脱离；27 秒目标消失。 |
| 尾删 | `ee973d25fe5c6dcbf49340750b3a85167df8705903351de96fdda0f2ab474448` | 15 秒保存 `NULL`；21 秒 `head→1→3→NULL`、目标 5 脱离；27 秒目标消失。 |

验证覆盖全部合法位置和非法边界、释放后零悬空引用、源码摘要失配拒绝、真实 MP4/SRT 帧与时长。实际测试命令及结果写入任务账本。真实 Provider 调用 0 次。下一任务 T008 将本地固定模板入口收敛为受限执行器与正式安全边界。
