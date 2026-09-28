# MVP-0.3-T008 受限模板渲染执行器验收与交接

[执行器](../../backend/app/services/animation_renderer.py) 仅接受注册表中 `source_status=approved` 且源码摘要匹配的链表插入/删除模板，并再次验证数据参数。它只复制当前尝试所需的方案、场景、注册表和固定 [容器入口](../../backend/app/animation_templates/container_runner.py)，不挂整个仓库。场景在 AST 层仅替换 `VALUES`、`INDEX`、`VALUE` 字面量，原始和编译后的源码均执行白名单导入、危险调用、反射及文件/网络入口审查；容器内注册表再次核对受版本控制的原始源码摘要。输入目录只读；任何代码、路径、URL 或额外参数在启动 Docker 前拒绝。

镜像固定为 `manimcommunity/manim@sha256:89ab433ce59134a4dcf351deb2511e067ab354393c0bb7d1859f3e8f0b2406a3`（Manim Community v0.21.0）。容器使用 UID/GID `10001:10001`、`--network none`、`--read-only`、`--cap-drop ALL`、`no-new-privileges`、2 CPU、1 GiB 内存、128 进程；`/tmp` 与 `/output` 各用 256 MiB tmpfs，输出总量在渲染过程中由文件系统硬限制。容器没有数据库、Docker socket、用户 Cookie、Provider 密钥或媒体库挂载。固定命令用参数数组传给 Docker，无 shell 拼接；Docker 不可用时返回 `RENDER_UNAVAILABLE`，不在宿主机回退。

容器内完整解码 MP4，校验 30–90 秒、尺寸、单文件不超过 64 MiB、SRT 每条非空及每 6 秒连续时间码；删掉 Manim 中间文件后仅允许固定 MP4/SRT。输出 tmpfs 无宿主挂载：Docker `cp` 在本环境不能读取运行中容器的 tmpfs，因此执行器仅通过运行中容器的固定 `cat` 路径有上限地取回最终文件，再核对 SHA-256；不放宽硬配额。媒体停留在本次私有候选目录，尚未发布或赋予 owner 权限。成功后移除容器和临时输入；超时/失败强制终止容器进程树并仅清理本次尝试目录，返回稳定错误码而非日志/路径。后续 T009/T010 负责正式缓存和 Job 发布。

实测：两种模板经正式执行器渲染后，插入 MP4 36.0 秒且 SHA-256 为 `35b4ee0ac13ecff166320e4b1abde9dccc4226f8e177216c92d0b61abaa94f01`，删除 MP4 42.0 秒且 SHA-256 为 `95d4ab163dc455156477cb5325733577b7ec089b3db6a4250ec645a73ee690ae`，均与 T006/T007 的中插/中删审核视频完全一致。真实容器负向探针中，外网连接、向 `/etc` 写入、向 `/output` 写超过 256 MiB 均失败；0.01 秒测试超时返回 `RENDER_TIMEOUT`，之后 `docker ps --filter name=edumind-render-` 无运行中容器，测试目录无残留尝试。AST 回归拒绝非法导入、`eval/exec`、文件读写、`os.system`、反射及读取任意环境变量。

运行 `EDUMIND_DOCKER_TESTS=1 UV_CACHE_DIR=/private/tmp/edumind-uv-cache uv run --frozen pytest -q tests/test_animation_renderer.py` 可复现真实 Docker 正负测试；默认运行仅保留无 Docker 的单元测试。宿主全量测试与静态检查结果记录在任务账本。真实 Provider 调用 0 次。若目标主机不能建立 tmpfs 硬配额、非 root 或禁网限制，执行器应失败关闭，需按 ADR-0004 另行处理，不改为软配额。
