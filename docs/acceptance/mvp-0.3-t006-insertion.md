# MVP-0.3-T006 链表插入模板验收与交接

固定模板通过 [步骤计划](../../backend/app/animation_templates/insertion_plan.py) 生成六段、每段 6 秒的画面及 SRT；[Manim 场景](../../backend/app/animation_templates/linked_list_insertion.py) 只接受白名单数据参数，默认示例为 `[1,3,5]` 在位置 1 插入 2。先建立 `new.next = successor`，再更新前驱 `next` 或 `head`。空表、头部、中部、尾部四种情况均由同一源码实际渲染。视频画面使用英文标注，默认中文 SRT 承担教学解说。

## 可重复构建

在 `backend/` 执行下列命令，Docker 使用固定的 `manimcommunity/manim:v0.21.0` 镜像摘要 `sha256:89ab433ce59134a4dcf351deb2511e067ab354393c0bb7d1859f3e8f0b2406a3`。入口会先校验参数，再以禁网、只读根文件系统、只读源码挂载和 CPU/内存/进程限制渲染，结果落在 Git 忽略的 `data/videos/cache/t006/<case>/`。

```bash
UV_CACHE_DIR=/private/tmp/edumind-uv-cache uv run --frozen python scripts/render_linked_list_insertion.py --case empty --parameters '{"values":[],"index":0,"value":7}'
UV_CACHE_DIR=/private/tmp/edumind-uv-cache uv run --frozen python scripts/render_linked_list_insertion.py --case head --parameters '{"values":[1,3,5],"index":0,"value":2}'
UV_CACHE_DIR=/private/tmp/edumind-uv-cache uv run --frozen python scripts/render_linked_list_insertion.py --case middle --parameters '{"values":[1,3,5],"index":1,"value":2}'
UV_CACHE_DIR=/private/tmp/edumind-uv-cache uv run --frozen python scripts/render_linked_list_insertion.py --case tail --parameters '{"values":[1,3,5],"index":3,"value":7}'
```

源审核摘要 `465e3d945dc6fcc905f7daba716eb349e42e9a79274d120f5306123d5a68df77` 按源文件相对路径、NUL、文件字节、NUL 依次计算，涵盖步骤计划与场景。注册表在 `approved` 加载时核对摘要。源码只从固定环境变量读取至多 256 字符的 JSON 值对象，经 schema 和索引边界校验；未导入或执行外部 Python，未引用文件/网络地址。此审核限于固定插入模板，T008 仍须实现通用模板编译和正式 Worker 安全边界。

## 实测证据

四次 Docker 命令退出码均为 0，生成的 MP4 均为 854×480、15 fps、540 帧、36.0 秒；SRT 均为六条 6 秒连续字幕，尾时间 `00:00:36,000`。媒体文件被 `.gitignore` 的 `data/videos/*` 规则忽略。

| 情况 | MP4 SHA-256 | 逐帧目视结果 |
| --- | --- | --- |
| 空表 | `786ead4fa3a911c6eec39c86c5ebabc247acee230dad4a94beed6c5eb3dee6eb` | 15 秒 `head→NULL` 与新节点 `7→NULL` 并存；21 秒 `head→7→NULL`。 |
| 头插 | `a63657777ce1a475b8dd41a977a81baa0647840b9c7430f64a8fecb6971d8531` | 15 秒旧 `head→1→3→5` 保留且新节点 `2→1`；21 秒 `head→2→1→3→5`。 |
| 中插 | `35b4ee0ac13ecff166320e4b1abde9dccc4226f8e177216c92d0b61abaa94f01` | 15 秒旧 `1→3→5` 保留且 `2→3`；21 秒 `1→2→3→5`。 |
| 尾插 | `593e5a1ab727d3ba8fbbbaf3fce8c8d16fcc6544c0470151c4070f553e61e9ca` | 15 秒旧 `5→NULL` 与新 `7→NULL` 分开；21 秒 `1→3→5→7→NULL`。 |

目视检查使用从最终 MP4 解码的 15 秒/21 秒帧；首次检查发现尾插的旧 `5→NULL` 漏画，修正后四个视频全部重新渲染、复查。SRT 的六段时间与场景的六次 6 秒播放对应，文本由 [确定性字幕函数](../../backend/app/animation_templates/insertion_plan.py) 提供。MP4/SRT 是本地验收产物，不进入 Git。

验证：`pytest -q tests/test_animation_templates.py tests/test_linked_list_insertion_plan.py tests/test_mvp03_openapi_contract.py`、Ruff、Mypy 通过；实际结果见任务账本。真实 Provider 调用 0 次。下一任务 T007 实现删除模板并单独完成审核，正式 Job/缓存/媒体接口在后续 T008–T010 完成。
